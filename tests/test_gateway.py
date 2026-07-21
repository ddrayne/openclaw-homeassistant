"""Pragmatic tests for gateway protocol behavior (HA-free)."""

import asyncio
import importlib.util
import json
import logging
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
_device_auth = _load_module(
    "custom_components.openclaw.device_auth", _BASE / "device_auth.py"
)
_gateway = _load_module("custom_components.openclaw.gateway", _BASE / "gateway.py")

DevicePairingRequiredError = _exceptions.DevicePairingRequiredError
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
        if self._index >= len(self._responses):
            raise AssertionError("No more responses configured")
        item = self._responses[self._index]
        # Only wait for a client send if the response needs it (callable)
        if callable(item) and not self.sent:
            await self._sent_event.wait()
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

        import custom_components.openclaw.gateway as gateway_module

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

    @pytest.mark.asyncio
    async def test_ping_sends_pong(self) -> None:
        protocol = GatewayProtocol("localhost", 1, None)
        protocol._websocket = AsyncMock()

        await protocol._handle_message({"type": "ping"})

        protocol._websocket.send.assert_awaited_once()
        payload = json.loads(protocol._websocket.send.call_args.args[0])
        assert payload == {"type": "pong"}

    @pytest.mark.asyncio
    async def test_pong_updates_timestamp(self) -> None:
        protocol = GatewayProtocol("localhost", 1, None)
        protocol._last_pong = 0.0

        await protocol._handle_message({"type": "pong"})

        assert protocol._last_pong > 0.0


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

    @pytest.mark.asyncio
    async def test_snapshot_captured_from_handshake(self, caplog) -> None:
        snapshot_data = {
            "snapshot": {
                "uptimeMs": 123456,
                "health": {"status": "ok"},
                "presence": {"clients": ["a"]},
                "sessions": {"recent": [{"key": "private-session-key"}]},
                "stateVersion": 7,
            },
            "policy": {"maxSessions": 5},
        }

        def response(sent):
            return {
                "type": "res",
                "id": sent[-1]["id"],
                "ok": True,
                "payload": snapshot_data,
            }

        protocol = GatewayProtocol("localhost", 1, None)
        protocol._websocket = DummyWebSocket([response])

        with caplog.at_level(logging.DEBUG):
            await protocol._handshake()

        assert protocol.connect_snapshot == snapshot_data
        assert protocol.connect_snapshot["snapshot"]["uptimeMs"] == 123456
        assert "private-session-key" not in caplog.text

    @pytest.mark.asyncio
    async def test_snapshot_defaults_to_empty(self) -> None:
        def response(sent):
            return {
                "type": "res",
                "id": sent[-1]["id"],
                "ok": True,
            }

        protocol = GatewayProtocol("localhost", 1, None)
        protocol._websocket = DummyWebSocket([response])

        await protocol._handshake()

        assert protocol.connect_snapshot == {}

    @pytest.mark.asyncio
    async def test_presence_seeded_from_snapshot(self) -> None:
        presence = {"clients": ["ha-client"]}

        def response(sent):
            return {
                "type": "res",
                "id": sent[-1]["id"],
                "ok": True,
                "payload": {"snapshot": {"presence": presence}},
            }

        protocol = GatewayProtocol("localhost", 1, None)
        protocol._websocket = DummyWebSocket([response])

        await protocol._handshake()

        assert protocol.presence == presence

    @pytest.mark.asyncio
    async def test_presence_empty_when_no_snapshot(self) -> None:
        def response(sent):
            return {
                "type": "res",
                "id": sent[-1]["id"],
                "ok": True,
                "payload": {},
            }

        protocol = GatewayProtocol("localhost", 1, None)
        protocol._websocket = DummyWebSocket([response])

        await protocol._handshake()

        assert protocol.presence == {}

    @pytest.mark.asyncio
    async def test_presence_list_normalized_to_dict(self) -> None:
        def response(sent):
            return {
                "type": "res",
                "id": sent[-1]["id"],
                "ok": True,
                "payload": {"snapshot": {"presence": ["client-a", "client-b"]}},
            }

        protocol = GatewayProtocol("localhost", 1, None)
        protocol._websocket = DummyWebSocket([response])

        await protocol._handshake()

        assert protocol.presence == {"clients": ["client-a", "client-b"]}


