"""The Clawd integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN, CONF_TIMEOUT, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_USE_SSL, DEFAULT_TIMEOUT, DEFAULT_USE_SSL, DOMAIN
from .gateway_client import ClawdGatewayClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CONVERSATION]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Clawd from a config entry."""
    _LOGGER.info("Setting up Clawd integration")

    # Create Gateway client with config from entry.data
    gateway_client = ClawdGatewayClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        token=entry.data.get(CONF_TOKEN),
        use_ssl=entry.data.get(CONF_USE_SSL, DEFAULT_USE_SSL),
        timeout=entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
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
