"""Pragmatic tests for gateway_client behavior (HA-free)."""

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock

import pytest

_BASE = Path(__file__).parent.parent / "custom_components" / "openclaw"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.modules.setdefault("custom_components", ModuleType("custom_components"))
sys.modules.setdefault("custom_components.openclaw", ModuleType("custom_components.openclaw"))

_const = _load_module("custom_components.openclaw.const", _BASE / "const.py")
_exceptions = _load_module("custom_components.openclaw.exceptions", _BASE / "exceptions.py")
_device_auth = _load_module("custom_components.openclaw.device_auth", _BASE / "device_auth.py")
_gateway = _load_module("custom_components.openclaw.gateway", _BASE / "gateway.py")
_gateway_client = _load_module(
    "custom_components.openclaw.gateway_client", _BASE / "gateway_client.py"
)

AgentExecutionError = _exceptions.AgentExecutionError
DevicePairingRequiredError = _exceptions.DevicePairingRequiredError
GatewayAuthenticationError = _exceptions.GatewayAuthenticationError
GatewayConnectionError = _exceptions.GatewayConnectionError
GatewayTimeoutError = _exceptions.GatewayTimeoutError
ProtocolError = _exceptions.ProtocolError
AgentRun = _gateway_client.AgentRun
OpenClawGatewayClient = _gateway_client.OpenClawGatewayClient


async def _wait_for_run(client: OpenClawGatewayClient, run_id: str = "run-1") -> None:
    """Spin until the agent run tracker appears."""
    for _ in range(50):
        if run_id in client._agent_runs:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"{run_id} not found in _agent_runs")


class TestAgentRun:
    def test_add_output_cumulative(self) -> None:
        run = AgentRun("run-1")
        run.add_output("Hello")
        run.add_output("Hello world")
        assert run.get_response() == "Hello world"

    def test_add_output_ignores_structural_payload_after_text(self) -> None:
        run = AgentRun("run-1")
        run.add_output("Done")
        run.add_output("[]")
        assert run.get_response() == "Done"


class TestHandleAgentEvent:
    def test_buffers_output_from_data_text(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "data": {"text": "Hi"}}}
        )

        assert run.get_response() == "Hi"

    def test_buffers_output_from_result_payload_text(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        client._handle_agent_event(
            {
                "payload": {
                    "runId": "run-1",
                    "result": {"payloads": [{"text": "Action complete"}]},
                }
            }
        )

        assert run.get_response() == "Action complete"

    def test_marks_complete_with_summary(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "status": "ok", "summary": "Done"}}
        )

        assert run.complete_event.is_set()
        assert run.status == "ok"
        assert run.get_response() == "Done"

    def test_marks_complete_on_phase_end(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "data": {"phase": "end"}}}
        )

        assert run.complete_event.is_set()
        assert run.status == "ok"

    def test_item_phase_end_does_not_complete_run(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        client._handle_agent_event(
            {
                "payload": {
                    "runId": "run-1",
                    "data": {"phase": "end", "itemId": "tool-1"},
                }
            }
        )

        assert not run.complete_event.is_set()
        assert run.status is None

    @pytest.mark.asyncio
    async def test_initial_ack_payload_text_can_complete_request(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={
                "payload": {
                    "runId": "run-1",
                    "result": {"payloads": [{"text": "Done from ack"}]},
                }
            }
        )

        task = asyncio.create_task(client.send_agent_request("hello"))

        await _wait_for_run(client)

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "status": "ok"}}
        )

        result = await task
        assert result == "Done from ack"


