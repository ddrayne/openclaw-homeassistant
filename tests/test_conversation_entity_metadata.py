"""Tests for conversation entity metadata without HA runtime."""

from unittest.mock import MagicMock

from tests._conversation_loader import load_conversation_module


def _load_conversation_module():
    return load_conversation_module()


def test_entity_metadata_properties() -> None:
    conversation = _load_conversation_module()

    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {
        "host": "localhost",
        "port": 1234,
        "use_ssl": False,
        "session_key": "main",
        "strip_emojis": True,
        "tts_max_chars": 200,
    }
    entry.options = {
        "use_ssl": True,
        "strip_emojis": False,
        "tts_max_chars": 123,
    }

    entity = conversation.OpenClawConversationEntity(entry, MagicMock())

    assert entity.device_info["identifiers"] == {(conversation.DOMAIN, "entry-1")}
    assert entity.device_info["manufacturer"] == "OpenClaw"
    assert entity.extra_state_attributes["host"] == "localhost"
    assert entity.extra_state_attributes["use_ssl"] is True
    assert entity.extra_state_attributes["strip_emojis"] is False
    assert entity.extra_state_attributes["tts_max_chars"] == 123


def test_trim_tts_text() -> None:
    conversation = _load_conversation_module()

    assert conversation.trim_tts_text("short", 10) == "short"
    assert conversation.trim_tts_text("1234567890", 0) == "1234567890"
    assert conversation.trim_tts_text("1234567890", 3) == "123"
    assert conversation.trim_tts_text("1234567890", 6) == "123..."


def test_error_message_added_to_chat_log() -> None:
    conversation = _load_conversation_module()

    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"strip_emojis": True}
    entry.options = {}
    entity = conversation.OpenClawConversationEntity(entry, MagicMock())

    user_input = MagicMock()
    user_input.language = "en"
    user_input.conversation_id = "conv-1"
    user_input.agent_id = "agent-1"

    class FakeChatLog:
        def __init__(self) -> None:
            self.contents = []

        def async_add_assistant_content_without_tools(self, content) -> None:
            self.contents.append(content)

    chat_log = FakeChatLog()
    result = entity._create_error_result(user_input, "Error", chat_log)

    assert result.conversation_id == "conv-1"
    assert len(chat_log.contents) == 1
    assert chat_log.contents[0].content == "Error"
