"""Tests for proactive voice: session-message de-dupe and satellite announce."""

import time

import pytest

from tests._conversation_loader import load_conversation_module

_conv = load_conversation_module(streaming="none")
OpenClawGatewayClient = _conv.OpenClawGatewayClient
OpenClawConversationEntity = _conv.OpenClawConversationEntity


class TestProactiveDedup:
    """The session.message handler must announce only agent-initiated turns."""

    @staticmethod
    def _msg(role: str, content) -> dict:
        return {"payload": {"message": {"role": role, "content": content}}}

    def test_proactive_assistant_message_invokes_callback(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        seen: list[str] = []
        client.set_proactive_handler(seen.append)
        client._handle_session_message(self._msg("assistant", "Leave in 20 min"))
        assert seen == ["Leave in 20 min"]

    def test_echo_near_local_turn_is_suppressed(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        seen: list[str] = []
        client.set_proactive_handler(seen.append)
        client._last_local_turn = time.monotonic()  # user just spoke
        client._handle_session_message(self._msg("assistant", "echo of reply"))
        assert seen == []

    def test_user_message_ignored(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        seen: list[str] = []
        client.set_proactive_handler(seen.append)
        client._handle_session_message(self._msg("user", "turn on lights"))
        assert seen == []

    def test_no_handler_is_noop(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        # No proactive handler registered -> ignored, no error raised.
        client._handle_session_message(self._msg("assistant", "hi"))

    def test_content_list_is_flattened(self) -> None:
        client = OpenClawGatewayClient("localhost", 1, None)
        seen: list[str] = []
        client.set_proactive_handler(seen.append)
        client._handle_session_message(
            self._msg(
                "assistant",
                [{"type": "text", "text": "Part A "}, {"type": "text", "text": "Part B"}],
            )
        )
        assert seen == ["Part A Part B"]


class _FakeServices:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data, blocking))


class _FakeHass:
    def __init__(self) -> None:
        self.services = _FakeServices()


class _FakeEntry:
    entry_id = "e1"
    data: dict = {}

    def __init__(self, options: dict) -> None:
        self.options = options


def _make_entity(options: dict) -> OpenClawConversationEntity:
    client = OpenClawGatewayClient("localhost", 1, None)
    entity = OpenClawConversationEntity(_FakeEntry(options), client)
    entity.hass = _FakeHass()
    return entity


class TestAnnounce:
    """_async_announce maps a proactive turn onto assist_satellite services."""

    @pytest.mark.asyncio
    async def test_announce_strips_emojis_and_calls_service(self) -> None:
        entity = _make_entity(
            {
                "proactive_enabled": True,
                "proactive_satellite": "assist_satellite.kitchen",
                "proactive_mode": "announce",
                "strip_emojis": True,
            }
        )
        await entity._async_announce("Dinner is ready \U0001F600")
        calls = entity.hass.services.calls
        assert len(calls) == 1
        domain, service, data, _ = calls[0]
        assert (domain, service) == ("assist_satellite", "announce")
        assert data["entity_id"] == "assist_satellite.kitchen"
        assert data["message"] == "Dinner is ready"

    @pytest.mark.asyncio
    async def test_start_conversation_mode_uses_start_message(self) -> None:
        entity = _make_entity(
            {
                "proactive_enabled": True,
                "proactive_satellite": "assist_satellite.kitchen",
                "proactive_mode": "start_conversation",
            }
        )
        await entity._async_announce("Want me to read it?")
        domain, service, data, _ = entity.hass.services.calls[0]
        assert service == "start_conversation"
        assert data["start_message"] == "Want me to read it?"

    @pytest.mark.asyncio
    async def test_no_satellite_skips_call(self) -> None:
        entity = _make_entity({"proactive_enabled": True})
        await entity._async_announce("hi")
        assert entity.hass.services.calls == []

    @pytest.mark.asyncio
    async def test_satellite_error_is_handled(self) -> None:
        # A busy/offline satellite raises HomeAssistantError; _async_announce
        # must swallow it rather than letting it surface as an unhandled error.
        entity = _make_entity(
            {
                "proactive_enabled": True,
                "proactive_satellite": "assist_satellite.kitchen",
            }
        )

        async def _boom(*_args, **_kwargs):
            raise _conv.HomeAssistantError("device offline")

        entity.hass.services.async_call = _boom
        await entity._async_announce("hi")  # must not raise
