"""The Clawd integration."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_STRIP_EMOJIS,
    CONF_TIMEOUT,
    CONF_SESSION_KEY,
    CONF_TTS_MAX_CHARS,
    CONF_USE_SSL,
    DEFAULT_SESSION_KEY,
    DEFAULT_STRIP_EMOJIS,
    DEFAULT_TIMEOUT,
    DEFAULT_TTS_MAX_CHARS,
    DEFAULT_USE_SSL,
    DOMAIN,
)
from .gateway_client import ClawdGatewayClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CONVERSATION]
HEALTH_CHECK_INTERVAL = timedelta(seconds=60)

_OPTION_KEYS = {
    CONF_TOKEN,
    CONF_USE_SSL,
    CONF_TIMEOUT,
    CONF_SESSION_KEY,
    CONF_STRIP_EMOJIS,
    CONF_TTS_MAX_CHARS,
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Clawd from a config entry."""
    _LOGGER.info("Setting up Clawd integration")

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

    # Create Gateway client with config from entry.data
    gateway_client = ClawdGatewayClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        token=options.get(CONF_TOKEN, entry.data.get(CONF_TOKEN)),
        use_ssl=options.get(
            CONF_USE_SSL, entry.data.get(CONF_USE_SSL, DEFAULT_USE_SSL)
        ),
        timeout=options.get(
            CONF_TIMEOUT, entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        ),
        session_key=options.get(
            CONF_SESSION_KEY,
            entry.data.get(CONF_SESSION_KEY, DEFAULT_SESSION_KEY),
        ),
    )

    # Connect to Gateway
    try:
        await gateway_client.connect()
        _LOGGER.info(
            "Connected to Clawd Gateway at %s:%s",
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
        )
    except Exception as err:
        _LOGGER.error("Failed to connect to Gateway: %s", err)
        return False

    # Store client in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = gateway_client

    # Forward setup to conversation platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _health_check(_now) -> None:
        if not gateway_client.connected:
            _LOGGER.warning("Gateway disconnected, attempting reconnect")
            await gateway_client.connect()
            return

        try:
            await gateway_client.health()
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("Gateway health check failed: %s", err)
            await gateway_client.disconnect()
            await gateway_client.connect()

    remove_listener = async_track_time_interval(
        hass, _health_check, HEALTH_CHECK_INTERVAL
    )
    entry.async_on_unload(remove_listener)

    # Register reload listener
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Clawd integration")

    # Get client before unloading
    gateway_client: ClawdGatewayClient = hass.data[DOMAIN][entry.entry_id]

    # Unload conversation platform
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Always disconnect and cleanup, even if unload failed
    await gateway_client.disconnect()
    hass.data[DOMAIN].pop(entry.entry_id, None)
    _LOGGER.info("Disconnected from Clawd Gateway")

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
