"""Tests for conversation entity metadata without HA runtime."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock


def _stub_module(name: str) -> ModuleType:
    module = ModuleType(name)
    sys.modules[name] = module
    return module


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_entity_metadata_properties() -> None:
    homeassistant = _stub_module("homeassistant")
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
    conversation = _load_module("custom_components.clawd.conversation", base / "conversation.py")

    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {
        "host": "localhost",
        "port": 1234,
        "use_ssl": False,
        "session_key": "main",
        "strip_emojis": True,
    }

    entity = conversation.ClawdConversationEntity(entry, MagicMock())

    assert entity.device_info["identifiers"] == {(conversation.DOMAIN, "entry-1")}
    assert entity.device_info["manufacturer"] == "Clawdbot"
    assert entity.extra_state_attributes["host"] == "localhost"
    assert entity.extra_state_attributes["strip_emojis"] is True
