"""Tests for the built-in spoken phrases and their language selection."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tests._conversation_loader import load_conversation_module

conv = load_conversation_module(streaming="none")
phrases = __import__("sys").modules["custom_components.openclaw.phrases"]
exceptions = __import__("sys").modules["custom_components.openclaw.exceptions"]


def test_every_language_has_every_phrase() -> None:
    expected = set(phrases.PHRASES["en"])
    for language, table in phrases.PHRASES.items():
        assert set(table) == expected, language
        assert all(text.strip() for text in table.values()), language


def test_translations_differ_from_english() -> None:
    """Catches a language entry that was copied but never translated."""
    english = phrases.PHRASES["en"]
    for language, table in phrases.PHRASES.items():
        if language == "en":
            continue
        same = [key for key in table if table[key] == english[key]]
        assert not same, (language, same)


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("en", "en"),
        ("en-GB", "en"),
        ("de", "de"),
        ("de-CH", "de"),
        ("fr_CA", "fr"),
        ("pt", "pt-BR"),
        ("pt-BR", "pt-BR"),
        ("zh", "zh-Hans"),
        ("zh-CN", "zh-Hans"),
        ("zh-Hans", "zh-Hans"),
        ("zh-TW", "zh-Hant"),
        ("zh-HK", "zh-Hant"),
        ("zh-Hant", "zh-Hant"),
        ("JA", "ja"),
        ("xx", "en"),  # unknown language
        ("", "en"),
        (None, "en"),
        (MagicMock(), "en"),  # not a string at all
    ],
)
def test_resolve_language(tag, expected: str) -> None:
    assert phrases.resolve_language(tag) == expected


def test_holding_phrase_prefers_the_users_own() -> None:
    default = conv.DEFAULT_HOLDING_PHRASE
    german = phrases.PHRASES["de"]["holding"]

    # Untouched setting (absent, empty, or still the English default):
    # speak the request's language.
    assert phrases.holding_phrase({}, "de") == german
    assert phrases.holding_phrase({"holding_phrase": ""}, "de") == german
    assert phrases.holding_phrase({"holding_phrase": default}, "de") == german
    assert phrases.holding_phrase({"holding_phrase": default}, "en") == default
    # A phrase the user wrote is used as written, whatever the language.
    assert phrases.holding_phrase({"holding_phrase": "Moment!"}, "fr") == "Moment!"


def _entity(options: dict):
    entry = SimpleNamespace(entry_id="e1", data={}, options=options)
    client = conv.OpenClawGatewayClient("localhost", 1, None, timeout=5.0)
    client._resolved_agent_id = "main"

    async def fake_send_request(method=None, params=None, timeout=None, **_kw):
        return {"payload": {"runId": "r1"}}

    client._gateway.send_request = fake_send_request
    entity = conv.OpenClawConversationEntity(entry, client)
    entity.hass = MagicMock()
    entity.hass.async_create_background_task = (
        lambda coro, name=None: asyncio.create_task(coro)
    )
    return client, entity


def _user_input(language: str):
    return SimpleNamespace(
        text="hallo",
        language=language,
        agent_id="agent",
        conversation_id="c1",
        device_id=None,
    )


async def test_deferred_request_is_acknowledged_in_the_request_language() -> None:
    client, entity = _entity({"background_grace": 0.05})

    result = await asyncio.wait_for(
        entity._async_handle_message(_user_input("de-DE"), conv.conversation.ChatLog()),
        2,
    )

    assert result.response.speech == phrases.PHRASES["de"]["holding"]
    for task in list(entity._background_tasks):
        task.cancel()


async def test_error_message_is_spoken_in_the_request_language() -> None:
    client, entity = _entity({"background_enabled": False})

    async def fail(_message: str, **_kw) -> str:
        raise exceptions.GatewayTimeoutError("slow")

    client.send_agent_request = fail
    client._gateway._connected = True

    result = await entity._async_handle_message(
        _user_input("zh-CN"), conv.conversation.ChatLog()
    )

    assert result.response.speech == phrases.PHRASES["zh-Hans"]["timeout"]
