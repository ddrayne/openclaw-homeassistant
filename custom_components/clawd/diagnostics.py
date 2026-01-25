"""Diagnostics support for Clawd integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .gateway_client import ClawdGatewayClient


def _redact(data: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(data)
    if "token" in redacted and redacted["token"]:
        redacted["token"] = "REDACTED"
    return redacted
    return data


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    gateway_client: ClawdGatewayClient | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )

    diagnostics: dict[str, Any] = {
        "config": _redact(entry.data),
        "options": _redact(entry.options),
        "connected": gateway_client.connected if gateway_client else False,
    }

    if gateway_client:
        try:
            diagnostics["health"] = await gateway_client.health()
        except Exception as err:  # pragma: no cover - best-effort diagnostics
            diagnostics["health_error"] = str(err)

    return diagnostics
