"""High-level OpenClaw Gateway API client."""

import asyncio
import logging
import time
import uuid
from typing import Any, AsyncIterator

from .exceptions import (
    AgentExecutionError,
    GatewayAuthenticationError,
    GatewayConnectionError,
    GatewayTimeoutError,
    ProtocolError,
)
from .gateway import GatewayProtocol

_LOGGER = logging.getLogger(__name__)


class AgentRun:
    """Tracks an agent run and buffers its events."""

    def __init__(self, run_id: str, stream: bool = False) -> None:
        """Initialize agent run tracker."""
        self.run_id = run_id
        self.status: str | None = None
        self.summary: str | None = None
        self.complete_event = asyncio.Event()
        # Gateway sends cumulative text, not incremental
        self._full_text: str = ""
        self._stream_queue: asyncio.Queue[str | None] | None = (
            asyncio.Queue() if stream else None
        )
        self._streamed_any = False

    def add_output(self, output: str) -> None:
        """Add output to buffer. Gateway sends cumulative text, extract only new chars."""
        if not output:
            return

        # Gateway sends full text each time, only append what's new
        if output.startswith(self._full_text):
            # This is cumulative text, extract new portion
            new_text = output[len(self._full_text) :]
            if new_text:
                self._full_text = output
                _LOGGER.debug(
                    "Added %d new chars to %s (total: %d)",
                    len(new_text),
                    self.run_id,
                    len(self._full_text),
                )
        else:
            # Not cumulative (shouldn't happen), just replace
            _LOGGER.warning(
                "Non-cumulative text update for %s (was: %d, now: %d)",
                self.run_id,
                len(self._full_text),
                len(output),
            )
            new_text = output
            self._full_text = output

        if new_text and self._stream_queue is not None:
            self._stream_queue.put_nowait(new_text)
            self._streamed_any = True

    def set_complete(self, status: str, summary: str | None = None) -> None:
        """Mark run as complete."""
        self.status = status
        self.summary = summary
        self.complete_event.set()
        if self._stream_queue is not None:
            if summary and not self._streamed_any:
                self._stream_queue.put_nowait(summary)
                self._streamed_any = True
            self._stream_queue.put_nowait(None)

    def get_response(self) -> str:
        """Get assembled response."""
        if self.summary:
            return self.summary
        return self._full_text

    async def iter_stream(self, timeout: float) -> AsyncIterator[str]:
        """Yield output chunks until completion or timeout."""
        if self._stream_queue is None:
            self._stream_queue = asyncio.Queue()

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GatewayTimeoutError("Agent response timeout")
            try:
                chunk = await asyncio.wait_for(
                    self._stream_queue.get(), timeout=remaining
                )
            except asyncio.TimeoutError as err:
                raise GatewayTimeoutError(
                    "Agent response timeout"
                ) from err
            if chunk is None:
                break
            yield chunk