class TestSendAgentRequest:
    @pytest.mark.asyncio
    async def test_connection_error_propagates(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            side_effect=GatewayConnectionError("Not connected to Gateway"),
        )

        with pytest.raises(GatewayConnectionError):
            await client.send_agent_request("hello")

    @pytest.mark.asyncio
    async def test_missing_run_id_raises(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {}}
        )

        with pytest.raises(AgentExecutionError):
            await client.send_agent_request("hello")

        assert client._agent_runs == {}

    @pytest.mark.asyncio
    async def test_timeout_raises_and_cleans_up(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None, timeout=0)
        client._timeout = 0.01
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {"runId": "run-1"}}
        )

        with pytest.raises(GatewayTimeoutError):
            await client.send_agent_request("hello")

        assert client._agent_runs == {}

    @pytest.mark.asyncio
    async def test_success_returns_buffered_output(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {"runId": "run-1"}}
        )

        task = asyncio.create_task(
            client.send_agent_request("hello", idempotency_key="fixed")
        )

        await _wait_for_run(client)

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "output": "Hi there"}}
        )
        client._handle_agent_event(
            {"payload": {"runId": "run-1", "status": "ok"}}
        )

        result = await task
        assert result == "Hi there"
        assert client._agent_runs == {}

        client._gateway.send_request.assert_called_once()  # type: ignore[attr-defined]
        params = client._gateway.send_request.call_args.kwargs["params"]  # type: ignore[attr-defined]
        assert params["idempotencyKey"] == "fixed"
        assert "options" not in params
        assert params["sessionKey"] == "main"

    @pytest.mark.asyncio
    async def test_agent_id_prefixes_session_key(self) -> None:
        client = OpenClawGatewayClient(
            "localhost", 1, None, agent_id="my-agent", session_key="chat"
        )
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {"runId": "run-1"}}
        )

        task = asyncio.create_task(client.send_agent_request("hello"))

        await _wait_for_run(client)

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "status": "ok", "summary": "done"}}
        )

        await task

        params = client._gateway.send_request.call_args.kwargs["params"]  # type: ignore[attr-defined]
        assert params["sessionKey"] == "agent:my-agent:chat"

    @pytest.mark.asyncio
    async def test_no_agent_id_keeps_plain_session_key(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None, session_key="chat")
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {"runId": "run-1"}}
        )

        task = asyncio.create_task(client.send_agent_request("hello"))

        await _wait_for_run(client)

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "status": "ok", "summary": "done"}}
        )

        await task

        params = client._gateway.send_request.call_args.kwargs["params"]  # type: ignore[attr-defined]
        assert params["sessionKey"] == "chat"

    @pytest.mark.asyncio
    async def test_thinking_sent_as_root_param(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None, thinking="high")
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {"runId": "run-1"}}
        )

        task = asyncio.create_task(client.send_agent_request("hello"))

        await _wait_for_run(client)

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "status": "ok", "summary": "done"}}
        )

        result = await task
        assert result == "done"

        params = client._gateway.send_request.call_args.kwargs["params"]  # type: ignore[attr-defined]
        assert params["thinking"] == "high"
        assert "options" not in params

    @pytest.mark.asyncio
    async def test_model_and_thinking_sent_as_root_params(self) -> None:
        client = OpenClawGatewayClient(
            "localhost",
            1,
            None,
            model="anthropic/claude-sonnet-4-5",
            thinking="medium",
        )
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {"runId": "run-1"}}
        )

        task = asyncio.create_task(client.send_agent_request("hello"))

        await _wait_for_run(client)

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "status": "ok", "summary": "done"}}
        )

        result = await task
        assert result == "done"

        params = client._gateway.send_request.call_args.kwargs["params"]  # type: ignore[attr-defined]
        assert params["model"] == "anthropic/claude-sonnet-4-5"
        assert params["thinking"] == "medium"
        assert "options" not in params

    @pytest.mark.asyncio
    async def test_status_error_raises(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {"runId": "run-1"}}
        )

        task = asyncio.create_task(client.send_agent_request("hello"))

        await _wait_for_run(client)

        client._handle_agent_event(
            {
                "payload": {
                    "runId": "run-1",
                    "status": "error",
                    "summary": "boom",
                }
            }
        )

        with pytest.raises(AgentExecutionError):
            await task

        assert client._agent_runs == {}


