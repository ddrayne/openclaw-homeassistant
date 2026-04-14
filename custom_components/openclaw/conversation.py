"""Conversation entity for OpenClaw integration."""

import dataclasses
import logging
import re
from typing import Any, AsyncIterator

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_STRIP_EMOJIS,
    CONF_TTS_MAX_CHARS,
    DEFAULT_STRIP_EMOJIS,
    DEFAULT_TTS_MAX_CHARS,
    DOMAIN,
)
from .exceptions import (
    AgentExecutionError,
    GatewayAuthenticationError,
    GatewayConnectionError,
    GatewayTimeoutError,
)
from .gateway_client import OpenClawGatewayClient

_LOGGER = logging.getLogger(__name__)

# Emoji pattern for removal from TTS
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


def strip_emojis(text: str) -> str:
    """Remove emojis from text for TTS."""
    return EMOJI_PATTERN.sub("", text).strip()


def trim_tts_text(text: str, max_chars: int) -> str:
    """Trim TTS text to a max character limit."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3].rstrip() + "..."


def response_expects_followup(text: str) -> bool:
    """Return True if the response looks like it asks a follow-up question.

    Keeps the satellite mic open so the user can reply without re-triggering
    the wake word. We treat any "?" in the reply as a follow-up cue.
    """
    return "?" in (text or "")


def _set_continue_conversation(
    result: conversation.ConversationResult, value: bool
) -> None:
    """Best-effort set of continue_conversation on HA versions that support it.

    Some HA versions expose ConversationResult as a frozen dataclass; tolerate
    both the "attribute not supported" and "frozen instance" cases as no-ops.
    """
    try:
        result.continue_conversation = value
    except (AttributeError, dataclasses.FrozenInstanceError):
        pass


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OpenClaw conversation entity."""
    gateway_client: OpenClawGatewayClient = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities([OpenClawConversationEntity(config_entry, gateway_client)])


