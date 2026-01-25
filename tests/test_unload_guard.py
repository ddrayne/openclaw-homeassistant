"""Tests for unload/reload guards without HA runtime."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_unload_returns_true_when_entry_missing() -> None:
    sys.modules.setdefault("homeassistant", ModuleType("homeassistant"))
    config_entries_mod = ModuleType("homeassistant.config_entries")
    const_mod = ModuleType("homeassistant.const")
    core_mod = ModuleType("homeassistant.core")
    event_mod = ModuleType("homeassistant.helpers.event")
    sys.modules["homeassistant.config_entries"] = config_entries_mod
    sys.modules["homeassistant.const"] = const_mod
    sys.modules["homeassistant.core"] = core_mod
    sys.modules["homeassistant.helpers.event"] = event_mod
    sys.modules.setdefault("homeassistant.helpers", ModuleType("homeassistant.helpers"))

    class Platform:
        CONVERSATION = "conversation"
        SENSOR = "sensor"

    const_mod.CONF_HOST = "host"
    const_mod.CONF_PORT = "port"
    const_mod.CONF_TOKEN = "token"
    const_mod.Platform = Platform
    config_entries_mod.ConfigEntry = object
    core_mod.HomeAssistant = object
    event_mod.async_track_time_interval = lambda *args, **kwargs: None

    base = Path(__file__).parent.parent / "custom_components" / "clawd"
    sys.modules.setdefault("custom_components", ModuleType("custom_components"))
    sys.modules.setdefault("custom_components.clawd", ModuleType("custom_components.clawd"))

    _load_module("custom_components.clawd.const", base / "const.py")
    gateway_client_mod = ModuleType("custom_components.clawd.gateway_client")
    sys.modules["custom_components.clawd.gateway_client"] = gateway_client_mod
    gateway_client_mod.ClawdGatewayClient = object

    integration = _load_module("custom_components.clawd.__init__", base / "__init__.py")

    hass = MagicMock()
    hass.data = {}
    entry = MagicMock()
    entry.entry_id = "missing"

    result = await integration.async_unload_entry(hass, entry)
    assert result is True
