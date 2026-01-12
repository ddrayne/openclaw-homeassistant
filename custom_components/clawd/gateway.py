"""Low-level WebSocket protocol client for Clawdbot Gateway."""

import asyncio
import json
import logging
import uuid
from typing import Any, Callable

import websockets
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosedError

from .const import (
    CLIENT_DISPLAY_NAME,
    CLIENT_ID,
    CLIENT_MODE,
    CLIENT_PLATFORM,
    CLIENT_VERSION,
    PROTOCOL_MAX_VERSION,
    PROTOCOL_MIN_VERSION,
)
from .exceptions import (
    GatewayAuthenticationError,
    GatewayConnectionError,
    ProtocolError,
)

_LOGGER = logging.getLogger(__name__)


class GatewayProtocol:
    """Low-level Clawdbot Gateway WebSocket protocol implementation."""

    def __init__(
        self,
        host: str,
        port: int,
        token: str | None,
        use_ssl: bool = False,
    ) -> None:
        """Initialize the Gateway protocol client."""
        self._host = host
        self._port = port
        self._token = token
        self._use_ssl = use_ssl

        # Connection state
        self._websocket: WebSocketClientProtocol | None = None
        self._connected = False
        self._connected_event = asyncio.Event()
        self._connect_task: asyncio.Task | None = None
        self._receive_task: asyncio.Task | None = None

        # Request/response correlation
        self._pending_requests: dict[str, asyncio.Future] = {}

        # Event handlers
        self._event_handlers: dict[str, list[Callable]] = {}

        # Build WebSocket URI
        protocol = "wss" if use_ssl else "ws"
        self._uri = f"{protocol}://{host}:{port}"

    @property
    def connected(self) -> bool:
        """Return whether the connection is established."""
        return self._connected

    async def connect(self) -> None:
        """Connect to the Gateway and perform handshake."""
        if self._connect_task is not None:
            return

        self._connect_task = asyncio.create_task(self._connection_loop())

    async def disconnect(self) -> None:
        """Disconnect from the Gateway."""
        _LOGGER.info("Disconnecting from Gateway")
        self._connected = False
        self._connected_event.clear()

        # Cancel tasks
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._connect_task:
            self._connect_task.cancel()
            try:
                await self._connect_task
            except asyncio.CancelledError:
                pass

        # Close websocket
        if self._websocket:
            await self._websocket.close()
            self._websocket = None

        # Fail all pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.set_exception(
                    GatewayConnectionError("Connection closed")
                )
        self._pending_requests.clear()

    async def _connection_loop(self) -> None:
        """Maintain connection with automatic reconnection."""
        while True:
            try:
                _LOGGER.info("Connecting to Gateway at %s", self._uri)
                async for websocket in websockets.connect(
                    self._uri,
                    ping_interval=30,
                    ping_timeout=10,
                ):
                    self._websocket = websocket
                    try:
                        await self._handshake()
                        self._connected = True
                        self._connected_event.set()
                        _LOGGER.info("Connected to Gateway successfully")

                        # Start receive loop
                        self._receive_task = asyncio.create_task(
                            self._receive_loop()
                        )
                        await self._receive_task

                    except (
                        GatewayAuthenticationError,
                        ProtocolError,
                    ) as err:
                        _LOGGER.error("Gateway error: %s", err)
                        self._connected = False
                        self._connected_event.clear()
                        raise

                    except ConnectionClosedError as err:
                        # Handle WebSocket close gracefully
                        self._connected = False
                        self._connected_event.clear()
                        if err.rcvd and err.rcvd.code == 1012:
                            # Service restart - this is normal, will reconnect
                            _LOGGER.info("Gateway is restarting, will reconnect")
                        else:
                            _LOGGER.warning(
                                "Connection closed: %s (code: %s)",
                                err.rcvd.reason if err.rcvd else "unknown",
                                err.rcvd.code if err.rcvd else "none",
                            )

                    except Exception as err:  # pylint: disable=broad-except
                        _LOGGER.error(
                            "Unexpected error in connection: %s",
                            err,
                            exc_info=True,
                        )
                        self._connected = False
                        self._connected_event.clear()

                    finally:
                        if self._receive_task:
                            self._receive_task.cancel()
                            try:
                                await self._receive_task
                            except asyncio.CancelledError:
                                pass

            except asyncio.CancelledError:
                _LOGGER.debug("Connection loop cancelled")
                break

            except (GatewayAuthenticationError, ProtocolError):
                # Don't retry auth/protocol errors - these require user intervention
                _LOGGER.error(
                    "Fatal error - authentication or protocol issue. "
                    "Stopping connection attempts."
                )
                break

            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.warning(
                    "Connection failed, will retry: %s", err
                )
                await asyncio.sleep(5)  # Wait before reconnecting

    async def _handshake(self) -> None:
        """Perform connection handshake with authentication."""
        if not self._websocket:
            raise GatewayConnectionError("WebSocket not connected")

        # Build connect request
        connect_params: dict[str, Any] = {
            "minProtocol": PROTOCOL_MIN_VERSION,
            "maxProtocol": PROTOCOL_MAX_VERSION,
            "client": {
                "id": CLIENT_ID,
                "displayName": CLIENT_DISPLAY_NAME,
                "version": CLIENT_VERSION,
                "platform": CLIENT_PLATFORM,
                "mode": CLIENT_MODE,
            },
            "caps": [],  # No special capabilities
            "locale": "en-US",
            "userAgent": f"{CLIENT_DISPLAY_NAME}/{CLIENT_VERSION}",
        }

        # Add authentication if token is provided
        if self._token:
            connect_params["auth"] = {"token": self._token}

        request_id = str(uuid.uuid4())
        connect_request = {
            "type": "req",
            "id": request_id,
            "method": "connect",
            "params": connect_params,
        }

        _LOGGER.debug("Sending connect request")
        await self._websocket.send(json.dumps(connect_request))

        # Wait for response
        try:
            response_text = await asyncio.wait_for(
                self._websocket.recv(), timeout=10.0
            )
            response = json.loads(response_text)

            _LOGGER.debug("Received connect response: %s", response)

            if response.get("type") != "res":
                raise ProtocolError(
                    f"Expected response, got {response.get('type')}"
                )

            if response.get("id") != request_id:
                raise ProtocolError("Response ID mismatch")

            if not response.get("ok"):
                error_msg = response.get("error", "Unknown error")
                error_str = str(error_msg) if not isinstance(error_msg, str) else error_msg
                if "auth" in error_str.lower() or "token" in error_str.lower():
                    raise GatewayAuthenticationError(
                        f"Authentication failed: {error_msg}"
                    )
                raise ProtocolError(f"Connection failed: {error_msg}")

            _LOGGER.debug("Handshake completed successfully")

        except asyncio.TimeoutError as err:
            raise GatewayConnectionError(
                "Handshake timeout"
            ) from err

        except json.JSONDecodeError as err:
            raise ProtocolError(
                "Invalid JSON in handshake response"
            ) from err

    async def _receive_loop(self) -> None:
        """Receive and process messages from Gateway."""
        if not self._websocket:
            return

        try:
            async for message_text in self._websocket:
                try:
                    message = json.loads(message_text)
                    await self._handle_message(message)

                except json.JSONDecodeError:
                    _LOGGER.warning(
                        "Received invalid JSON: %s", message_text
                    )

                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.error(
                        "Error handling message: %s",
                        err,
                        exc_info=True,
                    )

        except asyncio.CancelledError:
            _LOGGER.debug("Receive loop cancelled")
            raise

        except ConnectionClosedError as err:
            # Handle WebSocket close gracefully
            if err.rcvd and err.rcvd.code == 1012:
                # Service restart - this is normal, will reconnect automatically
                _LOGGER.info("Gateway is restarting, will reconnect automatically")
            else:
                _LOGGER.warning(
                    "WebSocket connection closed: %s (code: %s)",
                    err.rcvd.reason if err.rcvd else "unknown",
                    err.rcvd.code if err.rcvd else "none",
                )
            raise

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error(
                "Error in receive loop: %s", err, exc_info=True
            )
            raise

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle incoming message from Gateway."""
        message_type = message.get("type")

        if message_type == "res":
            # Response to a request
            request_id = message.get("id")
            if request_id in self._pending_requests:
                future = self._pending_requests[request_id]
                if not future.done():
                    future.set_result(message)
            else:
                # Response arrived after timeout/cleanup - this is normal
                _LOGGER.debug(
                    "Received response for request that already timed out: %s",
                    request_id,
                )

        elif message_type == "event":
            # Server-pushed event
            event_name = message.get("event")
            if event_name:
                await self._dispatch_event(event_name, message)
            else:
                _LOGGER.warning("Event message without event name")

        else:
            _LOGGER.warning("Unknown message type: %s", message_type)

    async def _dispatch_event(
        self, event_name: str, event: dict[str, Any]
    ) -> None:
        """Dispatch event to registered handlers."""
        handlers = self._event_handlers.get(event_name, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.error(
                    "Error in event handler for %s: %s",
                    event_name,
                    err,
                    exc_info=True,
                )

    def on_event(self, event_name: str, handler: Callable) -> None:
        """Register an event handler."""
        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = []
        # Prevent duplicate handler registration
        if handler not in self._event_handlers[event_name]:
            self._event_handlers[event_name].append(handler)

    async def send_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Send a request and wait for response."""
        if not self._connected or not self._websocket:
            raise GatewayConnectionError("Not connected to Gateway")

        request_id = str(uuid.uuid4())
        request = {
            "type": "req",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        # Create future for response
        future: asyncio.Future = asyncio.Future()
        self._pending_requests[request_id] = future

        try:
            # Send request
            _LOGGER.debug("Sending request: %s %s", method, request_id)
            await self._websocket.send(json.dumps(request))

            # Wait for response
            response = await asyncio.wait_for(future, timeout=timeout)

            if not response.get("ok"):
                error_msg = response.get("error", "Unknown error")
                raise ProtocolError(f"Request failed: {error_msg}")

            return response

        except asyncio.TimeoutError as err:
            raise GatewayConnectionError(
                f"Request timeout for {method}"
            ) from err

        finally:
            # Clean up pending request
            self._pending_requests.pop(request_id, None)
