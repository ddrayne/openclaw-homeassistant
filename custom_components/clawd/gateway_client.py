"""High-level Clawdbot Gateway API client."""

import asyncio
import logging
import uuid
from typing import Any

from .exceptions import (
    AgentExecutionError,
    GatewayTimeoutError,
)
from .gateway import GatewayProtocol

_LOGGER = logging.getLogger(__name__)


class AgentRun:
    """Tracks an agent run and buffers its events."""

    def __init__(self, run_id: str) -> None:
        """Initialize agent run tracker."""
        self.run_id = run_id
        self.output_parts: list[str] = []
        self.status: str | None = None
        self.summary: str | None = None
        self.complete_event = asyncio.Event()

    def add_output(self, output: str) -> None:
        """Add output to buffer."""
        if output:
            self.output_parts.append(output)

    def set_complete(self, status: str, summary: str | None = None) -> None:
        """Mark run as complete."""
        self.status = status
        self.summary = summary
        self.complete_event.set()

    def get_response(self) -> str:
        """Get assembled response."""
        if self.summary:
            return self.summary
        if self.output_parts:
            return "".join(self.output_parts)
        return ""


class ClawdGatewayClient:
    """High-level Gateway API client with event buffering."""

    def __init__(
        self,
        host: str,
        port: int,
        token: str | None,
        use_ssl: bool = False,
        timeout: int = 30,
    ) -> None:
        """Initialize the Gateway client."""
        self._gateway = GatewayProtocol(host, port, token, use_ssl)
        self._timeout = timeout
        self._agent_runs: dict[str, AgentRun] = {}

        # Register event handler
        self._gateway.on_event("agent", self._handle_agent_event)

    async def connect(self) -> None:
        """Connect to Gateway."""
        await self._gateway.connect()

        # Wait for connection to be established (event-based, no polling)
        try:
            await asyncio.wait_for(
                self._gateway._connected_event.wait(), timeout=5.0
            )
        except asyncio.TimeoutError:
            _LOGGER.warning("Connection timeout - Gateway may not be reachable")

    async def disconnect(self) -> None:
        """Disconnect from Gateway."""
        await self._gateway.disconnect()

    @property
    def connected(self) -> bool:
        """Return whether connected to Gateway."""
        return self._gateway.connected

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
            response = await self._gateway.send_request(
                method="agent",
                params={
                    "message": message,
                    "idempotencyKey": idempotency_key,
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

        except GatewayTimeoutError:
            raise

        except AgentExecutionError:
            raise

        except Exception as err:
            _LOGGER.error(
                "Error in agent request: %s", err, exc_info=True
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

        # Buffer output
        output = payload.get("output")
        if output:
            agent_run.add_output(output)

        # Check for completion
        status = payload.get("status")
        if status in ("ok", "error"):
            summary = payload.get("summary")
            agent_run.set_complete(status, summary)
            _LOGGER.debug("Agent run %s completed with status: %s", run_id, status)

    async def health(self) -> dict[str, Any]:
        """Get Gateway health status."""
        response = await self._gateway.send_request("health", timeout=5.0)
        return response.get("payload", {})

    async def status(self) -> dict[str, Any]:
        """Get Gateway status."""
        response = await self._gateway.send_request("status", timeout=5.0)
        return response.get("payload", {})