class OpenClawGatewayClient:
    """High-level Gateway API client with event buffering."""

    def __init__(
        self,
        host: str,
        port: int,
        token: str | None,
        use_ssl: bool = False,
        timeout: int = 30,
        session_key: str = "main",
        model: str | None = None,
        thinking: str | None = None,
        hass: Any | None = None,
    ) -> None:
        """Initialize the Gateway client."""
        self._gateway = GatewayProtocol(
            host, port, token, use_ssl, hass=hass
        )
        self._timeout = timeout
        self._session_key = session_key
        self._model = model
        self._thinking = thinking
        self._agent_runs: dict[str, AgentRun] = {}

        # Register event handlers
        self._gateway.on_event("agent", self._handle_agent_event)
        self._gateway.on_event("presence", self._handle_presence_event)

    @property
    def fatal_error(self) -> Exception | None:
        """Return the fatal error that stopped the gateway connection, if any."""
        return self._gateway._fatal_error

    async def connect(self) -> None:
        """Connect to Gateway.

        Raises:
            GatewayAuthenticationError: If authentication fails.
            GatewayConnectionError: If connection fails or times out.
        """
        await self._gateway.connect()

        # Wait for connection to be established (event-based, no polling)
        try:
            await asyncio.wait_for(
                self._gateway._connected_event.wait(), timeout=5.0
            )
        except asyncio.TimeoutError:
            fatal = self._gateway._fatal_error
            if isinstance(fatal, GatewayAuthenticationError):
                raise fatal
            if isinstance(fatal, ProtocolError):
                raise GatewayConnectionError(str(fatal)) from fatal
            if fatal:
                raise GatewayConnectionError(str(fatal)) from fatal
            raise GatewayConnectionError(
                f"Connection timeout - Gateway at {self._gateway._host}:"
                f"{self._gateway._port} may not be reachable"
            )

    async def disconnect(self) -> None:
        """Disconnect from Gateway."""
        await self._gateway.disconnect()

    @property
    def connected(self) -> bool:
        """Return whether connected to Gateway."""
        return self._gateway.connected

    @property
    def session_key(self) -> str:
        """Return the active session key."""
        return self._session_key

    def set_session_key(self, session_key: str) -> None:
        """Set the active session key for new requests."""
        self._session_key = session_key

    @property
    def model(self) -> str | None:
        """Return the configured model override."""
        return self._model

    def set_model(self, model: str | None) -> None:
        """Set the configured model override."""
        self._model = model

    @property
    def thinking(self) -> str | None:
        """Return the configured thinking mode override."""
        return self._thinking

    def set_thinking(self, thinking: str | None) -> None:
        """Set the configured thinking mode override."""
        self._thinking = thinking

    async def send_agent_request(
        self, message: str, idempotency_key: str | None = None
    ) -> str:
        """
        Send agent request and return complete response.

        Handles event buffering automatically.

        Args:
            message: User message to send to agent
            idempotency_key: Optional idempotency key for safe retries

        Returns:
            Complete response from agent

        Raises:
            GatewayTimeoutError: If request times out
            AgentExecutionError: If agent execution fails
        """
        if idempotency_key is None:
            idempotency_key = str(uuid.uuid4())

        _LOGGER.debug("Sending agent request with key: %s", idempotency_key)

        # Send agent request
        try:
            options: dict[str, Any] = {}
            if self._model:
                options["model"] = self._model
            if self._thinking:
                options["thinking"] = self._thinking
            response = await self._gateway.send_request(
                method="agent",
                params={
                    "message": message,
                    "sessionKey": self._session_key,
                    "idempotencyKey": idempotency_key,
                    **({"options": options} if options else {}),
                },
                timeout=10.0,  # Initial ack should be quick
            )

            # Extract runId from acknowledgment
            payload = response.get("payload", {})
            run_id = payload.get("runId")

            if not run_id:
                raise AgentExecutionError("No runId in agent response")

            _LOGGER.debug("Agent run started: %s", run_id)

            # Create run tracker
            agent_run = AgentRun(run_id)
            self._agent_runs[run_id] = agent_run

            try:
                # Wait for completion
                await asyncio.wait_for(
                    agent_run.complete_event.wait(), timeout=self._timeout
                )

                # Check status
                if agent_run.status == "ok":
                    response_text = agent_run.get_response()
                    _LOGGER.debug(
                        "Agent run completed: %s chars",
                        len(response_text),
                    )
                    return response_text

                if agent_run.status == "error":
                    raise AgentExecutionError(
                        f"Agent execution failed: {agent_run.summary}"
                    )

                raise AgentExecutionError(
                    f"Unknown agent status: {agent_run.status}"
                )

            except asyncio.TimeoutError as err:
                _LOGGER.warning(
                    "Agent request timeout after %s seconds", self._timeout
                )
                raise GatewayTimeoutError(
                    "Agent response timeout"
                ) from err

            finally:
                # Clean up run tracker
                self._agent_runs.pop(run_id, None)

        except (GatewayConnectionError, GatewayTimeoutError):
            raise

        except AgentExecutionError:
            raise

        except Exception as err:
            _LOGGER.error(
                "Error in agent request: %s", err, exc_info=True
            )
            raise AgentExecutionError(str(err)) from err

    async def stream_agent_request(
        self, message: str, idempotency_key: str | None = None
    ) -> AsyncIterator[str]:
        """
        Send agent request and stream response chunks.

        Args:
            message: User message to send to agent
            idempotency_key: Optional idempotency key for safe retries

        Yields:
            Text chunks from the agent response

        Raises:
            GatewayTimeoutError: If request times out
            AgentExecutionError: If agent execution fails
        """
        if idempotency_key is None:
            idempotency_key = str(uuid.uuid4())

        _LOGGER.debug("Streaming agent request with key: %s", idempotency_key)

        try:
            options: dict[str, Any] = {}
            if self._model:
                options["model"] = self._model
            if self._thinking:
                options["thinking"] = self._thinking
            response = await self._gateway.send_request(
                method="agent",
                params={
                    "message": message,
                    "sessionKey": self._session_key,
                    "idempotencyKey": idempotency_key,
                    **({"options": options} if options else {}),
                },
                timeout=10.0,
            )

            payload = response.get("payload", {})
            run_id = payload.get("runId")

            if not run_id:
                raise AgentExecutionError("No runId in agent response")

            _LOGGER.debug("Agent run started: %s", run_id)

            agent_run = AgentRun(run_id, stream=True)
            self._agent_runs[run_id] = agent_run

            try:
                async for chunk in agent_run.iter_stream(self._timeout):
                    yield chunk

                if agent_run.status == "ok":
                    return

                if agent_run.status == "error":
                    raise AgentExecutionError(
                        f"Agent execution failed: {agent_run.summary}"
                    )

                raise AgentExecutionError(
                    f"Unknown agent status: {agent_run.status}"
                )

            finally:
                self._agent_runs.pop(run_id, None)

        except (GatewayConnectionError, GatewayTimeoutError):
            raise

        except AgentExecutionError:
            raise

        except Exception as err:
            _LOGGER.error(
                "Error in streaming agent request: %s", err, exc_info=True
            )
            raise AgentExecutionError(str(err)) from err

    def _handle_agent_event(self, event: dict[str, Any]) -> None:
        """Handle agent event and buffer output."""
        payload = event.get("payload", {})
        run_id = payload.get("runId")

        if not run_id:
            _LOGGER.warning("Agent event without runId")
            return

        agent_run = self._agent_runs.get(run_id)
        if not agent_run:
            # Event for unknown run, might be from previous session
            _LOGGER.debug("Agent event for unknown run: %s", run_id)
            return

        # Log event details for debugging
        data = payload.get("data", {})
        _LOGGER.debug(
            "Agent event for %s: status=%s, output=%s, summary=%s, data keys=%s",
            run_id,
            payload.get("status"),
            "yes" if payload.get("output") else "no",
            "yes" if payload.get("summary") else "no",
            list(data.keys()) if data else "none",
        )

        # Buffer output from either 'output' field or 'data.text' field
        output = payload.get("output")
        if not output and "text" in data:
            output = data.get("text")

        if output:
            agent_run.add_output(output)

        # Check for completion - either via status field or phase field
        status = payload.get("status")
        phase = data.get("phase")

        if status in ("ok", "error"):
            # Old-style completion
            summary = payload.get("summary")
            agent_run.set_complete(status, summary)
            _LOGGER.info("Agent run %s completed with status: %s", run_id, status)
        elif phase == "end" or phase == "complete":
            # New-style completion via phase
            agent_run.set_complete("ok", None)
            _LOGGER.info("Agent run %s completed (phase: %s)", run_id, phase)
        elif status:
            _LOGGER.debug("Agent run %s status: %s (not complete)", run_id, status)
        elif phase:
            _LOGGER.debug("Agent run %s phase: %s", run_id, phase)

    @property
    def connect_snapshot(self) -> dict[str, Any]:
        """Return the snapshot received during the connect handshake."""
        return self._gateway.connect_snapshot

    @property
    def presence(self) -> dict[str, Any]:
        """Return the latest presence data."""
        return self._gateway.presence

    def _handle_presence_event(self, event: dict[str, Any]) -> None:
        """Handle presence event and update state."""
        payload = event.get("payload", {})
        if payload:
            if isinstance(payload, list):
                payload = {"clients": payload}
            self._gateway._presence = payload

    async def health(self) -> dict[str, Any]:
        """Get Gateway health status."""
        response = await self._gateway.send_request("health", timeout=5.0)
        return response.get("payload", {})

    async def status(self) -> dict[str, Any]:
        """Get Gateway status."""
        response = await self._gateway.send_request("status", timeout=5.0)
        return response.get("payload", {})
