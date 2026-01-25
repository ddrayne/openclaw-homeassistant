"""Conversation entity for Clawd integration."""

import logging
import re
from typing import Any

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
    GatewayConnectionError,
    GatewayTimeoutError,
)
from .gateway_client import ClawdGatewayClient

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


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Clawd conversation entity."""
    gateway_client: ClawdGatewayClient = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities([ClawdConversationEntity(config_entry, gateway_client)])


class ClawdConversationEntity(conversation.ConversationEntity):
    """Clawd conversation entity."""

    _attr_has_entity_name = True
    _attr_name = "Clawd"
    _attr_supported_languages = "*"
    _attr_supports_streaming = False

    def __init__(
        self, config_entry: ConfigEntry, gateway_client: ClawdGatewayClient
    ) -> None:
        """Initialize the conversation entity."""
        self._config_entry = config_entry
        self._gateway_client = gateway_client
        self._attr_unique_id = config_entry.entry_id

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for the gateway."""
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": "Clawd Gateway",
            "manufacturer": "Clawdbot",
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
            "session_key": data.get("session_key"),
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
            # Send to Gateway agent
            response_text = await self._gateway_client.send_agent_request(
                user_message
            )

            # Add assistant response to chat log (keep emojis for display)
            chat_log.async_add_assistant_content_without_tools(
                conversation.AssistantContent(
                    agent_id=user_input.agent_id,
                    content=response_text,
                )
            )

            # Create intent response, optionally strip emojis for TTS
            intent_response = intent.IntentResponse(language=user_input.language)
            config = {**self._config_entry.data, **self._config_entry.options}
            should_strip = config.get(
                CONF_STRIP_EMOJIS, DEFAULT_STRIP_EMOJIS
            )
            speech_text = strip_emojis(response_text) if should_strip else response_text
            max_chars = config.get(
                CONF_TTS_MAX_CHARS, DEFAULT_TTS_MAX_CHARS
            )
            speech_text = trim_tts_text(speech_text, max_chars)
            intent_response.async_set_speech(speech_text)

            return conversation.ConversationResult(
                response=intent_response,
                conversation_id=user_input.conversation_id,
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
