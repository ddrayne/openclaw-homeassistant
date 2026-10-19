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
    async def test_final_summary_appends_missing_suffix(self) -> None:
        run = AgentRun("run-1", stream=True)
        run.add_delta("Home")
        run.set_complete("ok", "Home Assistant automatise la maison.")
        chunks = [chunk async for chunk in run.iter_stream(timeout=1.0)]
        assert chunks == ["Home", " Assistant automatise la maison."]
        assert "".join(chunks) == run.get_response()

    @pytest.mark.asyncio
    async def test_final_summary_replaces_nonprefix_content(self) -> None:
        run = AgentRun("run-1", stream=True)
        run.add_delta("Home")
        run.set_complete("ok", "La domotique contrôle la maison.")
        chunks = [chunk async for chunk in run.iter_stream(timeout=1.0)]
        assert chunks[0] == "Home"
        assert isinstance(chunks[1], _gateway_client.AgentTextReplacement)
        assert chunks[1].text == run.get_response()

    @pytest.mark.asyncio
    async def test_final_summary_equal_to_stream_not_duplicated(self) -> None:
        run = AgentRun("run-1", stream=True)
        run.add_delta("Home Assistant")
        run.set_complete("ok", "Home Assistant")
        assert [chunk async for chunk in run.iter_stream(timeout=1.0)] == ["Home Assistant"]

    @pytest.mark.asyncio
    async def test_empty_summary_preserves_buffered_reply(self) -> None:
        run = AgentRun("run-1", stream=True)
        run.add_delta("Home Assistant")
        run.set_complete("ok", "")
        assert run.get_response() == "Home Assistant"
        assert [chunk async for chunk in run.iter_stream(timeout=1.0)] == [
            "Home Assistant"
        ]

    @pytest.mark.asyncio
    async def test_no_final_summary_keeps_streamed_answer(self) -> None:
        run = AgentRun("run-1", stream=True)
        run.add_delta("Home")
        run.add_delta(" Assistant")
        run.set_complete("ok", None)
        assert [chunk async for chunk in run.iter_stream(timeout=1.0)] == [
            "Home", " Assistant"
        ]

    @pytest.mark.asyncio
    async def test_error_summary_not_streamed_as_content(self) -> None:
        # On error the summary is an internal diagnostic; it must not be
        # streamed as spoken content (which would also suppress the friendly
        # error fallback in the conversation entity).
        run = AgentRun("run-1", stream=True)
        run.set_complete("error", "stopReason: boom")
        chunks = [chunk async for chunk in run.iter_stream(timeout=1.0)]
        assert chunks == []


class TestModernAssistantEvents:
    def test_delta_after_initial_snapshot_builds_complete_response(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        client._handle_agent_event({
            "payload": {"runId": "run-1", "stream": "assistant",
                        "data": {"text": "Home", "delta": "Home"}}
        })
        client._handle_agent_event({
            "payload": {"runId": "run-1", "stream": "assistant",
                        "data": {"delta": " Assistant"}}
        })
        client._handle_agent_event({
            "payload": {"runId": "run-1", "stream": "assistant",
                        "data": {"delta": " automatise la maison."}}
        })
        assert run.get_response() == "Home Assistant automatise la maison."

    def test_authoritative_snapshot_already_includes_delta(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run
        for data in (
            {"text": "Hello", "delta": "Hello"},
            {"text": "Hello world", "delta": " world"},
            {"delta": "!"},
            {"text": "Hello world!", "delta": "!"},
        ):
            client._handle_agent_event({
                "payload": {"runId": "run-1", "stream": "assistant", "data": data}
            })
        assert run.get_response() == "Hello world!"

    def test_replace_and_empty_retract_on_non_streaming_run(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run
        def deliver(data):
            client._handle_agent_event({
                "payload": {"runId": "run-1", "stream": "assistant", "data": data}
            })
        deliver({"delta": "Draft"})
        deliver({"replace": True, "delta": "Corrected"})
        assert run.get_response() == "Corrected"
        deliver({"replace": True, "delta": ""})
        assert run.get_response() == ""
        deliver({"text": "Final"})
        assert run.get_response() == "Final"
        deliver({"replace": True, "text": ""})
        assert run.get_response() == ""

    def test_ignores_delta_from_tool_stream(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run
        client._handle_agent_event({
            "payload": {"runId": "run-1", "stream": "tool",
                        "data": {"delta": "secret tool output"}}
        })
        assert run.get_response() == ""

    @pytest.mark.asyncio
    async def test_streaming_yields_every_delta_once(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1", stream=True)
        client._agent_runs["run-1"] = run
        for data in (
            {"text": "Home", "delta": "Home"},
            {"delta": " Assistant"},
            {"text": "Home Assistant est libre", "delta": " est libre"},
            {"delta": "."},
        ):
            client._handle_agent_event({
                "payload": {"runId": "run-1", "stream": "assistant", "data": data}
            })
        client._handle_agent_event({
            "payload": {"runId": "run-1", "stream": "lifecycle",
                        "data": {"phase": "end"}}
        })
        chunks = [chunk async for chunk in client.stream_run(run)]
        assert chunks == ["Home", " Assistant", " est libre", "."]
        assert "".join(chunks) == "Home Assistant est libre."
        assert client._agent_runs == {}

    @pytest.mark.asyncio
    async def test_streamed_replacement_emits_corrected_message(self) -> None:
        run = AgentRun("run-1", stream=True)
        run.add_delta("Draft")
        run.replace_output("Corrected")
        run.set_complete("ok")
        chunks = [chunk async for chunk in run.iter_stream(timeout=1)]
        assert chunks[0] == "Draft"
        assert isinstance(chunks[1], _gateway_client.AgentTextReplacement)
        assert chunks[1].text == "Corrected"

class TestHandleAgentEvent:
    def test_result_payloads_reconcile_stream_and_include_all_messages(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1", stream=True)
        client._agent_runs["run-1"] = run

        client._handle_agent_event({
            "payload": {"runId": "run-1", "stream": "assistant",
                        "data": {"delta": "Home"}}
        })
        client._handle_agent_event({
            "payload": {"runId": "run-1", "result": {
                "payloads": [{"text": "Home Assistant"}, {"text": "Deuxième réponse."}]
            }}
        })
        assert run.get_response() == "Home Assistant\n\nDeuxième réponse."

    def test_item_scoped_snapshots_preserve_previous_items(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run
        for data in (
            {"itemId": "first", "text": "Hello", "delta": "Hello"},
            {"itemId": "first", "delta": " world"},
            {"itemId": "second", "text": "Second"},
            {"itemId": "second", "delta": " item"},
        ):
            client._handle_agent_event({
                "payload": {"runId": "run-1", "stream": "assistant", "data": data}
            })
        assert run.get_response() == "Hello world\n\nSecond item"

    def test_per_item_status_does_not_complete_run(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run
        client._handle_agent_event({
            "payload": {"runId": "run-1", "stream": "assistant",
                        "status": "ok", "data": {"itemId": "one"}}
        })
        assert not run.complete_event.is_set()

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
