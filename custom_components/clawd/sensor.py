"""Usage sensors for the Clawd integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from aiohttp import ContentTypeError

from .const import (
    CONF_SESSION_KEY,
    CONF_TOKEN,
    CONF_USE_SSL,
    DEFAULT_SESSION_KEY,
    DEFAULT_USE_SSL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_UPDATE_INTERVAL = timedelta(seconds=60)


async def _async_fetch_session_status(
    hass: HomeAssistant,
    host: str,
    port: int,
    use_ssl: bool,
    token: str | None,
    session_key: str,
) -> dict[str, Any]:
    """Fetch session status from the Gateway."""
    scheme = "https" if use_ssl else "http"
    url = f"{scheme}://{host}:{port}/sessions/{session_key}/status"
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    session = aiohttp_client.async_get_clientsession(hass)
    async with session.get(url, headers=headers, timeout=10) as resp:
        if resp.status != 200:
            raise UpdateFailed(
                f"Session status request failed with status {resp.status}"
            )
        try:
            payload = await resp.json()
        except ContentTypeError as err:
            raise UpdateFailed(
                f"Session status response was not JSON ({resp.content_type})"
            ) from err

    if not payload.get("ok", True):
        raise UpdateFailed(payload.get("error", "Session status request failed"))

    return payload


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Clawd usage sensors."""
    data = {**entry.data, **entry.options}
    host = data["host"]
    port = data["port"]
    use_ssl = data.get(CONF_USE_SSL, DEFAULT_USE_SSL)
    token = data.get(CONF_TOKEN)
    session_key = data.get(CONF_SESSION_KEY, DEFAULT_SESSION_KEY)

    async def _async_update() -> dict[str, Any]:
        client = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        active_session_key = session_key
        if client and getattr(client, "session_key", None):
            active_session_key = client.session_key
        return await _async_fetch_session_status(
            hass, host, port, use_ssl, token, active_session_key
        )

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_session_status_{entry.entry_id}",
        update_method=_async_update,
        update_interval=_UPDATE_INTERVAL,
    )
    try:
        await coordinator.async_refresh()
    except Exception as err:  # pragma: no cover - best effort startup
        _LOGGER.warning("Session status refresh failed: %s", err)

    sensors = [
        ClawdSessionSensor(
            coordinator,
            entry.entry_id,
            "Tokens Used",
            "total_tokens",
            "tokens",
            SensorStateClass.TOTAL_INCREASING,
            _value_from_usage("totalTokens"),
        ),
        ClawdSessionSensor(
            coordinator,
            entry.entry_id,
            "Estimated Cost",
            "estimated_cost",
            "$",
            SensorStateClass.TOTAL_INCREASING,
            _value_from_usage("estimatedCost"),
        ),
        ClawdSessionSensor(
            coordinator,
            entry.entry_id,
            "Message Count",
            "message_count",
            "messages",
            SensorStateClass.TOTAL_INCREASING,
            _value_from_usage("messageCount"),
        ),
    ]

    async_add_entities(sensors)


def _value_from_usage(key: str):
    """Build a getter for a usage field."""

    def _getter(data: dict[str, Any]) -> int | float | None:
        usage = data.get("usage", {})
        return usage.get(key)

    return _getter


class ClawdSessionSensor(CoordinatorEntity, SensorEntity):
    """Sensor for Clawd session usage stats."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry_id: str,
        name: str,
        unique_suffix: str,
        unit: str,
        state_class: SensorStateClass | None,
        value_getter,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = f"Clawd {name}"
        self._attr_unique_id = f"{entry_id}_{unique_suffix}"
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._value_getter = value_getter
        self._entry_id = entry_id

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for the gateway."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "Clawd Gateway",
            "manufacturer": "Clawdbot",
            "model": "Gateway",
        }

    @property
    def native_value(self) -> int | float | None:
        """Return the sensor value."""
        data = self.coordinator.data or {}
        return self._value_getter(data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        data = self.coordinator.data or {}
        return {
            "session_key": data.get("sessionKey"),
            "model": data.get("model"),
        }
