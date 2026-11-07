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

    @pytest.mark.asyncio
    async def test_ok_summary_streamed_when_no_tokens(self) -> None:
        run = AgentRun("run-1", stream=True)
        run.set_complete("ok", "Final answer")
        chunks = [chunk async for chunk in run.iter_stream(timeout=1.0)]
        assert chunks == ["Final answer"]

    @pytest.mark.asyncio
    async def test_error_summary_not_streamed_as_content(self) -> None:
        # On error the summary is an internal diagnostic; it must not be
        # streamed as spoken content (which would also suppress the friendly
        # error fallback in the conversation entity).
        run = AgentRun("run-1", stream=True)
        run.set_complete("error", "stopReason: boom")
        chunks = [chunk async for chunk in run.iter_stream(timeout=1.0)]
        assert chunks == []


class TestHandleAgentEvent:
    def test_buffers_output_from_data_text(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "data": {"text": "Hi"}}}
        )

        assert run.get_response() == "Hi"

    def test_appends_delta_only_assistant_events(self) -> None:
        # Newer gateways send the text snapshot only on the first event.
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1", stream=True)
        client._agent_runs["run-1"] = run

        for data in (
            {"itemId": "a1", "text": "It's sunny and", "delta": "It's sunny and"},
            {"itemId": "a1", "delta": " seventy-two"},
            {"itemId": "a1", "delta": " degrees."},
        ):
            client._handle_agent_event(
                {"payload": {"runId": "run-1", "stream": "assistant", "data": data}}
            )

        assert run.get_response() == "It's sunny and seventy-two degrees."
        queued = []
        while not run._stream_queue.empty():
            queued.append(run._stream_queue.get_nowait())
        assert queued == ["It's sunny and", " seventy-two", " degrees."]

    def test_replays_captured_gateway_delta_sequence(self) -> None:
        # Event sequence captured from a live gateway 2026.10.4 where Voice PE
        # spoke only "He": the snapshot arrives once, then deltas only (#16).
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        for data in (
            {"text": "He", "delta": "He", "itemId": "i"},
            {"delta": "ute leichter Regen,", "itemId": "i"},
            {"delta": " vierzehn Grad.", "itemId": "i"},
        ):
            client._handle_agent_event(
                {"payload": {"runId": "run-1", "stream": "assistant", "data": data}}
            )

        assert run.get_response() == "Heute leichter Regen, vierzehn Grad."

    @pytest.mark.asyncio
    async def test_iter_stream_yields_delta_only_chunks(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1", stream=True)
        client._agent_runs["run-1"] = run

        for data in ({"text": "He", "delta": "He"}, {"delta": "llo"}):
            client._handle_agent_event(
                {"payload": {"runId": "run-1", "stream": "assistant", "data": data}}
            )
        run.set_complete("ok", None)

        chunks = [chunk async for chunk in run.iter_stream(timeout=1.0)]
        assert chunks == ["He", "llo"]

    def test_delta_for_new_item_starts_its_text(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        for data in (
            {"itemId": "a1", "text": "Checking.", "delta": "Checking."},
            {"itemId": "a2", "delta": "All"},
            {"itemId": "a2", "delta": " done."},
        ):
            client._handle_agent_event(
                {"payload": {"runId": "run-1", "stream": "assistant", "data": data}}
            )

        assert run.get_response() == "All done."

    @pytest.mark.asyncio
    async def test_streamed_items_are_separated(self, caplog) -> None:
        """A second item (the answer after a tool call) must not be glued on."""
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1", stream=True)
        client._agent_runs["run-1"] = run

        with caplog.at_level("WARNING"):
            for data in (
                {"itemId": "a1", "text": "Let me check.", "delta": "Let me check."},
                {"itemId": "a2", "text": "It's", "delta": "It's"},
                {"itemId": "a2", "delta": " 72 degrees."},
            ):
                client._handle_agent_event(
                    {"payload": {"runId": "run-1", "stream": "assistant", "data": data}}
                )
        run.set_complete("ok", None)

        chunks = [chunk async for chunk in run.iter_stream(timeout=1.0)]
        assert chunks == ["Let me check.", "\n\nIt's", " 72 degrees."]
        # The buffered (non-streaming) reply is still the final item only.
        assert run.get_response() == "It's 72 degrees."
        # Routine item boundaries are not warnings.
        assert caplog.records == []

    @pytest.mark.asyncio
    async def test_delta_only_new_item_is_separated_when_streamed(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1", stream=True)
        client._agent_runs["run-1"] = run

        for data in (
            {"itemId": "a1", "text": "Checking.", "delta": "Checking."},
            {"itemId": "a2", "delta": "All"},
            {"itemId": "a2", "delta": " done."},
        ):
            client._handle_agent_event(
                {"payload": {"runId": "run-1", "stream": "assistant", "data": data}}
            )
        run.set_complete("ok", None)

        chunks = [chunk async for chunk in run.iter_stream(timeout=1.0)]
        assert chunks == ["Checking.", "\n\nAll", " done."]

    def test_existing_whitespace_is_not_doubled(self) -> None:
        run = AgentRun("run-1", stream=True)
        run.add_output("Checking. ")
        run.add_output("All done.")

        queued = []
        while not run._stream_queue.empty():
            queued.append(run._stream_queue.get_nowait())
        assert queued == ["Checking. ", "All done."]

    def test_ignores_delta_from_non_assistant_stream(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "stream": "assistant", "data": {"text": "Hi"}}}
        )
        client._handle_agent_event(
            {"payload": {"runId": "run-1", "stream": "thinking", "data": {"delta": "hmm"}}}
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

    def test_lifecycle_stream_end_completes_run(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        client._handle_agent_event(
            {
                "payload": {
                    "runId": "run-1",
                    "stream": "lifecycle",
                    "data": {"phase": "end"},
                }
            }
        )

        assert run.complete_event.is_set()
        assert run.status == "ok"

    def test_item_stream_end_does_not_complete_run(self) -> None:
        # Even without an itemId, a terminal phase on a non-lifecycle stream
        # must not complete the run.
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        client._handle_agent_event(
            {
                "payload": {
                    "runId": "run-1",
                    "stream": "item",
                    "data": {"phase": "end"},
                }
            }
        )

        assert not run.complete_event.is_set()
        assert run.status is None

    def test_lifecycle_error_phase_marks_run_failed(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        client._handle_agent_event(
            {
                "payload": {
                    "runId": "run-1",
                    "stream": "lifecycle",
                    "data": {"phase": "error", "error": "boom"},
                }
            }
        )

        assert run.complete_event.is_set()
        assert run.status == "error"
        assert run.summary == "boom"

    @pytest.mark.asyncio
    async def test_error_phase_fails_request_fast(self) -> None:
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
                    "stream": "lifecycle",
                    "data": {"phase": "error", "error": "kaboom"},
                }
            }
        )

        with pytest.raises(AgentExecutionError):
            await task

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

        params = client._gateway.send_request.call_args_list[-1].kwargs["params"]  # type: ignore[attr-defined]
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
    async def test_gateway_default_agent_prefixes_session_key(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None, session_key="chat")
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            side_effect=[
                {"payload": {"defaultId": "main"}},
                {"payload": {"runId": "run-1"}},
            ]
        )

        task = asyncio.create_task(client.send_agent_request("hello"))

        await _wait_for_run(client)

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "status": "ok", "summary": "done"}}
        )

        await task

        calls = client._gateway.send_request.call_args_list  # type: ignore[attr-defined]
        assert calls[0].args == ("agents.list",)
        assert calls[1].kwargs["params"]["sessionKey"] == "agent:main:chat"

    @pytest.mark.asyncio
    async def test_missing_gateway_default_keeps_plain_session_key(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None, session_key="chat")
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            side_effect=[
                {"payload": {}},
                {"payload": {"runId": "run-1"}},
            ]
        )

        task = asyncio.create_task(client.send_agent_request("hello"))

        await _wait_for_run(client)

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "status": "ok", "summary": "done"}}
        )

        await task

        calls = client._gateway.send_request.call_args_list  # type: ignore[attr-defined]
        assert calls[1].kwargs["params"]["sessionKey"] == "chat"

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

        params = client._gateway.send_request.call_args_list[-1].kwargs["params"]  # type: ignore[attr-defined]
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

    @pytest.mark.asyncio
    async def test_connect_names_upgrade_auth_rejection(self) -> None:
        """A 401/403 on the upgrade is reported instead of "may not be reachable"."""
        client = OpenClawGatewayClient("localhost", 1, "tok")
        client._gateway._upgrade_auth_status = 403
        client._gateway.connect = AsyncMock()  # type: ignore[attr-defined]

        with pytest.raises(
            _exceptions.GatewayUpgradeRejectedError, match="HTTP 403"
        ) as info:
            await client.connect()

        assert info.value.status_code == 403
        # Still a connection error, so existing handlers keep treating it as
        # retryable.
        assert isinstance(info.value, GatewayConnectionError)

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


