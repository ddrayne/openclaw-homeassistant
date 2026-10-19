"""Tests for the 'continue_conversation on follow-up question' behavior.

Covers both the pure helper and the three end-to-end paths through
`OpenClawConversationEntity._async_handle_message`:

- non-streaming
- streaming via ChatLog.async_add_delta_content_stream (HA 2025.6+)
"""

from __future__ import annotations

from typing import AsyncIterator
from unittest.mock import MagicMock

from tests._conversation_loader import load_conversation_module


def _make_entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "entry-1"
    # background_enabled False: these tests pin the legacy (non-grace-race)
    # request paths, which remain reachable behind that option.
    entry.data = {
        "strip_emojis": False,
        "tts_max_chars": 0,
        "streaming_enabled": True,  # opt-in explicitly for ChatLog tests
        "background_enabled": False,
    }
    entry.options = {}
    return entry


def _make_gateway() -> MagicMock:
    gw = MagicMock()
    gw.connected = True
    gw.session_key = "main"
    gw.agent_id = ""
    gw.model = ""
    gw.thinking = ""
    return gw


def _make_user_input(text: str = "hello") -> MagicMock:
    ui = MagicMock()
    ui.language = "en"
    ui.conversation_id = None
    ui.agent_id = "agent-1"
    ui.text = text
    return ui


class FakeChatLog:
    def async_add_assistant_content_without_tools(self, _content) -> None:
        return None


# ---------- pure helper ----------


def test_response_expects_followup_helper() -> None:
    conv = load_conversation_module()
    assert conv.response_expects_followup("What do you think?") is True
    assert conv.response_expects_followup("Maybe? sure.") is True
    assert conv.response_expects_followup("Done.") is False
    assert conv.response_expects_followup("") is False
    assert conv.response_expects_followup(None) is False  # type: ignore[arg-type]


# ---------- non-streaming path ----------


async def test_non_streaming_sets_continue_on_question() -> None:
    conv = load_conversation_module(streaming="none")
    gateway = _make_gateway()

    async def fake_send(_message: str, **_kw) -> str:
        return "Want me to do that for you?"

    gateway.send_agent_request = fake_send

    entity = conv.OpenClawConversationEntity(_make_entry(), gateway)
    result = await entity._async_handle_message(_make_user_input(), FakeChatLog())

    assert result.continue_conversation is True


async def test_non_streaming_no_followup_on_statement() -> None:
    conv = load_conversation_module(streaming="none")
    gateway = _make_gateway()

    async def fake_send(_message: str, **_kw) -> str:
        return "Done."

    gateway.send_agent_request = fake_send

    entity = conv.OpenClawConversationEntity(_make_entry(), gateway)
    result = await entity._async_handle_message(_make_user_input(), FakeChatLog())

    assert result.continue_conversation is False


async def test_chatlog_available_but_streaming_disabled_by_default() -> None:
    """Text Assist can return the complete response with TTS limit set to 0."""
    conv = load_conversation_module(streaming="chatlog")
    gateway = _make_gateway()

    async def fake_send(_message: str, **_kw) -> str:
        return "Full response " * 230

    gateway.send_agent_request = fake_send
    entry = _make_entry()
    entry.data.pop("streaming_enabled")
    entity = conv.OpenClawConversationEntity(entry, gateway)
    chat_log = conv.conversation.ChatLog()

    result = await entity._async_handle_message(_make_user_input(), chat_log)

    assert entity._attr_supports_streaming is False
    assert chat_log.deltas == []
    assert result.response.speech == "Full response " * 230
    gateway.stream_agent_request.assert_not_called()


async def test_chatlog_streaming_opt_in_without_tts_limit() -> None:
    """Voice installations can explicitly opt in to incremental ChatLog output."""
    conv = load_conversation_module(streaming="chatlog")
    gateway = _make_gateway()

    async def fake_stream(_message: str, **_kw) -> AsyncIterator[str]:
        yield "Chunk one"
        yield " and two"

    gateway.stream_agent_request = fake_stream
    entry = _make_entry()
    entity = conv.OpenClawConversationEntity(entry, gateway)
    chat_log = conv.conversation.ChatLog()

    result = await entity._async_handle_message(_make_user_input(), chat_log)

    assert entity._attr_supports_streaming is True
    assert chat_log.deltas == [
        {"role": "assistant"},
        {"content": "Chunk one"},
        {"content": " and two"},
    ]
    assert result.response.speech == "Chunk one and two"


async def test_streaming_terminal_replacement_updates_intent_end() -> None:
    """A non-prefix final answer becomes the ChatLog's last assistant item."""
    conv = load_conversation_module(streaming="chatlog")
    from custom_components.openclaw.gateway_client import AgentTextReplacement

    gateway = _make_gateway()

    async def fake_stream(_message: str, **_kw):
        yield "Home"
        yield AgentTextReplacement("La domotique contrôle la maison.")

    gateway.stream_agent_request = fake_stream
    entity = conv.OpenClawConversationEntity(_make_entry(), gateway)
    chat_log = conv.conversation.ChatLog()

    result = await entity._async_handle_message(_make_user_input(), chat_log)

    assert chat_log.deltas == [
        {"role": "assistant"},
        {"content": "Home"},
        {"role": "assistant", "content": "La domotique contrôle la maison."},
    ]
    assert result.response.speech == "La domotique contrôle la maison."


# ---------- streaming via ChatLog deltas ----------


