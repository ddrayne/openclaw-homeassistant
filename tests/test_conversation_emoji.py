"""Tests for emoji stripping, against the integration's real pattern."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tests._conversation_loader import load_conversation_module

conv = load_conversation_module(streaming="none")
strip_emojis = conv.strip_emojis


class TestStripEmojis:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Hello \U0001F600", "Hello"),
            ("I'm Claude \U0001F99E", "I'm Claude"),  # lobster, a newer emoji
            ("Done ✅", "Done"),
            ("Sunny ☀️ today", "Sunny  today"),
            ("⭐ Starred", "Starred"),
            # ZWJ sequence (family) and a flag are removed whole.
            ("Hi \U0001F468‍\U0001F469‍\U0001F467 all", "Hi  all"),
            ("Go \U0001F1E9\U0001F1EA", "Go"),
            ("Press 3️⃣", "Press 3"),
        ],
    )
    def test_removes_emoji(self, text: str, expected: str) -> None:
        assert strip_emojis(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "Hi :)",
            "Plain text",
            # Regression (#22): the old pattern's U+24C2-U+1F251 range removed
            # every CJK character, leaving an empty spoken response.
            "你好，今天天气晴朗。",
            "こんにちは、元気です。カタカナ",
            "안녕하세요",
            "Привет, как дела?",
            "Grüße — 20 °C, 5 € × 2 → 10 €",
            "مرحبا بالعالم",
            # A zero-width joiner outside emoji shapes text and must survive.
            "می‍خواهم",
            "© 2026 OpenClaw™ ①②③",
        ],
    )
    def test_keeps_text(self, text: str) -> None:
        assert strip_emojis(text) == text


def _entity(strip: bool = True):
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"strip_emojis": strip, "tts_max_chars": 0, "background_enabled": False}
    entry.options = {}
    gateway = MagicMock()
    gateway.connected = True
    return conv.OpenClawConversationEntity(entry, gateway), gateway


def _user_input():
    user_input = MagicMock()
    user_input.text = "你好"
    user_input.language = "zh"
    user_input.conversation_id = "c1"
    user_input.agent_id = "agent"
    return user_input


async def test_chinese_reply_is_spoken_with_stripping_on() -> None:
    """End to end for #22: the reply must reach Assist, not an empty response."""
    entity, gateway = _entity()

    async def fake_send(_message: str, **_kw) -> str:
        return "今天天气晴朗 \U0001F31E"

    gateway.send_agent_request = fake_send
    result = await entity._async_handle_message(
        _user_input(), conv.conversation.ChatLog()
    )

    assert result.response.speech == "今天天气晴朗"


async def test_emoji_only_reply_is_not_spoken_as_empty() -> None:
    entity, gateway = _entity()

    async def fake_send(_message: str, **_kw) -> str:
        return "\U0001F44D"

    gateway.send_agent_request = fake_send
    result = await entity._async_handle_message(
        _user_input(), conv.conversation.ChatLog()
    )

    assert result.response.speech == "\U0001F44D"