class TestStreamAgentRequest:
    @pytest.mark.asyncio
    async def test_connection_error_propagates(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            side_effect=GatewayConnectionError("Not connected to Gateway"),
        )

        async def consume():
            async for _ in client.stream_agent_request("hello"):
                pass

        with pytest.raises(GatewayConnectionError):
            await consume()

    @pytest.mark.asyncio
    async def test_streams_chunks_and_cleans_up(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {"runId": "run-1"}}
        )

        chunks: list[str] = []

        async def consume():
            async for chunk in client.stream_agent_request(
                "hello", idempotency_key="fixed"
            ):
                chunks.append(chunk)

        task = asyncio.create_task(consume())

        await _wait_for_run(client)

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "output": "Hi"}}
        )
        client._handle_agent_event(
            {"payload": {"runId": "run-1", "output": "Hi there"}}
        )
        client._handle_agent_event(
            {"payload": {"runId": "run-1", "status": "ok"}}
        )

        await task
        assert chunks == ["Hi", " there"]
        assert client._agent_runs == {}

        client._gateway.send_request.assert_called_once()  # type: ignore[attr-defined]
        params = client._gateway.send_request.call_args.kwargs["params"]  # type: ignore[attr-defined]
        assert params["idempotencyKey"] == "fixed"
        assert "options" not in params

    @pytest.mark.asyncio
    async def test_stream_thinking_sent_as_root_param(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None, thinking="medium")
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {"runId": "run-1"}}
        )

        chunks: list[str] = []

        async def consume():
            async for chunk in client.stream_agent_request("hello"):
                chunks.append(chunk)

        task = asyncio.create_task(consume())

        await _wait_for_run(client)

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "output": "done"}}
        )
        client._handle_agent_event(
            {"payload": {"runId": "run-1", "status": "ok"}}
        )
        await task
        assert chunks == ["done"]

        params = client._gateway.send_request.call_args.kwargs["params"]  # type: ignore[attr-defined]
        assert params["thinking"] == "medium"
        assert "options" not in params

    @pytest.mark.asyncio
    async def test_stream_model_and_thinking_sent_as_root_params(self) -> None:
        client = OpenClawGatewayClient(
            "localhost",
            1,
            None,
            model="anthropic/claude-opus-4-5",
            thinking="low",
        )
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {"runId": "run-1"}}
        )

        chunks: list[str] = []

        async def consume():
            async for chunk in client.stream_agent_request("hello"):
                chunks.append(chunk)

        task = asyncio.create_task(consume())

        await _wait_for_run(client)

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "output": "done"}}
        )
        client._handle_agent_event(
            {"payload": {"runId": "run-1", "status": "ok"}}
        )
        await task
        assert chunks == ["done"]

        params = client._gateway.send_request.call_args.kwargs["params"]  # type: ignore[attr-defined]
        assert params["model"] == "anthropic/claude-opus-4-5"
        assert params["thinking"] == "low"
        assert "options" not in params

    @pytest.mark.asyncio
    async def test_stream_timeout_raises_and_cleans_up(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None, timeout=0)
        client._timeout = 0.01
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {"runId": "run-1"}}
        )

        async def consume():
            async for _ in client.stream_agent_request("hello"):
                pass

        with pytest.raises(GatewayTimeoutError):
            await consume()

        assert client._agent_runs == {}


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_raises_on_auth_error(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, "bad-token")
        auth_err = GatewayAuthenticationError("bad token")
        client._gateway._fatal_error = auth_err
        client._gateway.connect = AsyncMock()  # type: ignore[attr-defined]
        # _connected_event never set, so wait_for will time out

        with pytest.raises(GatewayAuthenticationError):
            await client.connect()

    @pytest.mark.asyncio
    async def test_connect_raises_on_pairing_error(self) -> None:
        """DevicePairingRequiredError propagates through connect()."""
        client = OpenClawGatewayClient("localhost", 1, "tok")
        pairing_err = DevicePairingRequiredError("not paired")
        client._gateway._fatal_error = pairing_err
        client._gateway.connect = AsyncMock()  # type: ignore[attr-defined]

        with pytest.raises(DevicePairingRequiredError):
            await client.connect()

    @pytest.mark.asyncio
    async def test_connect_raises_on_protocol_error(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        client._gateway._fatal_error = ProtocolError("version mismatch")
        client._gateway.connect = AsyncMock()  # type: ignore[attr-defined]

        with pytest.raises(GatewayConnectionError, match="version mismatch"):
            await client.connect()

    @pytest.mark.asyncio
    async def test_connect_raises_timeout_when_no_fatal_error(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        client._gateway.connect = AsyncMock()  # type: ignore[attr-defined]
        # No fatal error, event never set

        with pytest.raises(GatewayConnectionError, match="Connection timeout"):
            await client.connect()

    def test_fatal_error_property(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        assert client.fatal_error is None

        err = GatewayAuthenticationError("bad token")
        client._gateway._fatal_error = err
        assert client.fatal_error is err


class TestConnectSnapshot:
    def test_passthrough_property(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        client._gateway._connect_snapshot = {"snapshot": {"uptimeMs": 500}}
        assert client.connect_snapshot == {"snapshot": {"uptimeMs": 500}}

    def test_defaults_empty(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        assert client.connect_snapshot == {}


class TestPresence:
    def test_passthrough_property(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        client._gateway._presence = {"clients": ["a", "b"]}
        assert client.presence == {"clients": ["a", "b"]}

    def test_event_updates_state(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        assert client.presence == {}

        client._handle_presence_event(
            {"payload": {"clients": ["ha-client"]}}
        )

        assert client.presence == {"clients": ["ha-client"]}

    def test_event_with_empty_payload_ignored(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        client._gateway._presence = {"clients": ["existing"]}

        client._handle_presence_event({"payload": {}})

        assert client.presence == {"clients": ["existing"]}
