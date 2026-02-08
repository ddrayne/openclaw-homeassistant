"""WS-backed diagnostic sensors for the OpenClaw integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN
from .gateway_client import OpenClawGatewayClient

_LOGGER = logging.getLogger(__name__)

_UPDATE_INTERVAL = timedelta(seconds=60)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OpenClaw diagnostic sensors."""
    client: OpenClawGatewayClient = hass.data[DOMAIN][entry.entry_id]

    async def _async_update_status() -> dict[str, Any]:
        if not client.connected:
            raise UpdateFailed("Gateway not connected")
        try:
            return await client.status()
        except Exception as err:
            raise UpdateFailed(f"Status request failed: {err}") from err

    async def _async_update_health() -> dict[str, Any]:
        if not client.connected:
            raise UpdateFailed("Gateway not connected")
        try:
            return await client.health()
        except Exception as err:
            raise UpdateFailed(f"Health request failed: {err}") from err

    status_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_status_{entry.entry_id}",
        update_method=_async_update_status,
        update_interval=_UPDATE_INTERVAL,
    )

    health_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_health_{entry.entry_id}",
        update_method=_async_update_health,
        update_interval=_UPDATE_INTERVAL,
    )

    # Best-effort initial fetch — sensors will retry on next cycle
    for coordinator in (status_coordinator, health_coordinator):
        try:
            await coordinator.async_refresh()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Initial %s refresh failed, will retry", coordinator.name)

    async_add_entities([
        OpenClawUptimeSensor(status_coordinator, entry.entry_id, client),
        OpenClawConnectedClientsSensor(entry.entry_id, client),
        OpenClawHealthSensor(health_coordinator, entry.entry_id, client),
    ])


class OpenClawUptimeSensor(CoordinatorEntity, SensorEntity):
    """Gateway uptime in seconds."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "s"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:timer-outline"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry_id: str,
        client: OpenClawGatewayClient,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._entry_id = entry_id
        self._attr_name = "OpenClaw Gateway Uptime"
        self._attr_unique_id = f"{entry_id}_gateway_uptime"

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "OpenClaw Gateway",
            "manufacturer": "OpenClaw",
            "model": "Gateway",
        }

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data or {}
        uptime_ms = data.get("uptimeMs")
        if uptime_ms is not None:
            return round(uptime_ms / 1000, 1)
        # Fallback to connect snapshot
        snapshot = self._client.connect_snapshot.get("snapshot", {})
        snap_uptime = snapshot.get("uptimeMs")
        if snap_uptime is not None:
            return round(snap_uptime / 1000, 1)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "state_version": data.get("stateVersion"),
            "sessions": data.get("sessions"),
        }


class OpenClawConnectedClientsSensor(SensorEntity):
    """Number of connected gateway clients from presence data."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "clients"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:account-multiple"

    def __init__(self, entry_id: str, client: OpenClawGatewayClient) -> None:
        self._client = client
        self._entry_id = entry_id
        self._attr_name = "OpenClaw Connected Clients"
        self._attr_unique_id = f"{entry_id}_connected_clients"

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "OpenClaw Gateway",
            "manufacturer": "OpenClaw",
            "model": "Gateway",
        }

    @property
    def native_value(self) -> int | None:
        presence = self._client.presence
        if not presence:
            return None
        clients = presence.get("clients")
        if isinstance(clients, list):
            return len(clients)
        if isinstance(clients, int):
            return clients
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        presence = self._client.presence
        attrs: dict[str, Any] = {}
        clients = presence.get("clients")
        if isinstance(clients, list):
            attrs["client_list"] = clients
        return attrs


class OpenClawHealthSensor(CoordinatorEntity, SensorEntity):
    """Gateway health status."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:heart-pulse"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry_id: str,
        client: OpenClawGatewayClient,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._entry_id = entry_id
        self._attr_name = "OpenClaw Gateway Health"
        self._attr_unique_id = f"{entry_id}_gateway_health"

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "OpenClaw Gateway",
            "manufacturer": "OpenClaw",
            "model": "Gateway",
        }

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data or {}
        status = data.get("status")
        if status is not None:
            return status
        # Fallback to connect snapshot
        snapshot = self._client.connect_snapshot.get("snapshot", {})
        return snapshot.get("health", {}).get("status")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        attrs: dict[str, Any] = {}
        for key in ("version", "uptimeMs", "memoryUsage", "cpuUsage"):
            val = data.get(key)
            if val is not None:
                attrs[key] = val
        return attrs
