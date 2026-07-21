"""Tests for diagnostics output without HA runtime."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest


def _stub_module(name: str) -> ModuleType:
    module = ModuleType(name)
    sys.modules[name] = module
    return module


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_diagnostics_redacts_token_and_includes_health() -> None:
    _stub_module("homeassistant")
    config_entries_mod = _stub_module("homeassistant.config_entries")
    core_mod = _stub_module("homeassistant.core")
    config_entries_mod.ConfigEntry = object
    core_mod.HomeAssistant = object

    base = Path(__file__).parent.parent / "custom_components" / "openclaw"
    sys.modules.setdefault("custom_components", ModuleType("custom_components"))
    sys.modules.setdefault("custom_components.openclaw", ModuleType("custom_components.openclaw"))

    _load_module("custom_components.openclaw.const", base / "const.py")
    _load_module("custom_components.openclaw.exceptions", base / "exceptions.py")
    _load_module("custom_components.openclaw.device_auth", base / "device_auth.py")
    _load_module("custom_components.openclaw.gateway", base / "gateway.py")
    _load_module("custom_components.openclaw.gateway_client", base / "gateway_client.py")
    diagnostics = _load_module("custom_components.openclaw.diagnostics", base / "diagnostics.py")

    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"host": "localhost", "token": "secret"}
    entry.options = {"token": "secret2"}

    client = AsyncMock()
    client.connected = True
    client.health = AsyncMock(
        return_value={
            "status": "ok",
            "version": "2026.7.2",
            "sessions": {
                "count": 2,
                "path": "/config/private/sessions.json",
                "recent": [{"key": "agent:dan:main"}],
            },
            "channels": {"telegram": {"account_id": "123456"}},
            "agents": [{"id": "dan"}],
            "secret": "must-not-leak",
        }
    )

    hass = MagicMock()
    hass.data = {"openclaw": {"entry-1": client}}

    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)

    assert result["config"]["token"] == "REDACTED"
    assert result["options"]["token"] == "REDACTED"
    assert result["connected"] is True
    assert result["health"] == {
        "status": "ok",
        "version": "2026.7.2",
        "channel_count": 1,
        "agent_count": 1,
        "session_count": 2,
    }
    serialized = repr(result)
    assert "must-not-leak" not in serialized
    assert "agent:dan:main" not in serialized
    assert "/config/private" not in serialized
    assert "123456" not in serialized
