"""Config flow for Clawd integration."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN, CONF_TIMEOUT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_SESSION_KEY,
    CONF_STRIP_EMOJIS,
    CONF_TTS_MAX_CHARS,
    CONF_USE_SSL,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_SESSION_KEY,
    DEFAULT_STRIP_EMOJIS,
    DEFAULT_TTS_MAX_CHARS,
    DEFAULT_TIMEOUT,
    DEFAULT_USE_SSL,
    DOMAIN,
)
from .exceptions import (
    GatewayAuthenticationError,
    GatewayConnectionError,
    GatewayTimeoutError,
)
from .gateway_client import ClawdGatewayClient

_LOGGER = logging.getLogger(__name__)


async def validate_connection(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the Gateway connection."""
    client = ClawdGatewayClient(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        token=data.get(CONF_TOKEN),
        use_ssl=data.get(CONF_USE_SSL, DEFAULT_USE_SSL),
        timeout=data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
        session_key=data.get(CONF_SESSION_KEY, DEFAULT_SESSION_KEY),
    )

    try:
        # Try to connect
        await client.connect()

        # Test with a health check
        await client.health()

        # Return validated data
        return {"title": f"Clawd Gateway ({data[CONF_HOST]})"}

    finally:
        await client.disconnect()


class ClawdConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Clawd."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Check if already configured
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
            )
            self._abort_if_unique_id_configured()

            # Security warning for non-SSL remote connections
            if (
                not user_input.get(CONF_USE_SSL, DEFAULT_USE_SSL)
                and user_input[CONF_HOST]
                not in ("localhost", "127.0.0.1", "::1")
            ):
                _LOGGER.warning(
                    "Connecting to remote Gateway without SSL is not recommended"
                )

            try:
                info = await validate_connection(self.hass, user_input)
            except GatewayAuthenticationError:
                errors["base"] = "invalid_auth"
            except GatewayTimeoutError:
                errors["base"] = "timeout"
            except GatewayConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=info["title"], data=user_input
                )

        # Show form
        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    int, vol.Range(min=1, max=65535)
                ),
                vol.Optional(CONF_TOKEN): str,
                vol.Optional(
                    CONF_USE_SSL, default=DEFAULT_USE_SSL
                ): bool,
                vol.Optional(
                    CONF_TIMEOUT, default=DEFAULT_TIMEOUT
                ): vol.All(int, vol.Range(min=5, max=300)),
                vol.Optional(
                    CONF_SESSION_KEY, default=DEFAULT_SESSION_KEY
                ): str,
                vol.Optional(
                    CONF_STRIP_EMOJIS, default=DEFAULT_STRIP_EMOJIS
                ): bool,
                vol.Optional(
                    CONF_TTS_MAX_CHARS, default=DEFAULT_TTS_MAX_CHARS
                ): vol.All(int, vol.Range(min=0, max=2000)),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return ClawdOptionsFlowHandler()


class ClawdOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Clawd options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Security warning for non-SSL remote connections
            if (
                not user_input.get(CONF_USE_SSL, DEFAULT_USE_SSL)
                and user_input[CONF_HOST]
                not in ("localhost", "127.0.0.1", "::1")
            ):
                _LOGGER.warning(
                    "Connecting to remote Gateway without SSL is not recommended"
                )

            try:
                # Validate new settings
                await validate_connection(self.hass, user_input)
            except GatewayAuthenticationError:
                errors["base"] = "invalid_auth"
            except GatewayTimeoutError:
                errors["base"] = "timeout"
            except GatewayConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                data = dict(user_input)
                options = {
                    CONF_TOKEN: user_input.get(CONF_TOKEN),
                    CONF_USE_SSL: user_input.get(CONF_USE_SSL, DEFAULT_USE_SSL),
                    CONF_TIMEOUT: user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                    CONF_SESSION_KEY: user_input.get(
                        CONF_SESSION_KEY, DEFAULT_SESSION_KEY
                    ),
                    CONF_STRIP_EMOJIS: user_input.get(
                        CONF_STRIP_EMOJIS, DEFAULT_STRIP_EMOJIS
                    ),
                    CONF_TTS_MAX_CHARS: user_input.get(
                        CONF_TTS_MAX_CHARS, DEFAULT_TTS_MAX_CHARS
                    ),
                }
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=data,
                    options=options,
                    unique_id=f"{data[CONF_HOST]}:{data[CONF_PORT]}",
                )
                return self.async_create_entry(title="", data={})

        # Show form with current values
        current = {**self.config_entry.data, **self.config_entry.options}
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST, default=current.get(CONF_HOST, DEFAULT_HOST)
                ): str,
                vol.Required(
                    CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)
                ): vol.All(int, vol.Range(min=1, max=65535)),
                vol.Optional(CONF_TOKEN, default=current.get(CONF_TOKEN)): str,
                vol.Optional(
                    CONF_USE_SSL,
                    default=current.get(CONF_USE_SSL, DEFAULT_USE_SSL),
                ): bool,
                vol.Optional(
                    CONF_TIMEOUT,
                    default=current.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                ): vol.All(int, vol.Range(min=5, max=300)),
                vol.Optional(
                    CONF_SESSION_KEY,
                    default=current.get(CONF_SESSION_KEY, DEFAULT_SESSION_KEY),
                ): str,
                vol.Optional(
                    CONF_STRIP_EMOJIS,
                    default=current.get(CONF_STRIP_EMOJIS, DEFAULT_STRIP_EMOJIS),
                ): bool,
                vol.Optional(
                    CONF_TTS_MAX_CHARS,
                    default=current.get(
                        CONF_TTS_MAX_CHARS, DEFAULT_TTS_MAX_CHARS
                    ),
                ): vol.All(int, vol.Range(min=0, max=2000)),
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=data_schema, errors=errors
        )
