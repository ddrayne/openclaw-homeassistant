"""Pragmatic tests for gateway_client behavior (HA-free)."""

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock

import pytest

_BASE = Path(__file__).parent.parent / "custom_components" / "clawd"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.modules.setdefault("custom_components", ModuleType("custom_components"))
sys.modules.setdefault("custom_components.clawd", ModuleType("custom_components.clawd"))

_const = _load_module("custom_components.clawd.const", _BASE / "const.py")
_exceptions = _load_module("custom_components.clawd.exceptions", _BASE / "exceptions.py")
_gateway = _load_module("custom_components.clawd.gateway", _BASE / "gateway.py")
_gateway_client = _load_module(
    "custom_components.clawd.gateway_client", _BASE / "gateway_client.py"
)

AgentExecutionError = _exceptions.AgentExecutionError
GatewayTimeoutError = _exceptions.GatewayTimeoutError
AgentRun = _gateway_client.AgentRun
ClawdGatewayClient = _gateway_client.ClawdGatewayClient


class TestAgentRun:
    def test_add_output_cumulative(self) -> None:
        run = AgentRun("run-1")
        run.add_output("Hello")
        run.add_output("Hello world")
        assert run.get_response() == "Hello world"


class TestHandleAgentEvent:
    def test_buffers_output_from_data_text(self) -> None:
        client = ClawdGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "data": {"text": "Hi"}}}
        )

        assert run.get_response() == "Hi"

    def test_marks_complete_with_summary(self) -> None:
        client = ClawdGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "status": "ok", "summary": "Done"}}
        )

        assert run.complete_event.is_set()
        assert run.status == "ok"
        assert run.get_response() == "Done"

    def test_marks_complete_on_phase_end(self) -> None:
        client = ClawdGatewayClient("localhost", 1, None)
        run = AgentRun("run-1")
        client._agent_runs["run-1"] = run

        client._handle_agent_event(
            {"payload": {"runId": "run-1", "data": {"phase": "end"}}}
        )

        assert run.complete_event.is_set()
        assert run.status == "ok"


class TestSendAgentRequest:
    @pytest.mark.asyncio
    async def test_missing_run_id_raises(self) -> None:
        client = ClawdGatewayClient("localhost", 1, None)
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {}}
        )

        with pytest.raises(AgentExecutionError):
            await client.send_agent_request("hello")

        assert client._agent_runs == {}

    @pytest.mark.asyncio
    async def test_timeout_raises_and_cleans_up(self) -> None:
        client = ClawdGatewayClient("localhost", 1, None, timeout=0)
        client._timeout = 0.01
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {"runId": "run-1"}}
        )

        with pytest.raises(GatewayTimeoutError):
            await client.send_agent_request("hello")

        assert client._agent_runs == {}

    @pytest.mark.asyncio
    async def test_success_returns_buffered_output(self) -> None:
        client = ClawdGatewayClient("localhost", 1, None)
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {"runId": "run-1"}}
        )

        task = asyncio.create_task(
            client.send_agent_request("hello", idempotency_key="fixed")
        )

        for _ in range(50):
            if "run-1" in client._agent_runs:
                break
            await asyncio.sleep(0)
        assert "run-1" in client._agent_runs

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

    @pytest.mark.asyncio
    async def test_status_error_raises(self) -> None:
        client = ClawdGatewayClient("localhost", 1, None)
        client._gateway.send_request = AsyncMock(  # type: ignore[attr-defined]
            return_value={"payload": {"runId": "run-1"}}
        )

        task = asyncio.create_task(client.send_agent_request("hello"))

        for _ in range(50):
            if "run-1" in client._agent_runs:
                break
            await asyncio.sleep(0)
        assert "run-1" in client._agent_runs

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
