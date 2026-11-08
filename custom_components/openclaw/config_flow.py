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
    CONF_AGENT_ID,
    CONF_CLIENT_CERT,
    CONF_CLIENT_KEY,
    CONF_BACKGROUND_ENABLED,
    CONF_BACKGROUND_GRACE,
    CONF_HOLDING_PHRASE,
    CONF_MODEL,
    CONF_PROACTIVE_ENABLED,
    CONF_PROACTIVE_MODE,
    CONF_PROACTIVE_SATELLITE,
    CONF_SESSION_KEY,
    CONF_STREAMING_ENABLED,
    CONF_STRIP_EMOJIS,
    CONF_THINKING,
    CONF_TTS_MAX_CHARS,
    CONF_USE_SSL,
    DEFAULT_AGENT_ID,
    DEFAULT_BACKGROUND_ENABLED,
    DEFAULT_BACKGROUND_GRACE,
    DEFAULT_HOLDING_PHRASE,
    DEFAULT_HOST,
    DEFAULT_MODEL,
    DEFAULT_PORT,
    DEFAULT_PROACTIVE_ENABLED,
    DEFAULT_PROACTIVE_MODE,
    DEFAULT_SESSION_KEY,
    DEFAULT_STREAMING_ENABLED,
    DEFAULT_STRIP_EMOJIS,
    DEFAULT_THINKING,
    DEFAULT_TTS_MAX_CHARS,
    DEFAULT_TIMEOUT,
    DEFAULT_USE_SSL,
    DOMAIN,
    PROACTIVE_MODE_ANNOUNCE,
    PROACTIVE_MODE_START_CONVERSATION,
    entry_unique_id,
)
from .exceptions import (
    DevicePairingRequiredError,
    GatewayAuthenticationError,
    GatewayConnectionError,
    GatewayTLSConfigurationError,
    GatewayTimeoutError,
)
from .gateway import create_ssl_context
from .gateway_client import OpenClawGatewayClient

_LOGGER = logging.getLogger(__name__)


def _unique_id_for(data: dict[str, Any]) -> str:
    """Return the entry unique ID for config-flow or options data."""
    return entry_unique_id(
        data[CONF_HOST],
        data[CONF_PORT],
        data.get(CONF_AGENT_ID),
        data.get(CONF_SESSION_KEY, DEFAULT_SESSION_KEY),
    )


def _entry_title(base_title: str, data: dict[str, Any]) -> str:
    """Name the agent and session in the title when they are not the defaults.

    With several entries for one gateway (one per agent), the integrations
    page would otherwise list identical titles.
    """
    parts = []
    agent_id = (data.get(CONF_AGENT_ID) or "").strip()
    if agent_id:
        parts.append(agent_id)
    session_key = data.get(CONF_SESSION_KEY) or DEFAULT_SESSION_KEY
    if session_key != DEFAULT_SESSION_KEY:
        parts.append(f"session {session_key}")
    return f"{base_title} — {', '.join(parts)}" if parts else base_title


class InvalidMTLSConfiguration(ValueError):
    """mTLS requires TLS and a complete client certificate/key pair."""


def _validate_mtls_settings(data: dict[str, Any]) -> tuple[str | None, str | None]:
    """Check mTLS settings before attempting any Gateway connection."""
    cert = (data.get(CONF_CLIENT_CERT) or "").strip()
    key = (data.get(CONF_CLIENT_KEY) or "").strip()
    if bool(cert) != bool(key) or (cert and not data.get(CONF_USE_SSL, DEFAULT_USE_SSL)):
        raise InvalidMTLSConfiguration(
            "mTLS requires SSL and both client certificate and private key paths"
        )
    return cert or None, key or None


def _mtls_schema_fields(current: dict[str, Any] | None = None) -> dict:
    """Optional mTLS paths, clearable in options and reauth forms."""
    current = current or {}
    return {
        vol.Optional(
            CONF_CLIENT_CERT,
            description={"suggested_value": current.get(CONF_CLIENT_CERT) or ""},
        ): str,
        vol.Optional(
            CONF_CLIENT_KEY,
            description={"suggested_value": current.get(CONF_CLIENT_KEY) or ""},
        ): str,
    }


