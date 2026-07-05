"""High-level OpenClaw Gateway API client."""

import asyncio
import logging
import time
import uuid
from typing import Any, AsyncIterator, Callable

from .const import PROACTIVE_SUPPRESS_SECONDS
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
        # Set once the completion sentinel has been dequeued, so a consumer
        # that peeked the sentinel (grace race) doesn't wait for a second one.
        self._stream_done = False

    def add_output(self, output: str) -> None:
        """Add output to buffer. Gateway sends cumulative text, extract only new chars."""
        if not output:
            return

        if self._full_text and output.strip() in ("[]", "{}"):
            _LOGGER.debug(
                "Ignoring structural text update for %s: %s",
                self.run_id,
                output.strip(),
            )
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
            # Only surface a summary as streamed content on success. On error the
            # summary is an internal diagnostic (e.g. a stopReason); streaming it
            # would speak the raw error via TTS and, by setting had_content, would
            # suppress the conversation entity's friendly error fallback.
            # stream_agent_request still raises on error status once the queue
            # drains, so the caller fails cleanly.
            if status == "ok" and summary and not self._streamed_any:
                self._stream_queue.put_nowait(summary)
                self._streamed_any = True
            self._stream_queue.put_nowait(None)

    def get_response(self) -> str:
        """Get assembled response."""
        if self.summary:
            return self.summary
        return self._full_text

    async def get_chunk(self, timeout: float) -> str | None:
        """Await the next streamed chunk; None is the completion sentinel.

        Used to peek for first content during the grace race. Raises
        asyncio.TimeoutError when nothing arrives in time — safe to cancel:
        a queued item is never lost by a cancelled get().
        """
        if self._stream_queue is None:
            self._stream_queue = asyncio.Queue()
        if self._stream_done:
            return None
        chunk = await asyncio.wait_for(self._stream_queue.get(), timeout=timeout)
        if chunk is None:
            self._stream_done = True
        return chunk

    async def iter_stream(self, timeout: float) -> AsyncIterator[str]:
        """Yield output chunks until completion or timeout.

        The timeout applies per-chunk: each new chunk resets the clock.
        This prevents long but actively-streaming responses from timing out.
        """
        if self._stream_queue is None:
            self._stream_queue = asyncio.Queue()

        while not self._stream_done:
            try:
                chunk = await asyncio.wait_for(
                    self._stream_queue.get(), timeout=timeout
                )
            except asyncio.TimeoutError as err:
                raise GatewayTimeoutError(
                    "Agent response timeout"
                ) from err
            if chunk is None:
                self._stream_done = True
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
        agent_id: str | None = None,
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
        self._agent_id = agent_id
        self._model = model
        self._thinking = thinking
        self._agent_runs: dict[str, AgentRun] = {}

        # Proactive voice: callback invoked with agent-initiated assistant text,
        # and a timestamp of the most recent local agent activity used to
        # suppress echoes of the user's own conversation turns.
        self._proactive_callback: Callable[[str], None] | None = None
        self._last_local_turn: float = 0.0

        # Register event handlers
        self._gateway.on_event("agent", self._handle_agent_event)
        self._gateway.on_event("presence", self._handle_presence_event)
        self._gateway.on_event("session.message", self._handle_session_message)
        self._gateway._on_connected = self._on_gateway_connected

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
    def agent_id(self) -> str | None:
        """Return the configured agent ID override."""
        return self._agent_id

    def set_agent_id(self, agent_id: str | None) -> None:
        """Set the configured agent ID override."""
        self._agent_id = agent_id

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

    @property
    def _effective_session_key(self) -> str:
        """Build the session key, prefixed with agent ID when configured."""
        if self._agent_id:
            return f"agent:{self._agent_id}:{self._session_key}"
        return self._session_key

    async def _start_agent_run(
        self, message: str, idempotency_key: str, *, stream: bool = False
    ) -> AgentRun:
        """Send the agent request and return a tracked AgentRun."""
        # Mark local activity so proactive voice suppresses the session echo.
        self._last_local_turn = time.monotonic()
        options: dict[str, Any] = {}
        if self._model:
            options["model"] = self._model
        if self._thinking:
            options["thinking"] = self._thinking

        response = await self._gateway.send_request(
            method="agent",
            params={
                "message": message,
                "sessionKey": self._effective_session_key,
                "idempotencyKey": idempotency_key,
                **options,
            },
            timeout=10.0,
        )

        payload = response.get("payload", {})
        run_id = payload.get("runId")

        if not run_id:
            raise AgentExecutionError("No runId in agent response")

        _LOGGER.debug("Agent run started: %s", run_id)

        agent_run = AgentRun(run_id, stream=stream)
        self._agent_runs[run_id] = agent_run
        self._buffer_agent_payload(agent_run, payload)
        return agent_run

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

        try:
            agent_run = await self._start_agent_run(message, idempotency_key)
            run_id = agent_run.run_id

            try:
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

    async def begin_agent_run(
        self, message: str, idempotency_key: str | None = None
    ) -> AgentRun:
        """Start an agent run without consuming it.

        Chunks buffer in the run's stream queue from this moment; consume them
        with stream_run(). Splitting start from consumption lets the caller
        race the run against a grace timer and hand it off to a background
        consumer without cancelling a generator mid-flight.
        """
        if idempotency_key is None:
            idempotency_key = str(uuid.uuid4())
        _LOGGER.debug("Beginning agent run with key: %s", idempotency_key)
        return await self._start_agent_run(message, idempotency_key, stream=True)

    async def wait_run(self, agent_run: AgentRun, timeout: float) -> str:
        """Wait for an already-started run to complete and return its text.

        For detached (background) consumers: the timeout is an overall
        completion budget, not a per-chunk one — a deferred run only needs to
        finish eventually, not stream regularly. Owns run-tracker cleanup,
        so use either wait_run or stream_run for a run, never both.

        Raises:
            GatewayTimeoutError: If the run doesn't complete within timeout
            AgentExecutionError: If agent execution fails
        """
        try:
            try:
                await asyncio.wait_for(
                    agent_run.complete_event.wait(), timeout=timeout
                )
            except asyncio.TimeoutError as err:
                raise GatewayTimeoutError("Agent response timeout") from err

            if agent_run.status == "ok":
                return agent_run.get_response()

            raise AgentExecutionError(
                f"Agent execution failed: {agent_run.summary}"
            )

        finally:
            self._agent_runs.pop(agent_run.run_id, None)

    async def stream_run(self, agent_run: AgentRun) -> AsyncIterator[str]:
        """Consume an already-started run: yield chunks, raise on failure.

        Exactly one consumer per run — this owns cleanup of the run tracker.

        Raises:
            GatewayTimeoutError: If the per-chunk timeout expires
            AgentExecutionError: If agent execution fails
        """
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
            self._agent_runs.pop(agent_run.run_id, None)

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
        try:
            agent_run = await self.begin_agent_run(message, idempotency_key)

            async for chunk in self.stream_run(agent_run):
                yield chunk

        except (GatewayConnectionError, GatewayTimeoutError):
            raise

        except AgentExecutionError:
            raise

        except Exception as err:
            _LOGGER.error(
                "Error in streaming agent request: %s", err, exc_info=True
            )
            raise AgentExecutionError(str(err)) from err

    @staticmethod
    def _buffer_agent_payload(agent_run: AgentRun, payload: dict[str, Any]) -> None:
        """Buffer assistant text from a Gateway agent payload."""
        data = payload.get("data", {})
        if not isinstance(data, dict):
            data = {}

        output = payload.get("output")
        if not output and "text" in data:
            output = data.get("text")
        if not output:
            result = payload.get("result")
            if isinstance(result, dict):
                for item in result.get("payloads", []):
                    if isinstance(item, dict) and item.get("text"):
                        output = item["text"]
                        break

        if output:
            agent_run.add_output(output)

    @staticmethod
    def _is_run_lifecycle_event(
        stream: str | None, data: dict[str, Any]
    ) -> bool:
        """Return True if a terminal phase on this event describes the run.

        The gateway emits agent events on several streams (``lifecycle``,
        ``assistant``, ``item``, ``tool``, ``command_output``, ``patch``, ...).
        Only the ``lifecycle`` stream's terminal phases (``end``/``error``)
        describe the run as a whole; the per-item streams emit their own ``end``
        phases for individual tool/command items and must not complete the run.

        Older gateways may omit the ``stream`` field. In that case fall back to
        the itemId heuristic: per-item terminal events carry a ``data.itemId``
        while the run-level terminal event does not.
        """
        if stream:
            return stream == "lifecycle"
        return not data.get("itemId")

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

        # Keep the proactive suppression window fresh while one of our own runs
        # is active, so its session-message echo is not re-announced.
        self._last_local_turn = time.monotonic()

        # Log event details for debugging
        data = payload.get("data", {})
        stream = payload.get("stream")
        _LOGGER.debug(
            "Agent event for %s: stream=%s, status=%s, output=%s, summary=%s, "
            "data keys=%s",
            run_id,
            stream,
            payload.get("status"),
            "yes" if payload.get("output") else "no",
            "yes" if payload.get("summary") else "no",
            list(data.keys()) if data else "none",
        )

        self._buffer_agent_payload(agent_run, payload)

        # Determine completion. The gateway multiplexes several streams under
        # the single "agent" event; only the run-level "lifecycle" stream's
        # terminal phases describe the run itself, so a terminal phase only
        # completes the run when it belongs to that stream.
        status = payload.get("status")
        phase = data.get("phase")
        run_terminal = self._is_run_lifecycle_event(stream, data)

        if status in ("ok", "error"):
            # Legacy completion signalled by a top-level status field.
            summary = payload.get("summary")
            agent_run.set_complete(status, summary)
            _LOGGER.info("Agent run %s completed with status: %s", run_id, status)
        elif phase == "error" and run_terminal:
            # Failed run: complete with error status so the request fails fast
            # instead of waiting for the client timeout.
            summary = data.get("error") or data.get("stopReason")
            agent_run.set_complete("error", summary)
            _LOGGER.warning(
                "Agent run %s failed (phase: error): %s", run_id, summary
            )
        elif phase in ("end", "complete") and run_terminal:
            agent_run.set_complete("ok", None)
            _LOGGER.info("Agent run %s completed (phase: %s)", run_id, phase)
        elif status:
            _LOGGER.debug("Agent run %s status: %s (not complete)", run_id, status)
        elif phase:
            _LOGGER.debug(
                "Agent run %s phase: %s (stream=%s, not run-terminal)",
                run_id,
                phase,
                stream,
            )

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

    # --- Proactive voice -------------------------------------------------

    def set_proactive_handler(self, callback: Callable[[str], None]) -> None:
        """Enable proactive announcements and subscribe to session messages.

        Subscribes immediately if already connected; otherwise the connect
        hook re-issues the subscription on (re)connect.
        """
        self._proactive_callback = callback
        if self._gateway.connected:
            self._schedule_subscribe()

    def clear_proactive_handler(self) -> None:
        """Disable proactive announcements."""
        self._proactive_callback = None

    def _on_gateway_connected(self) -> None:
        """Re-issue the session subscription after every (re)connect."""
        if self._proactive_callback is not None:
            self._schedule_subscribe()

    def _schedule_subscribe(self) -> None:
        asyncio.create_task(self._subscribe_session_messages())

    async def _subscribe_session_messages(self) -> None:
        """Subscribe to the watched session's message stream (operator.read)."""
        try:
            await self._gateway.send_request(
                "sessions.messages.subscribe",
                {"key": self._effective_session_key},
                timeout=5.0,
            )
            _LOGGER.debug(
                "Subscribed to session messages for %s",
                self._effective_session_key,
            )
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning(
                "Failed to subscribe to session messages: %s", err
            )

    @staticmethod
    def _extract_message_text(message: dict[str, Any]) -> str:
        """Extract plain text from a session.message payload's message."""
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
                elif isinstance(part, str):
                    parts.append(part)
            return "".join(parts).strip()
        text = message.get("text")
        return text.strip() if isinstance(text, str) else ""

    def _handle_session_message(self, event: dict[str, Any]) -> None:
        """Announce agent-initiated assistant turns via the proactive callback.

        Skips the echo of the user's own conversation turns: any assistant
        message arriving close to local agent activity (see _last_local_turn)
        was already spoken through the normal conversation pipeline.
        """
        if self._proactive_callback is None:
            return
        payload = event.get("payload", {})
        message = payload.get("message") or {}
        if not isinstance(message, dict) or message.get("role") != "assistant":
            return
        # A run we started (including one detached past the grace period) can
        # take arbitrarily long, so suppress while any local run is in flight,
        # plus a short tail after the last local activity to cover the gap
        # between run completion and its echo arriving.
        if self._agent_runs or (
            time.monotonic() - self._last_local_turn < PROACTIVE_SUPPRESS_SECONDS
        ):
            _LOGGER.debug(
                "Suppressing session message near a local turn (run echo)"
            )
            return
        text = self._extract_message_text(message)
        if not text:
            return
        _LOGGER.debug("Proactive assistant message detected (%d chars)", len(text))
        try:
            self._proactive_callback(text)
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Proactive callback failed")

    async def health(self) -> dict[str, Any]:
        """Get Gateway health status."""
        response = await self._gateway.send_request("health", timeout=5.0)
        return response.get("payload", {})

    async def status(self) -> dict[str, Any]:
        """Get Gateway status."""
        response = await self._gateway.send_request("status", timeout=5.0)
        return response.get("payload", {})
