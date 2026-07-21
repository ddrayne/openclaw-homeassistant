"""Diagnostics support for OpenClaw integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .gateway_client import OpenClawGatewayClient

_SAFE_HEALTH_FIELDS = (
    "status",
    "ok",
    "healthy",
    "version",
    "uptimeMs",
    "durationMs",
    "heartbeatSeconds",
)


def _redact(data: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(data)
    if "token" in redacted:
        redacted["token"] = "REDACTED"
    return redacted


def _collection_count(value: Any) -> int | None:
    """Return a safe count for a health collection."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, (dict, list, tuple, set)):
        return len(value)
    return None


def _summarize_health(health: Any) -> dict[str, Any]:
    """Return useful health data without session, account, or path details."""
    if not isinstance(health, dict):
        return {}

    summary = {
        key: health[key]
        for key in _SAFE_HEALTH_FIELDS
        if key in health
        and isinstance(health[key], (str, int, float, bool))
    }

    for source, target in (
        ("channels", "channel_count"),
        ("agents", "agent_count"),
        ("plugins", "plugin_count"),
    ):
        count = _collection_count(health.get(source))
        if count is not None:
            summary[target] = count

    sessions = health.get("sessions")
    if isinstance(sessions, dict):
        sessions = sessions.get("count")
    session_count = _collection_count(sessions)
    if session_count is not None:
        summary["session_count"] = session_count

    return summary


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    gateway_client: OpenClawGatewayClient | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )

    diagnostics: dict[str, Any] = {
        "config": _redact(entry.data),
        "options": _redact(entry.options),
        "connected": gateway_client.connected if gateway_client else False,
    }

    if gateway_client:
        try:
            diagnostics["health"] = _summarize_health(
                await gateway_client.health()
            )
        except Exception as err:  # pragma: no cover - best-effort diagnostics
            diagnostics["health_error"] = type(err).__name__

    return diagnostics
