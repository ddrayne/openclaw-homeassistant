"""Shared helper: stub homeassistant and load the OpenClaw conversation module.

Used by tests that need to exercise `custom_components/openclaw/conversation.py`
without a real Home Assistant installation.

The `streaming` argument controls whether the stubbed `ChatLog` supports
Home Assistant's delta streaming API, so tests can exercise both paths:

- "none":    No streaming support. `_supports_streaming_result()` -> False.
- "chatlog": `ChatLog.async_add_delta_content_stream` and
             `conversation.async_get_result_from_chat_log` exist, mirroring
             how HA (2025.6+) streams LLM output into TTS.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, AsyncIterable, AsyncIterator


def _stub_module(name: str) -> ModuleType:
    module = ModuleType(name)
    sys.modules[name] = module
    return module


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_conversation_module(*, streaming: str = "none") -> ModuleType:
    """Stub homeassistant.* and load the conversation module fresh."""
    _stub_module("homeassistant")
    _stub_module("homeassistant.components")
    conversation_mod = _stub_module("homeassistant.components.conversation")
    config_entries_mod = _stub_module("homeassistant.config_entries")
    core_mod = _stub_module("homeassistant.core")
    intent_mod = _stub_module("homeassistant.helpers.intent")
    _stub_module("homeassistant.helpers")
    entity_platform_mod = _stub_module("homeassistant.helpers.entity_platform")
    er_mod = _stub_module("homeassistant.helpers.entity_registry")
    er_mod.async_get = lambda _hass: None
    er_mod.async_entries_for_device = lambda _registry, _device_id: []
    exceptions_mod = _stub_module("homeassistant.exceptions")
    exceptions_mod.HomeAssistantError = type(
        "HomeAssistantError", (Exception,), {}
    )

    class ConversationEntity:
        pass

    class AssistantContent:
        def __init__(self, agent_id: str, content: str | None = None) -> None:
            self.agent_id = agent_id
            self.content = content

    class ConversationInput:
        pass

    class ConversationResult:
        def __init__(
            self,
            response: Any,
            conversation_id: Any = None,
            continue_conversation: bool = False,
        ) -> None:
            self.response = response
            self.conversation_id = conversation_id
            self.continue_conversation = continue_conversation

    class IntentResponse:
        def __init__(self, language: str) -> None:
            self.language = language
            self.speech: str | None = None

        def async_set_speech(self, message: str) -> None:
            self.speech = message

    if streaming == "chatlog":

        class ChatLog:
            """Mirror of HA's ChatLog delta streaming (assistant role only)."""

            def __init__(self) -> None:
                self.content: list[Any] = []
                self.deltas: list[dict] = []

            def async_add_assistant_content_without_tools(
                self, content: Any
            ) -> None:
                self.content.append(content)

            async def async_add_delta_content_stream(
                self, agent_id: str, stream: AsyncIterable[dict]
            ) -> AsyncIterator[Any]:
                current: AssistantContent | None = None
                async for delta in stream:
                    self.deltas.append(delta)
                    if "role" in delta:
                        if current is not None:
                            self.content.append(current)
                            yield current
                        current = AssistantContent(
                            agent_id, delta.get("content") or ""
                        )
                        continue
                    assert current is not None, "delta before role"
                    current.content += delta.get("content") or ""
                if current is not None:
                    self.content.append(current)
                    yield current

        def async_get_result_from_chat_log(
            user_input: Any, chat_log: ChatLog
        ) -> ConversationResult:
            intent_response = IntentResponse(language=user_input.language)
            intent_response.async_set_speech(chat_log.content[-1].content or "")
            return ConversationResult(
                response=intent_response,
                conversation_id=user_input.conversation_id,
            )

        conversation_mod.async_get_result_from_chat_log = (
            async_get_result_from_chat_log
        )
    else:

        class ChatLog:
            def async_add_assistant_content_without_tools(
                self, _content: Any
            ) -> None:
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

    repo_root = Path(__file__).parent.parent
    base = repo_root / "custom_components" / "openclaw"

    # Register custom_components / custom_components.openclaw as real packages
    # so relative imports inside gateway.py ("from .device_auth import ...") work.
    cc_pkg = ModuleType("custom_components")
    cc_pkg.__path__ = [str(repo_root / "custom_components")]  # type: ignore[attr-defined]
    sys.modules["custom_components"] = cc_pkg

    oc_pkg = ModuleType("custom_components.openclaw")
    oc_pkg.__path__ = [str(base)]  # type: ignore[attr-defined]
    sys.modules["custom_components.openclaw"] = oc_pkg

    _load_module("custom_components.openclaw.const", base / "const.py")
    _load_module("custom_components.openclaw.exceptions", base / "exceptions.py")
    _load_module(
        "custom_components.openclaw.device_auth", base / "device_auth.py"
    )
    _load_module("custom_components.openclaw.gateway", base / "gateway.py")
    _load_module(
        "custom_components.openclaw.gateway_client", base / "gateway_client.py"
    )
    return _load_module(
        "custom_components.openclaw.conversation", base / "conversation.py"
    )
