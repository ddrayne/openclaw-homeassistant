"""Config flow for OpenClaw integration."""

import asyncio
import logging
from typing import Any

from aiohttp import ClientTimeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN, CONF_TIMEOUT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client, selector

from .const import (
    CONF_MODEL,
    CONF_SESSION_KEY,
    CONF_STRIP_EMOJIS,
    CONF_THINKING,
    CONF_TTS_MAX_CHARS,
    CONF_USE_SSL,
    DEFAULT_HOST,
    DEFAULT_MODEL,
    DEFAULT_PORT,
    DEFAULT_SESSION_KEY,
    DEFAULT_STRIP_EMOJIS,
    DEFAULT_THINKING,
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
from .gateway_client import OpenClawGatewayClient

_LOGGER = logging.getLogger(__name__)


async def validate_connection(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the Gateway connection."""
    client = OpenClawGatewayClient(
        hass=hass,
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
        return {"title": f"OpenClaw Gateway ({data[CONF_HOST]})"}

    finally:
        await client.disconnect()


async def _async_fetch_sessions(
    hass: HomeAssistant, data: dict[str, Any]
) -> list[str]:
    """Fetch available session keys from the Gateway."""
    scheme = "https" if data.get(CONF_USE_SSL, DEFAULT_USE_SSL) else "http"
    url = f"{scheme}://{data[CONF_HOST]}:{data[CONF_PORT]}/sessions"
    headers: dict[str, str] = {}
    token = data.get(CONF_TOKEN)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    session = aiohttp_client.async_get_clientsession(hass)
    try:
        async with session.get(
            url, headers=headers, timeout=ClientTimeout(total=10)
        ) as resp:
            if resp.status != 200:
                _LOGGER.debug(
                    "Session list request failed with status %s", resp.status
                )
                return []
            payload = await resp.json()
    except (asyncio.TimeoutError, OSError) as err:
        _LOGGER.debug("Session list request failed: %s", err)
        return []
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.debug("Session list request failed: %s", err)
        return []

    sessions = payload.get("sessions", [])
    session_keys: list[str] = []
    for item in sessions:
        key = item.get("sessionKey") or item.get("session_key")
        if key:
            session_keys.append(key)
    return session_keys


def _build_session_selector(
    session_keys: list[str], default_value: str
) -> selector.SelectSelector | type[str]:
    """Build a session selector when sessions are available."""
    ordered: list[str] = []
    for key in (default_value, DEFAULT_SESSION_KEY, *session_keys):
        if key and key not in ordered:
            ordered.append(key)

    options = [{"label": key, "value": key} for key in ordered]
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.DROPDOWN,
            custom_value=True,
        )
    )

def _build_thinking_selector() -> selector.SelectSelector:
    """Build a thinking mode selector."""
    options = [
        {"label": "Default", "value": ""},
        {"label": "Off", "value": "off"},
        {"label": "Low", "value": "low"},
        {"label": "Medium", "value": "medium"},
        {"label": "High", "value": "high"},
    ]
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.DROPDOWN,
            custom_value=True,
        )
    )


class OpenClawConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenClaw."""

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
                self._config_data = user_input
                self._config_title = info["title"]
                return await self.async_step_session()

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
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_session(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle session selection and speech options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            model = user_input.get(CONF_MODEL)
            if not model:
                user_input.pop(CONF_MODEL, None)
            thinking = user_input.get(CONF_THINKING)
            if not thinking:
                user_input.pop(CONF_THINKING, None)
            data = {**self._config_data, **user_input}
            return self.async_create_entry(
                title=self._config_title, data=data
            )

        current_session = self._config_data.get(
            CONF_SESSION_KEY, DEFAULT_SESSION_KEY
        )
        current_model = self._config_data.get(CONF_MODEL, DEFAULT_MODEL) or ""
        current_thinking = (
            self._config_data.get(CONF_THINKING, DEFAULT_THINKING) or ""
        )
        session_keys = await _async_fetch_sessions(self.hass, self._config_data)
        session_selector = _build_session_selector(session_keys, current_session)
        thinking_selector = _build_thinking_selector()

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_SESSION_KEY, default=current_session): session_selector,
                vol.Optional(CONF_MODEL, default=current_model): str,
                vol.Optional(CONF_THINKING, default=current_thinking): thinking_selector,
                vol.Optional(
                    CONF_STRIP_EMOJIS, default=DEFAULT_STRIP_EMOJIS
                ): bool,
                vol.Optional(
                    CONF_TTS_MAX_CHARS, default=DEFAULT_TTS_MAX_CHARS
                ): vol.All(int, vol.Range(min=0, max=2000)),
            }
        )

        return self.async_show_form(
            step_id="session", data_schema=data_schema, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Handle re-authentication when the gateway token becomes invalid."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-auth confirmation form."""
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None
        existing = {**self._reauth_entry.data, **self._reauth_entry.options}

        if user_input is not None:
            # Merge existing data with new user input for validation
            test_data = {**existing, **user_input}
            try:
                await validate_connection(self.hass, test_data)
            except GatewayAuthenticationError:
                errors["base"] = "invalid_auth"
            except GatewayTimeoutError:
                errors["base"] = "timeout"
            except GatewayConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during reauth")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={**self._reauth_entry.data, **user_input},
                    options={**self._reauth_entry.options, **user_input},
                )
                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST, default=existing.get(CONF_HOST, DEFAULT_HOST)
                ): str,
                vol.Required(
                    CONF_PORT, default=existing.get(CONF_PORT, DEFAULT_PORT)
                ): vol.All(int, vol.Range(min=1, max=65535)),
                vol.Optional(
                    CONF_TOKEN, default=existing.get(CONF_TOKEN)
                ): str,
                vol.Optional(
                    CONF_USE_SSL,
                    default=existing.get(CONF_USE_SSL, DEFAULT_USE_SSL),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OpenClawOptionsFlowHandler()


class OpenClawOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle OpenClaw options."""

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
                CONF_MODEL: user_input.get(CONF_MODEL) or None,
                CONF_THINKING: user_input.get(CONF_THINKING) or None,
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
        session_keys = await _async_fetch_sessions(self.hass, current)
        current_session = current.get(CONF_SESSION_KEY, DEFAULT_SESSION_KEY)
        current_model = current.get(CONF_MODEL, DEFAULT_MODEL) or ""
        current_thinking = current.get(CONF_THINKING, DEFAULT_THINKING) or ""
        session_selector = _build_session_selector(
            session_keys, current_session
        )
        thinking_selector = _build_thinking_selector()

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
                    CONF_SESSION_KEY, default=current_session
                ): session_selector,
                vol.Optional(CONF_MODEL, default=current_model): str,
                vol.Optional(CONF_THINKING, default=current_thinking): thinking_selector,
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
