"""Tests for the 'continue_conversation on follow-up question' behavior.

Covers both the pure helper and the three end-to-end paths through
`OpenClawConversationEntity._async_handle_message`:

- non-streaming
- streaming via setattr on ConversationResult (primary path)
- streaming via StreamingConversationResult (fallback path) — regression test
  for a bug where the generator's finally block mutated the wrong object.
"""

from __future__ import annotations

from typing import AsyncIterator
from unittest.mock import MagicMock

from tests._conversation_loader import load_conversation_module


def _make_entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"strip_emojis": False, "tts_max_chars": 0}
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


# ---------- streaming, primary path (setattr on ConversationResult) ----------


async def test_streaming_primary_path_sets_continue() -> None:
    conv = load_conversation_module(streaming="primary")
    gateway = _make_gateway()

    async def fake_stream(_message: str, **_kw) -> AsyncIterator[str]:
        for chunk in ("Here you go. ", "Want more detail?"):
            yield chunk

    gateway.stream_agent_request = fake_stream

    entity = conv.OpenClawConversationEntity(_make_entry(), gateway)
    result = await entity._async_handle_message(_make_user_input(), FakeChatLog())

    # Sanity: the primary path returns the original ConversationResult with
    # the async generator attached as `response_stream`.
    assert hasattr(result, "response_stream")
    async for _ in result.response_stream:
        pass

    assert result.continue_conversation is True


async def test_streaming_primary_path_no_followup() -> None:
    conv = load_conversation_module(streaming="primary")
    gateway = _make_gateway()

    async def fake_stream(_message: str, **_kw) -> AsyncIterator[str]:
        for chunk in ("All set. ", "Task complete."):
            yield chunk

    gateway.stream_agent_request = fake_stream

    entity = conv.OpenClawConversationEntity(_make_entry(), gateway)
    result = await entity._async_handle_message(_make_user_input(), FakeChatLog())
    async for _ in result.response_stream:
        pass

    assert result.continue_conversation is False


# ---------- streaming, fallback path (regression test for the bug fix) ----------


async def test_streaming_fallback_path_sets_continue_on_returned_object() -> None:
    conv = load_conversation_module(streaming="fallback")
    gateway = _make_gateway()

    async def fake_stream(_message: str, **_kw) -> AsyncIterator[str]:
        for chunk in ("Sure. ", "Need anything else?"):
            yield chunk

    gateway.stream_agent_request = fake_stream

    entity = conv.OpenClawConversationEntity(_make_entry(), gateway)
    result = await entity._async_handle_message(_make_user_input(), FakeChatLog())

    # Fallback path must return the StreamingConversationResult instance,
    # not the original ConversationResult.
    assert type(result).__name__ == "StreamingConversationResult"
    async for _ in result.response_stream:
        pass

    # Before the fix this was `False` because the generator's finally block
    # mutated a different object than the one returned to HA.
    assert result.continue_conversation is True


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
