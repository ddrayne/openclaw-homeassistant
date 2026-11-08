"""The OpenClaw integration."""

import inspect
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, ConfigEntryError
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue, async_delete_issue
from homeassistant.helpers.service import async_register_admin_service

from .const import (
    CONF_AGENT_ID,
    CONF_MODEL,
    CONF_SESSION_KEY,
    CONF_STRIP_EMOJIS,
    CONF_THINKING,
    CONF_TIMEOUT,
    CONF_TTS_MAX_CHARS,
    CONF_USE_SSL,
    DEFAULT_AGENT_ID,
    DEFAULT_MODEL,
    DEFAULT_SESSION_KEY,
    DEFAULT_STRIP_EMOJIS,
    DEFAULT_THINKING,
    DEFAULT_TIMEOUT,
    DEFAULT_TTS_MAX_CHARS,
    DEFAULT_USE_SSL,
    DOMAIN,
    UPGRADE_AUTH_RETRY_ATTEMPTS,
    CONF_CLIENT_CERT,
    CONF_CLIENT_KEY,
    entry_unique_id,
)
from .exceptions import (
    DevicePairingRequiredError,
    GatewayAuthenticationError,
    GatewayConnectionError,
    GatewayTimeoutError,
    GatewayUpgradeRejectedError,
    GatewayTLSConfigurationError,
)
from .gateway_client import OpenClawGatewayClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.CONVERSATION, Platform.SENSOR]
SERVICE_RECONNECT = "reconnect"
SERVICE_SET_SESSION = "set_session"
_SERVICE_REGISTERED = "_service_registered"
_PLATFORMS_LOADED = "_platforms_loaded"
# Consecutive setup attempts whose connection was refused with HTTP 401/403,
# per entry. Kept outside hass.data[DOMAIN], which only holds clients and flags.
_SETUP_UPGRADE_REJECTIONS = f"{DOMAIN}_setup_upgrade_rejections"
_RECONNECT_SCHEMA = vol.Schema({vol.Optional("entry_id"): str})
_SESSION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SESSION_KEY): vol.All(str, vol.Length(min=1)),
        vol.Optional("entry_id"): str,
    }
)

_OPTION_KEYS = {
    CONF_TOKEN,
    CONF_USE_SSL,
    CONF_CLIENT_CERT,
    CONF_CLIENT_KEY,
    CONF_TIMEOUT,
    CONF_SESSION_KEY,
    CONF_AGENT_ID,
    CONF_MODEL,
    CONF_THINKING,
    CONF_STRIP_EMOJIS,
    CONF_TTS_MAX_CHARS,
}


async def _async_disconnect_quietly(
    gateway_client: OpenClawGatewayClient, entry: ConfigEntry
) -> None:
    """Stop a client whose setup failed without masking the real error."""
    try:
        await gateway_client.disconnect()
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception(
            "Error disconnecting OpenClaw Gateway during setup of %s",
            entry.entry_id,
        )


