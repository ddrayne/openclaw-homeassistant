"""Tests for conversation entity metadata without HA runtime."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock


def _stub_module(name: str) -> ModuleType:
    module = ModuleType(name)
    sys.modules.setdefault(name, module)
    return module


def _ensure_ha_stubs() -> bool:
    existing = sys.modules.get("homeassistant")
    if existing is not None and not getattr(existing, "__file__", None):
        sys.modules.pop("homeassistant", None)
    try:
        import homeassistant  # noqa: F401
        return False
    except Exception:
        return True


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_conversation_module():
    if _ensure_ha_stubs():
        _stub_module("homeassistant")
        _stub_module("homeassistant.components")
        conversation_mod = _stub_module("homeassistant.components.conversation")
        config_entries_mod = _stub_module("homeassistant.config_entries")
        core_mod = _stub_module("homeassistant.core")
        intent_mod = _stub_module("homeassistant.helpers.intent")
        _stub_module("homeassistant.helpers")
        entity_platform_mod = _stub_module("homeassistant.helpers.entity_platform")

        class ConversationEntity:
            pass

        class AssistantContent:
            def __init__(self, agent_id: str, content: str) -> None:
                self.agent_id = agent_id
                self.content = content

        class ConversationInput:
            pass

        class ChatLog:
            def async_add_assistant_content_without_tools(self, _content) -> None:
                return None

        class ConversationResult:
            def __init__(self, response, conversation_id: str) -> None:
                self.response = response
                self.conversation_id = conversation_id

        class IntentResponse:
            def __init__(self, language: str) -> None:
                self.language = language

            def async_set_speech(self, _message: str) -> None:
                return None

        conversation_mod.ConversationEntity = ConversationEntity
        conversation_mod.AssistantContent = AssistantContent
        conversation_mod.ConversationInput = ConversationInput
        conversation_mod.ChatLog = ChatLog
        conversation_mod.ConversationResult = ConversationResult
        config_entries_mod.ConfigEntry = object
        core_mod.HomeAssistant = object
        intent_mod.IntentResponse = IntentResponse
        entity_platform_mod.AddEntitiesCallback = object

    base = Path(__file__).parent.parent / "custom_components" / "clawd"
    sys.modules.setdefault("custom_components", ModuleType("custom_components"))
    sys.modules.setdefault("custom_components.clawd", ModuleType("custom_components.clawd"))

    _load_module("custom_components.clawd.const", base / "const.py")
    _load_module("custom_components.clawd.exceptions", base / "exceptions.py")
    _load_module("custom_components.clawd.gateway", base / "gateway.py")
    _load_module("custom_components.clawd.gateway_client", base / "gateway_client.py")
    return _load_module(
        "custom_components.clawd.conversation", base / "conversation.py"
    )


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

    entity = conversation.ClawdConversationEntity(entry, MagicMock())

    assert entity.device_info["identifiers"] == {(conversation.DOMAIN, "entry-1")}
    assert entity.device_info["manufacturer"] == "Clawdbot"
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
    entity = conversation.ClawdConversationEntity(entry, MagicMock())

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