class TestChallengeHandshake:
    """Tests for the connect.challenge flow (2026.2.13+)."""

    @pytest.mark.asyncio
    async def test_challenge_consumed_token_only_auth(self) -> None:
        """Challenge is consumed but token-only auth is used (no device pairing)."""
        challenge = {
            "type": "event",
            "event": "connect.challenge",
            "payload": {"nonce": "test-uuid-nonce", "ts": 1700000000},
        }

        def ok_response(sent):
            return {
                "type": "res",
                "id": sent[-1]["id"],
                "ok": True,
                "payload": {},
            }

        protocol = GatewayProtocol("localhost", 1, "tok")
        protocol._websocket = DummyWebSocket([challenge, ok_response])

        await protocol._handshake()

        connect_params = protocol._websocket.sent[0]["params"]
        assert connect_params["auth"] == {"token": "tok"}
        assert connect_params["role"] == "operator"
        assert connect_params["scopes"] == ["operator.read", "operator.write"]
        assert "device" not in connect_params

    @pytest.mark.asyncio
    async def test_no_challenge_falls_back_to_legacy(self) -> None:
        """When gateway doesn't send challenge, handshake works normally."""

        def ok_response(sent):
            return {
                "type": "res",
                "id": sent[-1]["id"],
                "ok": True,
                "payload": {},
            }

        protocol = GatewayProtocol("localhost", 1, "tok")
        # First message is a non-challenge event (simulates old gateway)
        protocol._websocket = DummyWebSocket(
            [{"type": "event", "event": "agent"}, ok_response]
        )

        await protocol._handshake()

        connect_params = protocol._websocket.sent[0]["params"]
        assert "device" not in connect_params
        assert connect_params["auth"] == {"token": "tok"}

    @pytest.mark.asyncio
    async def test_nonce_mismatch_raises_auth_error(self) -> None:
        """Device nonce mismatch raises GatewayAuthenticationError."""
        challenge = {
            "type": "event",
            "event": "connect.challenge",
            "payload": {"nonce": "test-nonce", "ts": 1700000000},
        }

        def error_response(sent):
            return {
                "type": "res",
                "id": sent[-1]["id"],
                "ok": False,
                "error": "device nonce mismatch",
            }

        protocol = GatewayProtocol("localhost", 1, "tok")
        protocol._websocket = DummyWebSocket([challenge, error_response])

        with pytest.raises(GatewayAuthenticationError, match="device"):
            await protocol._handshake()

    @pytest.mark.asyncio
    async def test_not_paired_raises_pairing_error(self) -> None:
        """NOT_PAIRED error raises DevicePairingRequiredError."""
        challenge = {
            "type": "event",
            "event": "connect.challenge",
            "payload": {"nonce": "test-nonce", "ts": 1700000000},
        }

        def error_response(sent):
            return {
                "type": "res",
                "id": sent[-1]["id"],
                "ok": False,
                "error": {
                    "code": "NOT_PAIRED",
                    "message": "pairing required",
                },
            }

        protocol = GatewayProtocol("localhost", 1, "tok")
        protocol._websocket = DummyWebSocket([challenge, error_response])

        with pytest.raises(DevicePairingRequiredError, match="pairing"):
            await protocol._handshake()

    @pytest.mark.asyncio
    async def test_device_credentials_included_when_hass_provided(
        self, monkeypatch
    ) -> None:
        """When hass is available and nonce received, device credentials are included."""
        _device_auth = sys.modules["custom_components.openclaw.device_auth"]
        key = _device_auth.generate_keypair()
        monkeypatch.setattr(
            _gateway,
            "async_load_or_create_keypair",
            AsyncMock(return_value=key),
        )

        challenge = {
            "type": "event",
            "event": "connect.challenge",
            "payload": {"nonce": "test-nonce", "ts": 1700000000},
        }

        def ok_response(sent):
            return {
                "type": "res",
                "id": sent[-1]["id"],
                "ok": True,
                "payload": {},
            }

        mock_hass = object()
        protocol = GatewayProtocol("localhost", 1, "tok", hass=mock_hass)
        protocol._websocket = DummyWebSocket([challenge, ok_response])

        await protocol._handshake()

        connect_params = protocol._websocket.sent[0]["params"]
        assert "device" in connect_params
        assert "id" in connect_params["device"]
        assert "publicKey" in connect_params["device"]
        assert "signature" in connect_params["device"]
        assert connect_params["device"]["nonce"] == "test-nonce"

    @pytest.mark.asyncio
    async def test_no_device_credentials_without_hass(self) -> None:
        """Without hass, device credentials are omitted even with a nonce."""
        challenge = {
            "type": "event",
            "event": "connect.challenge",
            "payload": {"nonce": "test-nonce", "ts": 1700000000},
        }

        def ok_response(sent):
            return {
                "type": "res",
                "id": sent[-1]["id"],
                "ok": True,
                "payload": {},
            }

        protocol = GatewayProtocol("localhost", 1, "tok")  # No hass
        protocol._websocket = DummyWebSocket([challenge, ok_response])

        await protocol._handshake()

        connect_params = protocol._websocket.sent[0]["params"]
        assert "device" not in connect_params

    @pytest.mark.asyncio
    async def test_token_is_not_in_uri(self) -> None:
        """Token is not exposed in the WebSocket URI."""
        protocol = GatewayProtocol("localhost", 18789, "my-secret-token")
        assert protocol._uri == "ws://localhost:18789"
        assert "my-secret-token" not in protocol._uri

    @pytest.mark.asyncio
    async def test_no_token_uri_has_no_query(self) -> None:
        """Without a token, URI has no query params."""
        protocol = GatewayProtocol("localhost", 18789, None)
        assert protocol._uri == "ws://localhost:18789"