class TestAgentScope:
    @pytest.mark.asyncio
    async def test_gateway_default_scopes_proactive_subscription(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None, session_key="voice")
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            side_effect=[
                {"payload": {"defaultId": "main"}},
                {"payload": {}},
            ]
        )

        await client._subscribe_session_messages()

        calls = client._gateway.send_request.call_args_list  # type: ignore[attr-defined]
        assert calls[0].args == ("agents.list",)
        assert calls[1].args == (
            "sessions.messages.subscribe",
            {"key": "agent:main:voice"},
        )

    def test_reconnect_invalidates_resolved_gateway_default(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        client._resolved_agent_id = "main"

        client._on_gateway_connected()

        assert client._resolved_agent_id is None


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


class TestEarlyAgentEvents:
    """The Gateway may publish text and terminal events before its agent RPC ack."""

    @pytest.mark.asyncio
    async def test_events_in_same_read_as_ack_are_not_lost(self) -> None:
        """The ack and the run's first events can arrive in one websocket read.

        The receive loop then handles them back to back. Resolving the ack's
        future only *schedules* the waiting request, so without buffering the
        events are dispatched before the run is registered and dropped, and
        the request waits for a completion that already happened.
        """
        client = OpenClawGatewayClient(
            "localhost", 1, None, agent_id="main", timeout=1.0
        )
        gateway = client._gateway
        sent = asyncio.Event()

        async def send_request(**_kwargs):
            future = asyncio.get_running_loop().create_future()
            gateway._pending_requests["req-1"] = future
            sent.set()
            return await future

        gateway.send_request = send_request
        request = asyncio.create_task(client.send_agent_request("hi"))
        await sent.wait()

        for message in (
            {
                "type": "res",
                "id": "req-1",
                "ok": True,
                "payload": {"runId": "r1", "status": "accepted"},
            },
            {
                "type": "event",
                "event": "agent",
                "payload": {
                    "runId": "r1",
                    "stream": "assistant",
                    "data": {"text": "Hello there", "delta": "Hello there"},
                },
            },
            {
                "type": "event",
                "event": "agent",
                "payload": {
                    "runId": "r1",
                    "stream": "lifecycle",
                    "data": {"phase": "end"},
                },
            },
        ):
            await gateway._handle_message(message)

        assert await asyncio.wait_for(request, 2) == "Hello there"
        assert client._early_agent_events == {}

    @pytest.mark.asyncio
    async def test_fast_run_finishes_before_ack(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None, agent_id="main")

        async def send_before_ack(*_args, **_kwargs):
            client._handle_agent_event(
                {"payload": {"runId": "fast-run", "output": "Finished"}}
            )
            client._handle_agent_event(
                {
                    "payload": {
                        "runId": "fast-run",
                        "stream": "lifecycle",
                        "data": {"phase": "end"},
                    }
                }
            )
            return {"payload": {"runId": "fast-run"}}

        client._gateway.send_request = AsyncMock(side_effect=send_before_ack)
        result = await asyncio.wait_for(client.send_agent_request("hello"), 1.0)
        assert result == "Finished"
        assert client._agent_runs == {}
        assert client._early_agent_events == {}
        assert client._pending_agent_starts == 0

    @pytest.mark.asyncio
    async def test_fast_stream_replays_chunks_and_terminal_event(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None, agent_id="main")

        async def send_before_ack(*_args, **_kwargs):
            for output in ("Hello", "Hello world"):
                client._handle_agent_event(
                    {"payload": {"runId": "fast-stream", "output": output}}
                )
            client._handle_agent_event(
                {
                    "payload": {
                        "runId": "fast-stream",
                        "stream": "lifecycle",
                        "data": {"phase": "end"},
                    }
                }
            )
            return {"payload": {"runId": "fast-stream"}}

        client._gateway.send_request = AsyncMock(side_effect=send_before_ack)
        chunks = [
            chunk async for chunk in client.stream_agent_request("hello")
        ]
        assert chunks == ["Hello", " world"]
        assert client._agent_runs == {}
        assert client._early_agent_events == {}

    def test_orphans_are_not_cached_without_pending_start(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        client._handle_agent_event(
            {"payload": {"runId": "unrelated", "status": "ok"}}
        )
        assert client._early_agent_events == {}


class TestStreamRunUntilQuiet:
    @pytest.mark.asyncio
    async def test_quiet_run_stays_tracked_for_wait_run(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1", stream=True)
        client._agent_runs["run-1"] = run
        run.add_output("Let me check.")

        chunks = []
        with pytest.raises(_gateway_client.AgentRunQuiet):
            async for chunk in client.stream_run_until_quiet(run, 0.05):
                chunks.append(chunk)

        assert chunks == ["Let me check."]
        # Still tracked: the background consumer finishes it with wait_run.
        assert client._agent_runs == {"run-1": run}

        run.add_output("Let me check. All clear.")
        run.set_complete("ok", None)
        assert await client.wait_run(run, 1.0) == "Let me check. All clear."
        assert client._agent_runs == {}

    @pytest.mark.asyncio
    async def test_completed_run_is_cleaned_up(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1", stream=True)
        client._agent_runs["run-1"] = run
        run.add_output("Hi")
        run.set_complete("ok", None)

        chunks = [c async for c in client.stream_run_until_quiet(run, 1.0)]

        assert chunks == ["Hi"]
        assert client._agent_runs == {}

    @pytest.mark.asyncio
    async def test_failed_run_raises_and_is_cleaned_up(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1", stream=True)
        client._agent_runs["run-1"] = run
        run.set_complete("error", "boom")

        with pytest.raises(AgentExecutionError, match="boom"):
            async for _chunk in client.stream_run_until_quiet(run, 1.0):
                pass
        assert client._agent_runs == {}