def _async_migrate_unique_id(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Scope the entry's unique ID to its agent and session (#13).

    Entries used to be unique per ``host:port``. An entry already set to a
    specific agent would then block adding the same gateway again for another
    agent, so move it to the agent-scoped ID unless another entry holds it.
    """
    config = {**entry.data, **entry.options}
    unique_id = entry_unique_id(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        config.get(CONF_AGENT_ID),
        config.get(CONF_SESSION_KEY),
    )
    if entry.unique_id == unique_id:
        return
    if any(
        other.unique_id == unique_id
        for other in hass.config_entries.async_entries(DOMAIN)
        if other.entry_id != entry.entry_id
    ):
        _LOGGER.debug(
            "Not migrating unique ID of %s: %s is already in use",
            entry.entry_id,
            unique_id,
        )
        return
    hass.config_entries.async_update_entry(entry, unique_id=unique_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OpenClaw from a config entry."""
    _LOGGER.info("Setting up OpenClaw integration")

    # Migrate option-like keys from data to options for existing entries.
    if not entry.options:
        migrated = {
            key: entry.data.get(key)
            for key in _OPTION_KEYS
            if key in entry.data
        }
        if migrated:
            hass.config_entries.async_update_entry(entry, options=migrated)

    options = entry.options
    _async_migrate_unique_id(hass, entry)

    # Create Gateway client with config from entry.data
    gateway_client = OpenClawGatewayClient(
        hass=hass,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        token=options.get(CONF_TOKEN, entry.data.get(CONF_TOKEN)),
        use_ssl=options.get(
            CONF_USE_SSL, entry.data.get(CONF_USE_SSL, DEFAULT_USE_SSL)
        ),
        client_cert=options.get(
            CONF_CLIENT_CERT, entry.data.get(CONF_CLIENT_CERT)
        ),
        client_key=options.get(
            CONF_CLIENT_KEY, entry.data.get(CONF_CLIENT_KEY)
        ),
        timeout=options.get(
            CONF_TIMEOUT, entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        ),
        session_key=options.get(
            CONF_SESSION_KEY,
            entry.data.get(CONF_SESSION_KEY, DEFAULT_SESSION_KEY),
        ),
        agent_id=options.get(
            CONF_AGENT_ID, entry.data.get(CONF_AGENT_ID, DEFAULT_AGENT_ID)
        ),
        model=options.get(CONF_MODEL, entry.data.get(CONF_MODEL, DEFAULT_MODEL)),
        thinking=options.get(
            CONF_THINKING, entry.data.get(CONF_THINKING, DEFAULT_THINKING)
        ),
    )

    # Connect to Gateway
    try:
        await gateway_client.connect()
        hass.data.get(_SETUP_UPGRADE_REJECTIONS, {}).pop(entry.entry_id, None)
        _LOGGER.info(
            "Connected to OpenClaw Gateway at %s:%s",
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
        )
    except Exception as err:  # pylint: disable=broad-except
        # Stop the connection loop before Home Assistant retries setup: it is
        # already retrying on its own, and a client that never reached
        # ``hass.data`` would otherwise keep reconnecting untracked while the
        # next setup attempt creates another one.
        await _async_disconnect_quietly(gateway_client, entry)
        if isinstance(err, GatewayTLSConfigurationError):
            raise ConfigEntryError(
                f"Invalid Gateway TLS configuration: {err}"
            ) from err
        if isinstance(err, GatewayAuthenticationError):
            raise ConfigEntryAuthFailed(err) from err
        if isinstance(err, GatewayUpgradeRejectedError):
            # A 401/403 on the upgrade is retried because a restarting proxy
            # can reject a valid token. Setup only waits a few seconds and
            # each retry builds a fresh client, so the connection loop's own
            # retry budget would restart every attempt and a wrong token would
            # never surface. Count rejections across attempts instead.
            rejections = hass.data.setdefault(_SETUP_UPGRADE_REJECTIONS, {})
            count = rejections.get(entry.entry_id, 0) + 1
            if count > UPGRADE_AUTH_RETRY_ATTEMPTS:
                rejections.pop(entry.entry_id, None)
                raise ConfigEntryAuthFailed(err) from err
            rejections[entry.entry_id] = count
            raise ConfigEntryNotReady(err) from err
        if isinstance(err, (GatewayConnectionError, GatewayTimeoutError)):
            raise ConfigEntryNotReady(err) from err
        raise ConfigEntryNotReady(err) from err

    # Register runtime fatal error callback for repair issues
    def _on_fatal_error(err: Exception) -> None:
        if isinstance(err, DevicePairingRequiredError):
            async_create_issue(
                hass,
                DOMAIN,
                "device_pairing_required",
                is_fixable=False,
                severity=IssueSeverity.WARNING,
                translation_key="device_pairing_required",
            )
        elif isinstance(err, GatewayAuthenticationError):
            async_create_issue(
                hass,
                DOMAIN,
                "gateway_auth_failed",
                is_fixable=False,
                severity=IssueSeverity.ERROR,
                translation_key="gateway_auth_failed",
            )

    gateway_client._gateway._on_fatal_error = _on_fatal_error

    # Clear any stale repair issue from a previous session
    async_delete_issue(hass, DOMAIN, "gateway_auth_failed")

    # Store client in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = gateway_client

    if not hass.data[DOMAIN].get(_SERVICE_REGISTERED):
        async def _async_handle_reconnect(call) -> None:
            entry_id = call.data.get("entry_id")
            clients = hass.data.get(DOMAIN, {})

            if entry_id:
                target = clients.get(entry_id)
                if not target:
                    _LOGGER.warning("Reconnect requested for unknown entry: %s", entry_id)
                    return
                targets = [(entry_id, target)]
            else:
                targets = [
                    (key, client)
                    for key, client in clients.items()
                    if key not in (_SERVICE_REGISTERED, _PLATFORMS_LOADED)
                ]

            for key, client in targets:
                try:
                    await client.disconnect()
                    await client.connect()
                except GatewayAuthenticationError as err:
                    _LOGGER.error(
                        "Reconnect for entry %s failed: the Gateway rejected "
                        "authentication (%s). Update the token under Settings "
                        "> Devices & Services > OpenClaw > Configure.",
                        key,
                        err,
                    )
                except Exception as err:  # pylint: disable=broad-except
                    # ``connect()`` gives up waiting after a few seconds while
                    # its connection loop keeps retrying, so a still-recovering
                    # Gateway is not a service failure - and one entry must not
                    # stop the remaining entries from being reconnected.
                    _LOGGER.warning(
                        "Reconnect for entry %s is still in progress: %s", key, err
                    )

        async_register_admin_service(
            hass,
            DOMAIN,
            SERVICE_RECONNECT,
            _async_handle_reconnect,
            _RECONNECT_SCHEMA,
        )

        async def _async_handle_set_session(call) -> None:
            entry_id = call.data.get("entry_id")
            session_key = call.data[CONF_SESSION_KEY]
            clients = hass.data.get(DOMAIN, {})

            if entry_id:
                target = clients.get(entry_id)
                if not target:
                    _LOGGER.warning(
                        "Session update requested for unknown entry: %s",
                        entry_id,
                    )
                    return
                targets = [target]
            else:
                targets = [
                    client
                    for key, client in clients.items()
                    if key not in (_SERVICE_REGISTERED, _PLATFORMS_LOADED)
                ]

            for client in targets:
                client.set_session_key(session_key)

        async_register_admin_service(
            hass,
            DOMAIN,
            SERVICE_SET_SESSION,
            _async_handle_set_session,
            _SESSION_SCHEMA,
        )
        hass.data[DOMAIN][_SERVICE_REGISTERED] = True

    # Forward setup to platforms (guard against duplicate setup attempts)
    platforms_loaded = hass.data[DOMAIN].setdefault(_PLATFORMS_LOADED, set())
    if entry.entry_id not in platforms_loaded:
        try:
            await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        except Exception:
            _LOGGER.exception("Failed to set up platforms")
            await gateway_client.disconnect()
            hass.data[DOMAIN].pop(entry.entry_id, None)
            return False
        platforms_loaded.add(entry.entry_id)

    # Register reload listener
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading OpenClaw integration")

    # Get client before unloading
    gateway_client: OpenClawGatewayClient | None = (
        hass.data.get(DOMAIN, {}).get(entry.entry_id)
    )
    if gateway_client is None:
        _LOGGER.debug(
            "Entry not found in hass.data during unload: %s", entry.entry_id
        )

    # Unload platforms only if they were loaded.
    platforms_loaded = hass.data.get(DOMAIN, {}).get(_PLATFORMS_LOADED, set())
    if entry.entry_id in platforms_loaded:
        try:
            unload_result = hass.config_entries.async_unload_platforms(
                entry, PLATFORMS
            )
            if inspect.isawaitable(unload_result):
                unload_ok = await unload_result
            else:
                unload_ok = bool(unload_result) if unload_result is not None else True
        except ValueError:
            _LOGGER.warning(
                "Conversation platform was not loaded for entry: %s", entry.entry_id
            )
            unload_ok = True
        if unload_ok:
            platforms_loaded.discard(entry.entry_id)
    else:
        unload_ok = True

    # Always disconnect and cleanup, even if unload failed. Teardown must not be
    # able to fail the unload: an exception here used to make Home Assistant
    # abandon the reload and ask for a restart instead.
    if gateway_client is not None:
        try:
            await gateway_client.disconnect()
            _LOGGER.info("Disconnected from OpenClaw Gateway")
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Error disconnecting from OpenClaw Gateway")
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry.

    Delegate to Home Assistant's config-entry machinery rather than calling
    async_unload_entry/async_setup_entry directly. The manual path bypassed the
    entry's async_on_unload cleanup, so each reload leaked another update
    listener; the next options change then fired several concurrent reloads and
    platforms were set up twice ("already been setup").
    """
    await hass.config_entries.async_reload(entry.entry_id)