class OpenClawConversationEntity(conversation.ConversationEntity):
    """OpenClaw conversation entity."""

    _attr_has_entity_name = True
    _attr_name = "OpenClaw"
    _attr_supported_languages = "*"
    _attr_supports_streaming = False

    def __init__(
        self, config_entry: ConfigEntry, gateway_client: OpenClawGatewayClient
    ) -> None:
        """Initialize the conversation entity."""
        self._config_entry = config_entry
        self._gateway_client = gateway_client
        self._attr_unique_id = config_entry.entry_id
        self._attr_supports_streaming = self._supports_streaming_result()

    @staticmethod
    def _supports_streaming_result() -> bool:
        """Return whether the HA conversation result supports streaming."""
        if hasattr(conversation, "StreamingConversationResult"):
            return True
        result_cls = getattr(conversation, "ConversationResult", None)
        if result_cls is None:
            return False
        annotations = getattr(result_cls, "__annotations__", {})
        if "response_stream" in annotations:
            return True
        if hasattr(result_cls, "response_stream"):
            return True
        slots = getattr(result_cls, "__slots__", ())
        if isinstance(slots, str):
            return slots == "response_stream"
        return "response_stream" in slots

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for the gateway."""
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": "OpenClaw Gateway",
            "manufacturer": "OpenClaw",
            "model": "Gateway",
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes for diagnostics."""
        data = {**self._config_entry.data, **self._config_entry.options}
        return {
            "host": data.get("host"),
            "port": data.get("port"),
            "use_ssl": data.get("use_ssl"),
            "session_key": self._gateway_client.session_key,
            "agent_id": self._gateway_client.agent_id,
            "model": self._gateway_client.model,
            "thinking": self._gateway_client.thinking,
            "strip_emojis": data.get(CONF_STRIP_EMOJIS, DEFAULT_STRIP_EMOJIS),
            "tts_max_chars": data.get(CONF_TTS_MAX_CHARS, DEFAULT_TTS_MAX_CHARS),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._gateway_client.connected

    @property
    def supported_languages(self) -> list[str] | str:
        """Return supported languages."""
        return "*"

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Handle user message."""
        _LOGGER.debug(
            "Processing message: %s (conversation_id: %s)",
            user_input.text,
            user_input.conversation_id,
        )

        # Extract user message
        user_message = user_input.text

        try:
            streaming_result = self._build_streaming_result(
                user_input, chat_log, user_message
            )
            if streaming_result is not None:
                return streaming_result

            response_text = await self._gateway_client.send_agent_request(
                user_message
            )
            intent_response = intent.IntentResponse(language=user_input.language)
            self._finalize_response(
                user_input, chat_log, response_text, intent_response
            )

            result = conversation.ConversationResult(
                response=intent_response,
                conversation_id=user_input.conversation_id,
            )
            _set_continue_conversation(
                result, response_expects_followup(response_text)
            )
            return result

        except GatewayAuthenticationError as err:
            _LOGGER.error("Gateway authentication error: %s", err)
            return self._create_error_result(
                user_input,
                "The gateway token is no longer valid. Please update it in "
                "Settings, Devices and Services, OpenClaw, Configure.",
                chat_log,
            )

        except GatewayConnectionError as err:
            _LOGGER.error("Gateway connection error: %s", err)
            return self._create_error_result(
                user_input,
                "I'm having trouble connecting to the Gateway. Please check your configuration.",
                chat_log,
            )

        except GatewayTimeoutError as err:
            _LOGGER.warning("Gateway timeout: %s", err)
            return self._create_error_result(
                user_input,
                "The response took too long. Please try again.",
                chat_log,
            )

        except AgentExecutionError as err:
            _LOGGER.error("Agent execution error: %s", err)
            return self._create_error_result(
                user_input,
                "I encountered an error while processing your request. Please try again.",
                chat_log,
            )

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected error in message handling")
            return self._create_error_result(
                user_input,
                "An unexpected error occurred. Please try again.",
                chat_log,
            )

    def _build_streaming_result(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
        user_message: str,
    ) -> conversation.ConversationResult | None:
        """Build a streaming conversation result when supported."""
        if not self._supports_streaming_result():
            return None

        intent_response = intent.IntentResponse(language=user_input.language)
        result = conversation.ConversationResult(
            response=intent_response,
            conversation_id=user_input.conversation_id,
        )
        # Shared reference so _stream_response's finally block can mutate
        # whichever object actually gets returned below — including the
        # replacement built by the StreamingConversationResult fallback.
        result_ref: list[conversation.ConversationResult] = [result]
        response_stream = self._stream_response(
            user_input, chat_log, user_message, intent_response, result_ref
        )

        try:
            setattr(result, "response_stream", response_stream)
            return result
        except AttributeError:
            pass

        streaming_cls = getattr(conversation, "StreamingConversationResult", None)
        if streaming_cls is None:
            return None

        init_attempts = [
            {
                "response": intent_response,
                "conversation_id": user_input.conversation_id,
                "response_stream": response_stream,
            },
            {
                "response": intent_response,
                "conversation_id": user_input.conversation_id,
                "stream": response_stream,
            },
            {
                "response": intent_response,
                "conversation_id": user_input.conversation_id,
                "async_stream": response_stream,
            },
        ]
        for kwargs in init_attempts:
            try:
                streamed = streaming_cls(**kwargs)
            except TypeError:
                continue
            result_ref[0] = streamed
            return streamed

        try:
            streamed = streaming_cls(
                intent_response, user_input.conversation_id, response_stream
            )
        except TypeError:
            _LOGGER.debug(
                "StreamingConversationResult signature not supported by this HA version"
            )
            return None
        result_ref[0] = streamed
        return streamed

    async def _stream_response(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
        user_message: str,
        intent_response: intent.IntentResponse,
        result_ref: list[conversation.ConversationResult],
    ) -> AsyncIterator[str]:
        """Stream response chunks from the Gateway."""
        chunks: list[str] = []
        had_content = False
        try:
            async for chunk in self._gateway_client.stream_agent_request(
                user_message
            ):
                if chunk:
                    chunks.append(chunk)
                    had_content = True
                    yield chunk
        except GatewayAuthenticationError as err:
            _LOGGER.error("Gateway authentication error: %s", err)
            if not had_content:
                message = (
                    "The gateway token is no longer valid. Please update it in "
                    "Settings, Devices and Services, OpenClaw, Configure."
                )
                chunks = [message]
                yield message
        except GatewayConnectionError as err:
            _LOGGER.error("Gateway connection error: %s", err)
            if not had_content:
                message = (
                    "I'm having trouble connecting to the Gateway. "
                    "Please check your configuration."
                )
                chunks = [message]
                yield message
        except GatewayTimeoutError as err:
            _LOGGER.warning("Gateway timeout: %s", err)
            if not had_content:
                message = "The response took too long. Please try again."
                chunks = [message]
                yield message
        except AgentExecutionError as err:
            _LOGGER.error("Agent execution error: %s", err)
            if not had_content:
                message = (
                    "I encountered an error while processing your request. "
                    "Please try again."
                )
                chunks = [message]
                yield message
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected error in streaming response")
            if not had_content:
                message = "An unexpected error occurred. Please try again."
                chunks = [message]
                yield message
        finally:
            response_text = "".join(chunks)
            self._finalize_response(
                user_input, chat_log, response_text, intent_response
            )
            _set_continue_conversation(
                result_ref[0], response_expects_followup(response_text)
            )

    def _finalize_response(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
        response_text: str,
        intent_response: intent.IntentResponse,
    ) -> None:
        """Add response to chat log and set TTS speech."""
        chat_log.async_add_assistant_content_without_tools(
            conversation.AssistantContent(
                agent_id=user_input.agent_id,
                content=response_text,
            )
        )

        config = {**self._config_entry.data, **self._config_entry.options}
        should_strip = config.get(CONF_STRIP_EMOJIS, DEFAULT_STRIP_EMOJIS)
        speech_text = (
            strip_emojis(response_text) if should_strip else response_text
        )
        max_chars = config.get(CONF_TTS_MAX_CHARS, DEFAULT_TTS_MAX_CHARS)
        speech_text = trim_tts_text(speech_text, max_chars)
        intent_response.async_set_speech(speech_text)

    def _create_error_result(
        self,
        user_input: conversation.ConversationInput,
        message: str,
        chat_log: conversation.ChatLog | None = None,
    ) -> conversation.ConversationResult:
        """Create an error result."""
        if chat_log is not None:
            chat_log.async_add_assistant_content_without_tools(
                conversation.AssistantContent(
                    agent_id=user_input.agent_id,
                    content=message,
                )
            )
        intent_response = intent.IntentResponse(language=user_input.language)
        intent_response.async_set_speech(message)
        return conversation.ConversationResult(
            response=intent_response,
            conversation_id=user_input.conversation_id,
        )
