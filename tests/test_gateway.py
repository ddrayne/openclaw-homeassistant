"""Pragmatic tests for gateway protocol behavior (HA-free)."""

import asyncio
import importlib.util
import json
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

GatewayAuthenticationError = _exceptions.GatewayAuthenticationError
GatewayConnectionError = _exceptions.GatewayConnectionError
ProtocolError = _exceptions.ProtocolError
GatewayProtocol = _gateway.GatewayProtocol


class DummyWebSocket:
    def __init__(self, responses):
        self.sent = []
        self._responses = responses
        self._index = 0
        self._sent_event = asyncio.Event()

    async def send(self, data: str) -> None:
        self.sent.append(json.loads(data))
        self._sent_event.set()

    async def recv(self) -> str:
        if not self.sent:
            await self._sent_event.wait()
        if self._index >= len(self._responses):
            raise AssertionError("No more responses configured")
        item = self._responses[self._index]
        self._index += 1
        if callable(item):
            item = item(self.sent)
        return json.dumps(item)


class TestSendRequest:
    @pytest.mark.asyncio
    async def test_not_connected_raises(self) -> None:
        protocol = GatewayProtocol("localhost", 1, None)
        with pytest.raises(GatewayConnectionError):
            await protocol.send_request("status")

    @pytest.mark.asyncio
    async def test_timeout_cleans_pending(self, monkeypatch) -> None:
        async def fake_wait_for(_future, timeout=None):
            raise asyncio.TimeoutError

        import custom_components.clawd.gateway as gateway_module

        monkeypatch.setattr(gateway_module.asyncio, "wait_for", fake_wait_for)

        protocol = GatewayProtocol("localhost", 1, None)
        protocol._connected = True
        protocol._websocket = AsyncMock()

        with pytest.raises(GatewayConnectionError):
            await protocol.send_request("status", timeout=0.01)

        assert protocol._pending_requests == {}


class TestMessageHandling:
    @pytest.mark.asyncio
    async def test_response_resolves_future(self) -> None:
        protocol = GatewayProtocol("localhost", 1, None)
        future = asyncio.Future()
        protocol._pending_requests["req-1"] = future
        message = {"type": "res", "id": "req-1", "ok": True, "payload": {}}

        await protocol._handle_message(message)

        assert future.done()
        assert future.result() == message

    @pytest.mark.asyncio
    async def test_event_dispatches_handler(self) -> None:
        protocol = GatewayProtocol("localhost", 1, None)
        seen = []

        def handler(event):
            seen.append(event)

        protocol.on_event("agent", handler)
        await protocol._handle_message({"type": "event", "event": "agent"})

        assert len(seen) == 1


class TestHandshake:
    @pytest.mark.asyncio
    async def test_auth_error_raises(self) -> None:
        def response(sent):
            return {
                "type": "res",
                "id": sent[-1]["id"],
                "ok": False,
                "error": "Invalid token",
            }

        protocol = GatewayProtocol("localhost", 1, "token")
        protocol._websocket = DummyWebSocket([response])

        with pytest.raises(GatewayAuthenticationError):
            await protocol._handshake()

    @pytest.mark.asyncio
    async def test_protocol_error_raises(self) -> None:
        def response(sent):
            return {
                "type": "res",
                "id": sent[-1]["id"],
                "ok": False,
                "error": "Bad request",
            }

        protocol = GatewayProtocol("localhost", 1, None)
        protocol._websocket = DummyWebSocket([response])

        with pytest.raises(ProtocolError):
            await protocol._handshake()

    @pytest.mark.asyncio
    async def test_skips_event_before_response(self) -> None:
        def response(sent):
            return {
                "type": "res",
                "id": sent[-1]["id"],
                "ok": True,
                "payload": {},
            }

        protocol = GatewayProtocol("localhost", 1, None)
        protocol._websocket = DummyWebSocket(
            [{"type": "event", "event": "agent"}, response]
        )

        await protocol._handshake()

        assert protocol._websocket.sent[0]["method"] == "connect"
