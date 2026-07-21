"""Low-level WebSocket protocol client for OpenClaw Gateway."""

import asyncio
import inspect
import json
import logging
import time
import uuid
from typing import Any, Callable

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedError, InvalidStatus

from .const import (
    CHALLENGE_TIMEOUT,
    CLIENT_DISPLAY_NAME,
    CLIENT_ID,
    CLIENT_MODE,
    CLIENT_PLATFORM,
    CLIENT_VERSION,
    DEVICE_ROLE,
    DEVICE_SCOPES,
    PROTOCOL_MAX_VERSION,
    PROTOCOL_MIN_VERSION,
)
from .device_auth import async_load_or_create_keypair, build_device_auth_dict
from .exceptions import (
    DevicePairingRequiredError,
    GatewayAuthenticationError,
    GatewayConnectionError,
    ProtocolError,
)

_LOGGER = logging.getLogger(__name__)


class GatewayProtocol:
    """Low-level OpenClaw Gateway WebSocket protocol implementation."""

    def __init__(
        self,
        host: str,
        port: int,
        token: str | None,
        use_ssl: bool = False,
        hass: Any | None = None,
    ) -> None:
        """Initialize the Gateway protocol client."""
        self._hass = hass
        self._host = host
        self._port = port
        self._token = token
        self._use_ssl = use_ssl

        # Connection state
        self._websocket: Any | None = None
        self._connected = False
        self._connected_event = asyncio.Event()
        self._connect_task: asyncio.Task | None = None
        self._receive_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._heartbeat_interval = 30
        self._last_pong = 0.0

        # Request/response correlation
        self._pending_requests: dict[str, asyncio.Future] = {}

        # Event handlers
        self._event_handlers: dict[str, list[Callable]] = {}

        # Snapshot from the connect handshake response
        self._connect_snapshot: dict[str, Any] = {}

        # Presence data from WS events (seeded from snapshot)
        self._presence: dict[str, Any] = {}

        # Fatal error that stopped the connection loop (auth / protocol)
        self._fatal_error: Exception | None = None
        self._on_fatal_error: Callable[[Exception], None] | None = None
        # Fired after every successful handshake so callers can re-issue
        # per-connection state (e.g. session subscriptions) on reconnect.
        self._on_connected: Callable[[], None] | None = None

        # Keep credentials out of the URI so they cannot leak through logs,
        # proxies, or exception messages. Authentication is sent in the
        # connect payload below, with headers retained for legacy gateways.
        protocol = "wss" if use_ssl else "ws"
        self._uri = f"{protocol}://{host}:{port}"

    @property
    def connected(self) -> bool:
        """Return whether the connection is established."""
        return self._connected

    @property
    def connect_snapshot(self) -> dict[str, Any]:
        """Return the snapshot received during the connect handshake."""
        return self._connect_snapshot

    @property
    def presence(self) -> dict[str, Any]:
        """Return the latest presence data."""
        return self._presence

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

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._connect_task:
            self._connect_task.cancel()
            try:
                await self._connect_task
            except asyncio.CancelledError:
                pass
            self._connect_task = None

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
                headers = {}
                if self._token:
                    headers["Authorization"] = f"Bearer {self._token}"
                    headers["X-OpenClaw-Token"] = self._token
                async with connect(
                    self._uri,
                    ping_interval=30,
                    ping_timeout=10,
                    additional_headers=headers,
                ) as websocket:
                    self._websocket = websocket
                    try:
                        await self._handshake()
                        self._connected = True
                        self._connected_event.set()
                        _LOGGER.info("Connected to Gateway successfully")
                        self._last_pong = time.monotonic()

                        # Start receive loop
                        self._receive_task = asyncio.create_task(
                            self._receive_loop()
                        )
                        self._heartbeat_task = asyncio.create_task(
                            self._heartbeat_loop()
                        )
                        # Notify callers now that the receive loop is running,
                        # so any subscription requests they send get responses.
                        if self._on_connected:
                            try:
                                self._on_connected()
                            except Exception:  # pylint: disable=broad-except
                                _LOGGER.exception(
                                    "on_connected callback failed"
                                )
                        await self._receive_task

                    except GatewayAuthenticationError as err:
                        self._fatal_error = err
                        if isinstance(err, DevicePairingRequiredError):
                            _LOGGER.warning(
                                "Device not yet approved in OpenClaw. "
                                "Approve this device in the OpenClaw CLI "
                                "or Control UI. Detail: %s",
                                err,
                            )
                        else:
                            _LOGGER.error(
                                "Gateway authentication failed. Check that "
                                "the token in Settings > Devices & Services "
                                "> OpenClaw > Configure matches your gateway "
                                "token (openclaw doctor "
                                "--generate-gateway-token). Detail: %s",
                                err,
                            )
                        if self._on_fatal_error:
                            self._on_fatal_error(err)
                        # Return instead of raise: re-raising inside
                        # the websockets context manager allows
                        # __aexit__ to replace the exception with
                        # ConnectionClosedError, which the outer loop
                        # treats as transient, creating an infinite
                        # retry loop.
                        return

                    except ProtocolError as err:
                        self._fatal_error = err
                        _LOGGER.error(
                            "Gateway protocol error - the integration may "
                            "be incompatible with this gateway version. "
                            "Detail: %s",
                            err,
                        )
                        if self._on_fatal_error:
                            self._on_fatal_error(err)
                        return

                    finally:
                        self._connected = False
                        self._connected_event.clear()
                        if self._receive_task:
                            self._receive_task.cancel()
                            try:
                                await self._receive_task
                            except asyncio.CancelledError:
                                pass
                        if self._heartbeat_task:
                            self._heartbeat_task.cancel()
                            try:
                                await self._heartbeat_task
                            except asyncio.CancelledError:
                                pass
                        self._websocket = None

            except asyncio.CancelledError:
                _LOGGER.debug("Connection loop cancelled")
                break

            except (GatewayAuthenticationError, ProtocolError) as err:
                # Don't retry auth/protocol errors - these require user intervention
                if not self._fatal_error:
                    self._fatal_error = err
                    _LOGGER.error("Gateway connection stopped: %s", err)
                    if self._on_fatal_error:
                        self._on_fatal_error(err)
                break

            except InvalidStatus as err:
                if err.response.status_code in (401, 403):
                    auth_err = GatewayAuthenticationError(
                        f"Gateway rejected connection: HTTP {err.response.status_code}"
                    )
                    self._fatal_error = auth_err
                    _LOGGER.error(
                        "Gateway authentication failed (HTTP %s). Check that "
                        "the token in Settings > Devices & Services > OpenClaw "
                        "> Configure matches your gateway token "
                        "(openclaw doctor --generate-gateway-token)",
                        err.response.status_code,
                    )
                    if self._on_fatal_error:
                        self._on_fatal_error(auth_err)
                    break
                _LOGGER.warning(
                    "Gateway rejected WebSocket upgrade: HTTP %s",
                    err.response.status_code,
                )
                await asyncio.sleep(5)

            except ConnectionClosedError as err:
                if err.rcvd and err.rcvd.code == 1012:
                    # Service restart - this is normal, will reconnect
                    _LOGGER.info("Gateway is restarting, will reconnect")
                else:
                    _LOGGER.warning(
                        "Connection closed: %s (code: %s)",
                        err.rcvd.reason if err.rcvd else "unknown",
                        err.rcvd.code if err.rcvd else "none",
                    )
                await asyncio.sleep(5)

            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.warning(
                    "Connection failed, will retry: %s", err
                )
                await asyncio.sleep(5)  # Wait before reconnecting

    async def _handshake(self) -> None:
        """Perform connection handshake with authentication.

        Supports both legacy (no challenge) and new (challenge + device auth)
        flows for backwards compatibility with gateways older than 2026.2.13.
        """
        if not self._websocket:
            raise GatewayConnectionError("WebSocket not connected")

        # Step 1: Wait for optional connect.challenge event from server
        nonce: str | None = None
        first_message: dict[str, Any] | None = None

        try:
            challenge_text = await asyncio.wait_for(
                self._websocket.recv(), timeout=CHALLENGE_TIMEOUT
            )
            challenge = json.loads(challenge_text)
            if (
                challenge.get("type") == "event"
                and challenge.get("event") == "connect.challenge"
            ):
                nonce = challenge.get("payload", {}).get("nonce")
                _LOGGER.debug("Received connect.challenge")
            else:
                _LOGGER.debug(
                    "First message was not connect.challenge (%s/%s), "
                    "using legacy handshake",
                    challenge.get("type"),
                    challenge.get("event", ""),
                )
                first_message = challenge
        except asyncio.TimeoutError:
            _LOGGER.debug(
                "No connect.challenge received within %.1fs, "
                "using legacy handshake",
                CHALLENGE_TIMEOUT,
            )
        except json.JSONDecodeError:
            _LOGGER.debug("Non-JSON first message, using legacy handshake")

        # Step 2: Build connect request
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
            "caps": [],
            "locale": "en-US",
            "userAgent": f"{CLIENT_DISPLAY_NAME}/{CLIENT_VERSION}",
        }

        if self._token:
            connect_params["auth"] = {"token": self._token}

        # Role and scopes are required for the gateway to grant permissions.
        connect_params["role"] = DEVICE_ROLE
        connect_params["scopes"] = DEVICE_SCOPES

        # Include device credentials when a challenge nonce is received
        # and hass is available for keypair storage.
        if nonce and self._hass:
            key = await async_load_or_create_keypair(self._hass)
            connect_params["device"] = build_device_auth_dict(
                key=key,
                client_id=CLIENT_ID,
                client_mode=CLIENT_MODE,
                role=DEVICE_ROLE,
                scopes=DEVICE_SCOPES,
                token=self._token or "",
                nonce=nonce,
            )
            _LOGGER.debug("Including device credentials in connect request")
        elif nonce:
            _LOGGER.debug(
                "Challenge received but no hass context; "
                "using token-only auth"
            )

        request_id = str(uuid.uuid4())
        connect_request = {
            "type": "req",
            "id": request_id,
            "method": "connect",
            "params": connect_params,
        }

        _LOGGER.debug("Sending connect request")
        await self._websocket.send(json.dumps(connect_request))

        # Step 3: Wait for response
        try:
            while True:
                # Process stored first_message before reading from socket
                if first_message is not None:
                    response = first_message
                    first_message = None
                else:
                    response_text = await asyncio.wait_for(
                        self._websocket.recv(), timeout=10.0
                    )
                    response = json.loads(response_text)

                if response.get("type") == "event":
                    _LOGGER.debug(
                        "Received event during handshake, skipping: %s",
                        response.get("event"),
                    )
                    continue

                _LOGGER.debug(
                    "Received connect response (type=%s, ok=%s)",
                    response.get("type"),
                    response.get("ok"),
                )

                if response.get("type") != "res":
                    raise ProtocolError(
                        f"Expected response, got {response.get('type')}"
                    )

                break

            if response.get("id") != request_id:
                raise ProtocolError("Response ID mismatch")

            if not response.get("ok"):
                error_msg = response.get("error", "Unknown error")
                error_str = str(error_msg) if not isinstance(error_msg, str) else error_msg
                error_lower = error_str.lower()

                # Detect NOT_PAIRED specifically before generic auth errors
                error_code = None
                if isinstance(error_msg, dict):
                    error_code = error_msg.get("code")
                if error_code == "NOT_PAIRED" or "not_paired" in error_lower:
                    raise DevicePairingRequiredError(
                        f"Device pairing required: {error_msg}"
                    )

                if any(
                    kw in error_lower
                    for kw in ("auth", "token", "nonce", "device", "pair")
                ):
                    raise GatewayAuthenticationError(
                        f"Authentication failed: {error_msg}"
                    )
                raise ProtocolError(f"Connection failed: {error_msg}")

            self._connect_snapshot = response.get("payload", {})
            presence = (
                self._connect_snapshot
                .get("snapshot", {})
                .get("presence", {})
            )
            if isinstance(presence, list):
                presence = {"clients": presence}
            self._presence = presence
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
                        "Received invalid JSON message (%d characters)",
                        len(message_text),
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

        elif message_type == "ping":
            await self._send_pong()

        elif message_type == "pong":
            self._last_pong = time.monotonic()
            _LOGGER.debug("Received heartbeat pong")

        else:
            _LOGGER.warning("Unknown message type: %s", message_type)

    async def _send_pong(self) -> None:
        """Respond to a heartbeat ping."""
        if not self._websocket:
            return
        try:
            await self._websocket.send(json.dumps({"type": "pong"}))
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("Failed to send pong: %s", err)

    async def _heartbeat_loop(self) -> None:
        """Send heartbeat pings while connected."""
        while self._connected and self._websocket:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                if not self._connected or not self._websocket:
                    break
                await self._websocket.send(json.dumps({"type": "ping"}))
            except asyncio.CancelledError:
                raise
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.warning("Heartbeat failed: %s", err)
                break

    async def _dispatch_event(
        self, event_name: str, event: dict[str, Any]
    ) -> None:
        """Dispatch event to registered handlers."""
        handlers = self._event_handlers.get(event_name, [])
        _LOGGER.debug(
            "Dispatching %s event to %d handler(s)", event_name, len(handlers)
        )
        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
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
            _LOGGER.debug(
                "Registered event handler for %s (total handlers: %d)",
                event_name,
                len(self._event_handlers[event_name]),
            )
        else:
            _LOGGER.warning(
                "Attempted to register duplicate handler for %s (ignored)",
                event_name,
            )

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

                error_code: str | None = None
                error_text = str(error_msg)
                if isinstance(error_msg, dict):
                    error_code = error_msg.get("code")
                    error_text = str(error_msg.get("message", error_msg))

                error_text_lower = error_text.lower()
                if (
                    error_code in {"UNAUTHORIZED", "FORBIDDEN", "AUTH_FAILED"}
                    or "missing scope" in error_text_lower
                    or "invalid token" in error_text_lower
                    or "authentication" in error_text_lower
                    or "unauthorized" in error_text_lower
                ):
                    raise GatewayAuthenticationError(
                        f"Request failed: {error_text}"
                    )

                raise ProtocolError(f"Request failed: {error_msg}")

            return response

        except asyncio.TimeoutError as err:
            raise GatewayConnectionError(
                f"Request timeout for {method}"
            ) from err

        finally:
            # Clean up pending request
            self._pending_requests.pop(request_id, None)