async def test_supports_streaming_detects_chatlog_api() -> None:
    conv = load_conversation_module(streaming="chatlog")
    assert conv.OpenClawConversationEntity._supports_streaming_result() is True
    conv = load_conversation_module(streaming="none")
    assert conv.OpenClawConversationEntity._supports_streaming_result() is False


async def test_streaming_sets_continue_on_question() -> None:
    conv = load_conversation_module(streaming="chatlog")
    gateway = _make_gateway()

    async def fake_stream(_message: str, **_kw) -> AsyncIterator[str]:
        for chunk in ("Here you go. ", "Want more detail?"):
            yield chunk

    gateway.stream_agent_request = fake_stream

    entity = conv.OpenClawConversationEntity(_make_entry(), gateway)
    chat_log = conv.conversation.ChatLog()
    result = await entity._async_handle_message(_make_user_input(), chat_log)

    # Each Gateway chunk reaches the chat log as its own delta, so HA's
    # pipeline can start streaming TTS before the reply is complete.
    assert chat_log.deltas == [
        {"role": "assistant"},
        {"content": "Here you go. "},
        {"content": "Want more detail?"},
    ]
    assert result.response.speech == "Here you go. Want more detail?"
    assert result.continue_conversation is True


async def test_streaming_no_followup_on_statement() -> None:
    conv = load_conversation_module(streaming="chatlog")
    gateway = _make_gateway()

    async def fake_stream(_message: str, **_kw) -> AsyncIterator[str]:
        for chunk in ("All set. ", "Task complete."):
            yield chunk

    gateway.stream_agent_request = fake_stream

    entity = conv.OpenClawConversationEntity(_make_entry(), gateway)
    result = await entity._async_handle_message(
        _make_user_input(), conv.conversation.ChatLog()
    )

    assert result.response.speech == "All set. Task complete."
    assert result.continue_conversation is False


async def test_streaming_strips_emojis_per_chunk() -> None:
    conv = load_conversation_module(streaming="chatlog")
    gateway = _make_gateway()

    async def fake_stream(_message: str, **_kw) -> AsyncIterator[str]:
        for chunk in ("Done ", "😀", " for today."):
            yield chunk

    gateway.stream_agent_request = fake_stream

    entry = _make_entry()
    entry.data["strip_emojis"] = True
    entity = conv.OpenClawConversationEntity(entry, gateway)
    chat_log = conv.conversation.ChatLog()
    result = await entity._async_handle_message(_make_user_input(), chat_log)

    # The emoji-only chunk is dropped; whitespace between chunks survives.
    assert chat_log.deltas == [
        {"role": "assistant"},
        {"content": "Done "},
        {"content": " for today."},
    ]
    assert result.response.speech == "Done  for today."


async def test_streaming_error_before_content_speaks_fallback() -> None:
    conv = load_conversation_module(streaming="chatlog")
    from custom_components.openclaw.exceptions import GatewayTimeoutError

    gateway = _make_gateway()

    async def fake_stream(_message: str, **_kw) -> AsyncIterator[str]:
        raise GatewayTimeoutError("slow")
        yield  # pragma: no cover - makes this an async generator

    gateway.stream_agent_request = fake_stream

    entity = conv.OpenClawConversationEntity(_make_entry(), gateway)
    result = await entity._async_handle_message(
        _make_user_input(), conv.conversation.ChatLog()
    )

    assert result.response.speech == "The response took too long. Please try again."
    assert result.continue_conversation is False


async def test_streaming_error_after_content_keeps_partial_reply() -> None:
    conv = load_conversation_module(streaming="chatlog")
    from custom_components.openclaw.exceptions import GatewayConnectionError

    gateway = _make_gateway()

    async def fake_stream(_message: str, **_kw) -> AsyncIterator[str]:
        yield "Partial answer."
        raise GatewayConnectionError("dropped")

    gateway.stream_agent_request = fake_stream

    entity = conv.OpenClawConversationEntity(_make_entry(), gateway)
    result = await entity._async_handle_message(
        _make_user_input(), conv.conversation.ChatLog()
    )

    assert result.response.speech == "Partial answer."


async def test_streaming_skipped_when_tts_trimming_enabled() -> None:
    conv = load_conversation_module(streaming="chatlog")
    gateway = _make_gateway()

    async def fake_send(_message: str, **_kw) -> str:
        return "A rather long answer"

    gateway.send_agent_request = fake_send

    entry = _make_entry()
    entry.data["tts_max_chars"] = 8
    entity = conv.OpenClawConversationEntity(entry, gateway)
    chat_log = conv.conversation.ChatLog()
    result = await entity._async_handle_message(_make_user_input(), chat_log)

    # Trimming needs the full text, so the plain (buffered) path is used.
    assert chat_log.deltas == []
    assert result.response.speech == "A rat..."


# ---------- error path ----------


async def test_error_path_keeps_continue_false() -> None:
    conv = load_conversation_module(streaming="none")
    from custom_components.openclaw.exceptions import GatewayConnectionError

    gateway = _make_gateway()

    async def fake_send(_message: str, **_kw) -> str:
        raise GatewayConnectionError("boom")

    gateway.send_agent_request = fake_send

    entity = conv.OpenClawConversationEntity(_make_entry(), gateway)
    result = await entity._async_handle_message(_make_user_input(), FakeChatLog())

    assert getattr(result, "continue_conversation", False) is False
