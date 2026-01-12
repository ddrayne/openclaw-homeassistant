"""Conversation entity for Clawd integration."""

import logging

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .exceptions import (
    AgentExecutionError,
    GatewayConnectionError,
    GatewayTimeoutError,
)
from .gateway_client import ClawdGatewayClient

_LOGGER = logging.getLogger(__name__)


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

            # Add assistant response to chat log
            chat_log.async_add_message(
                conversation.AssistantContent(response=response_text)
            )

            # Create intent response
            intent_response = conversation.IntentResponse()
            intent_response.async_set_speech(response_text)

            return conversation.ConversationResult(
                response=intent_response,
                conversation_id=user_input.conversation_id,
            )

        except GatewayConnectionError as err:
            _LOGGER.error("Gateway connection error: %s", err)
            return self._create_error_result(
                "I'm having trouble connecting to the Gateway. Please check your configuration.",
                user_input.conversation_id,
            )

        except GatewayTimeoutError as err:
            _LOGGER.warning("Gateway timeout: %s", err)
            return self._create_error_result(
                "The response took too long. Please try again.",
                user_input.conversation_id,
            )

        except AgentExecutionError as err:
            _LOGGER.error("Agent execution error: %s", err)
            return self._create_error_result(
                "I encountered an error while processing your request. Please try again.",
                user_input.conversation_id,
            )

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected error in message handling")
            return self._create_error_result(
                "An unexpected error occurred. Please try again.",
                user_input.conversation_id,
            )

    def _create_error_result(
        self, message: str, conversation_id: str | None
    ) -> conversation.ConversationResult:
        """Create an error result."""
        intent_response = conversation.IntentResponse()
        intent_response.async_set_speech(message)
        return conversation.ConversationResult(
            response=intent_response,
            conversation_id=conversation_id,
        )