async def validate_connection(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the Gateway connection."""
    cert, key = _validate_mtls_settings(data)
    if cert and key:
        # Detect missing, unreadable or mismatched files before opening a socket.
        await asyncio.to_thread(create_ssl_context, cert, key)
    client = OpenClawGatewayClient(
        hass=hass,
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        token=data.get(CONF_TOKEN),
        use_ssl=data.get(CONF_USE_SSL, DEFAULT_USE_SSL),
        client_cert=cert,
        client_key=key,
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
        cert, key = _validate_mtls_settings(data)
        ssl_context = None
        if scheme == "https":
            ssl_context = await asyncio.to_thread(create_ssl_context, cert, key)
        async with session.get(
            url,
            headers=headers,
            timeout=ClientTimeout(total=10),
            ssl=ssl_context if ssl_context is not None else True,
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


def _background_schema_fields(current: dict[str, Any] | None = None) -> dict:
    """Background-work fields for the options form.

    When a request produces no content within the grace period, the entity
    speaks the holding phrase and announces the result later instead of
    timing out.
    """
    current = current or {}
    return {
        vol.Optional(
            CONF_BACKGROUND_ENABLED,
            default=current.get(
                CONF_BACKGROUND_ENABLED, DEFAULT_BACKGROUND_ENABLED
            ),
        ): bool,
        vol.Optional(
            CONF_BACKGROUND_GRACE,
            default=current.get(
                CONF_BACKGROUND_GRACE, DEFAULT_BACKGROUND_GRACE
            ),
        ): vol.All(int, vol.Range(min=3, max=60)),
        vol.Optional(
            CONF_HOLDING_PHRASE,
            default=current.get(CONF_HOLDING_PHRASE, DEFAULT_HOLDING_PHRASE),
        ): str,
    }


def _proactive_schema_fields(current: dict[str, Any] | None = None) -> dict:
    """Shared opt-in proactive-voice fields for the setup and options forms."""
    current = current or {}
    return {
        vol.Optional(
            CONF_PROACTIVE_ENABLED,
            default=current.get(
                CONF_PROACTIVE_ENABLED, DEFAULT_PROACTIVE_ENABLED
            ),
        ): bool,
        vol.Optional(
            CONF_PROACTIVE_SATELLITE,
            description={
                "suggested_value": current.get(CONF_PROACTIVE_SATELLITE)
            },
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="assist_satellite")
        ),
        vol.Optional(
            CONF_PROACTIVE_MODE,
            default=current.get(CONF_PROACTIVE_MODE, DEFAULT_PROACTIVE_MODE),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    PROACTIVE_MODE_ANNOUNCE,
                    PROACTIVE_MODE_START_CONVERSATION,
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }


class OpenClawConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenClaw."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Duplicates are checked in the session step: the same gateway may
            # be added once per agent and session (#13).

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
            except InvalidMTLSConfiguration:
                errors["base"] = "invalid_mtls"
            except GatewayTLSConfigurationError:
                errors["base"] = "invalid_mtls_files"
            except DevicePairingRequiredError:
                _LOGGER.info("Device pairing required — showing approval step")
                self._config_data = {
                    **user_input,
                    CONF_CLIENT_CERT: user_input.get(CONF_CLIENT_CERT) or None,
                    CONF_CLIENT_KEY: user_input.get(CONF_CLIENT_KEY) or None,
                }
                self._config_title = (
                    f"OpenClaw Gateway ({user_input[CONF_HOST]})"
                )
                return await self.async_step_pairing()
            except GatewayAuthenticationError as err:
                _LOGGER.warning("Authentication failed: %s", err)
                errors["base"] = "invalid_auth"
            except GatewayTimeoutError:
                errors["base"] = "timeout"
            except GatewayConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                self._config_data = {
                    **user_input,
                    CONF_CLIENT_CERT: user_input.get(CONF_CLIENT_CERT) or None,
                    CONF_CLIENT_KEY: user_input.get(CONF_CLIENT_KEY) or None,
                }
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
                **_mtls_schema_fields(),
                vol.Optional(
                    CONF_TIMEOUT, default=DEFAULT_TIMEOUT
                ): vol.All(int, vol.Range(min=5, max=600)),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_pairing(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle device pairing approval step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # User clicked Submit — retry the connection
            try:
                info = await validate_connection(
                    self.hass, self._config_data
                )
            except InvalidMTLSConfiguration:
                errors["base"] = "invalid_mtls"
            except GatewayTLSConfigurationError:
                errors["base"] = "invalid_mtls_files"
            except DevicePairingRequiredError:
                errors["base"] = "pairing_not_approved"
            except GatewayAuthenticationError as err:
                _LOGGER.warning("Authentication failed after pairing: %s", err)
                errors["base"] = "invalid_auth"
            except GatewayTimeoutError:
                errors["base"] = "timeout"
            except GatewayConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during pairing retry")
                errors["base"] = "unknown"
            else:
                self._config_title = info["title"]
                return await self.async_step_session()

        return self.async_show_form(
            step_id="pairing",
            data_schema=vol.Schema({}),
            errors=errors,
        )

    async def async_step_session(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle session selection and speech options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_AGENT_ID):
                user_input.pop(CONF_AGENT_ID, None)
            model = user_input.get(CONF_MODEL)
            if not model:
                user_input.pop(CONF_MODEL, None)
            thinking = user_input.get(CONF_THINKING)
            if not thinking:
                user_input.pop(CONF_THINKING, None)
            data = {**self._config_data, **user_input}
            await self.async_set_unique_id(_unique_id_for(data))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=_entry_title(self._config_title, data), data=data
            )

        current_session = self._config_data.get(
            CONF_SESSION_KEY, DEFAULT_SESSION_KEY
        )
        current_agent = self._config_data.get(CONF_AGENT_ID, DEFAULT_AGENT_ID) or ""
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
                vol.Optional(CONF_AGENT_ID, default=current_agent): str,
                vol.Optional(CONF_MODEL, default=current_model): str,
                vol.Optional(CONF_THINKING, default=current_thinking): thinking_selector,
                vol.Optional(
                    CONF_STRIP_EMOJIS, default=DEFAULT_STRIP_EMOJIS
                ): bool,
                vol.Optional(
                    CONF_TTS_MAX_CHARS, default=DEFAULT_TTS_MAX_CHARS
                ): vol.All(int, vol.Range(min=0, max=2000)),
                **_proactive_schema_fields(),
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
            for field in (CONF_CLIENT_CERT, CONF_CLIENT_KEY):
                if field in user_input:
                    test_data[field] = user_input[field] or None
            try:
                await validate_connection(self.hass, test_data)
            except InvalidMTLSConfiguration:
                errors["base"] = "invalid_mtls"
            except GatewayTLSConfigurationError:
                errors["base"] = "invalid_mtls_files"
            except DevicePairingRequiredError:
                _LOGGER.info("Device pairing required during reauth")
                errors["base"] = "pairing_required"
            except GatewayAuthenticationError as err:
                _LOGGER.warning("Authentication failed during reauth: %s", err)
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
                    data={**self._reauth_entry.data, **{
                        k: test_data[k] for k in user_input
                    }},
                    options={**self._reauth_entry.options, **{
                        k: test_data[k] for k in user_input
                    }},
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
                **_mtls_schema_fields(existing),
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
            except InvalidMTLSConfiguration:
                errors["base"] = "invalid_mtls"
            except GatewayTLSConfigurationError:
                errors["base"] = "invalid_mtls_files"
            except DevicePairingRequiredError:
                _LOGGER.info("Device pairing required during options update")
                errors["base"] = "pairing_required"
            except GatewayAuthenticationError as err:
                _LOGGER.warning("Authentication failed: %s", err)
                errors["base"] = "invalid_auth"
            except GatewayTimeoutError:
                errors["base"] = "timeout"
            except GatewayConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                unique_id = _unique_id_for(user_input)
                if self._unique_id_taken(unique_id):
                    errors["base"] = "already_configured"
                    return await self._async_show_options_form(errors)
                data = dict(user_input)
                data[CONF_CLIENT_CERT] = user_input.get(CONF_CLIENT_CERT) or None
                data[CONF_CLIENT_KEY] = user_input.get(CONF_CLIENT_KEY) or None
                options = {
                    CONF_TOKEN: user_input.get(CONF_TOKEN),
                    CONF_USE_SSL: user_input.get(CONF_USE_SSL, DEFAULT_USE_SSL),
                    CONF_CLIENT_CERT: user_input.get(CONF_CLIENT_CERT) or None,
                    CONF_CLIENT_KEY: user_input.get(CONF_CLIENT_KEY) or None,
                    CONF_TIMEOUT: user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                    CONF_SESSION_KEY: user_input.get(
                        CONF_SESSION_KEY, DEFAULT_SESSION_KEY
                    ),
                    CONF_AGENT_ID: user_input.get(CONF_AGENT_ID) or None,
                    CONF_MODEL: user_input.get(CONF_MODEL) or None,
                    CONF_THINKING: user_input.get(CONF_THINKING) or None,
                    CONF_STRIP_EMOJIS: user_input.get(
                        CONF_STRIP_EMOJIS, DEFAULT_STRIP_EMOJIS
                    ),
                    CONF_TTS_MAX_CHARS: user_input.get(
                        CONF_TTS_MAX_CHARS, DEFAULT_TTS_MAX_CHARS
                    ),
                    CONF_STREAMING_ENABLED: user_input.get(
                        CONF_STREAMING_ENABLED, DEFAULT_STREAMING_ENABLED
                    ),
                }
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=data,
                    options=options,
                    unique_id=unique_id,
                )
                return self.async_create_entry(title="", data={})

        return await self._async_show_options_form(errors)

    def _unique_id_taken(self, unique_id: str) -> bool:
        """Return whether another entry already uses this gateway/agent/session."""
        return any(
            entry.unique_id == unique_id
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if entry.entry_id != self.config_entry.entry_id
        )

    async def _async_show_options_form(self, errors: dict[str, str]) -> FlowResult:
        """Show the options form with the entry's current values."""
        current = {**self.config_entry.data, **self.config_entry.options}
        session_keys = await _async_fetch_sessions(self.hass, current)
        current_session = current.get(CONF_SESSION_KEY, DEFAULT_SESSION_KEY)
        current_agent = current.get(CONF_AGENT_ID, DEFAULT_AGENT_ID) or ""
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
                **_mtls_schema_fields(current),
                vol.Optional(
                    CONF_TIMEOUT,
                    default=current.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                ): vol.All(int, vol.Range(min=5, max=600)),
                vol.Optional(
                    CONF_SESSION_KEY, default=current_session
                ): session_selector,
                vol.Optional(CONF_AGENT_ID, default=current_agent): str,
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
                vol.Optional(
                    CONF_STREAMING_ENABLED,
                    default=current.get(
                        CONF_STREAMING_ENABLED, DEFAULT_STREAMING_ENABLED
                    ),
                ): bool,
                **_background_schema_fields(current),
                **_proactive_schema_fields(current),
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=data_schema, errors=errors
        )
