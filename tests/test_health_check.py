"""Tests for periodic health checks without HA runtime."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest


def _stub_module(name: str) -> ModuleType:
    module = ModuleType(name)
    sys.modules.setdefault(name, module)
    return module


def _ensure_ha_stubs() -> bool:
    existing = sys.modules.get("homeassistant")
    if existing is not None and not getattr(existing, "__file__", None):
        sys.modules.pop("homeassistant", None)
    try:
        import homeassistant  # noqa: F401
        return False
    except Exception:
        return True


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_health_check_reconnects_when_disconnected() -> None:
    captured = {}

    if _ensure_ha_stubs():
        _stub_module("homeassistant")
        config_entries_mod = _stub_module("homeassistant.config_entries")
        const_mod = _stub_module("homeassistant.const")
        core_mod = _stub_module("homeassistant.core")
        event_mod = _stub_module("homeassistant.helpers.event")
        _stub_module("homeassistant.helpers")

        class Platform:
            CONVERSATION = "conversation"

        const_mod.CONF_HOST = "host"
        const_mod.CONF_PORT = "port"
        const_mod.CONF_TOKEN = "token"
        const_mod.CONF_TIMEOUT = "timeout"
        const_mod.Platform = Platform
        config_entries_mod.ConfigEntry = object
        core_mod.HomeAssistant = object
        event_mod.async_track_time_interval = lambda *args, **kwargs: None
        event_mod.async_track_time_interval = lambda *args, **kwargs: None
    else:
        import homeassistant.helpers.event as event_mod

    base = Path(__file__).parent.parent / "custom_components" / "clawd"
    sys.modules.setdefault("custom_components", ModuleType("custom_components"))
    sys.modules.setdefault("custom_components.clawd", ModuleType("custom_components.clawd"))

    _load_module("custom_components.clawd.const", base / "const.py")
    gateway_client_mod = ModuleType("custom_components.clawd.gateway_client")
    sys.modules["custom_components.clawd.gateway_client"] = gateway_client_mod

    class ClawdGatewayClient:
        last_instance = None

        def __init__(self, *args, **kwargs) -> None:
            ClawdGatewayClient.last_instance = self
            self.connected = False
            self.connect = AsyncMock()
            self.disconnect = AsyncMock()
            self.health = AsyncMock()

    gateway_client_mod.ClawdGatewayClient = ClawdGatewayClient

    integration = _load_module("custom_components.clawd.__init__", base / "__init__.py")

    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"host": "localhost", "port": 1, "token": None, "timeout": 30}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock()

    def async_track_time_interval(_hass, action, interval):
        captured["action"] = action
        captured["interval"] = interval
        return lambda: None

    original_tracker = integration.async_track_time_interval
    integration.async_track_time_interval = async_track_time_interval

    try:
        await integration.async_setup_entry(hass, entry)
        client = ClawdGatewayClient.last_instance
        client.connect.reset_mock()

        await captured["action"](None)

        client.connect.assert_called_once()
    finally:
        integration.async_track_time_interval = original_tracker


@pytest.mark.asyncio
async def test_health_check_reconnects_on_health_error() -> None:
    captured = {}

    if _ensure_ha_stubs():
        _stub_module("homeassistant")
        config_entries_mod = _stub_module("homeassistant.config_entries")
        const_mod = _stub_module("homeassistant.const")
        core_mod = _stub_module("homeassistant.core")
        event_mod = _stub_module("homeassistant.helpers.event")
        _stub_module("homeassistant.helpers")

        class Platform:
            CONVERSATION = "conversation"

        const_mod.CONF_HOST = "host"
        const_mod.CONF_PORT = "port"
        const_mod.CONF_TOKEN = "token"
        const_mod.CONF_TIMEOUT = "timeout"
        const_mod.Platform = Platform
        config_entries_mod.ConfigEntry = object
        core_mod.HomeAssistant = object
    else:
        import homeassistant.helpers.event as event_mod

    base = Path(__file__).parent.parent / "custom_components" / "clawd"
    sys.modules.setdefault("custom_components", ModuleType("custom_components"))
    sys.modules.setdefault("custom_components.clawd", ModuleType("custom_components.clawd"))

    _load_module("custom_components.clawd.const", base / "const.py")
    gateway_client_mod = ModuleType("custom_components.clawd.gateway_client")
    sys.modules["custom_components.clawd.gateway_client"] = gateway_client_mod

    class ClawdGatewayClient:
        last_instance = None

        def __init__(self, *args, **kwargs) -> None:
            ClawdGatewayClient.last_instance = self
            self.connected = True
            self.connect = AsyncMock()
            self.disconnect = AsyncMock()
            self.health = AsyncMock(side_effect=RuntimeError("boom"))

    gateway_client_mod.ClawdGatewayClient = ClawdGatewayClient

    integration = _load_module("custom_components.clawd.__init__", base / "__init__.py")

    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"host": "localhost", "port": 1, "token": None, "timeout": 30}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock()

    def async_track_time_interval(_hass, action, interval):
        captured["action"] = action
        captured["interval"] = interval
        return lambda: None

    original_tracker = integration.async_track_time_interval
    integration.async_track_time_interval = async_track_time_interval

    try:
        await integration.async_setup_entry(hass, entry)
        client = ClawdGatewayClient.last_instance
        client.connect.reset_mock()
        client.disconnect.reset_mock()

        await captured["action"](None)

        client.disconnect.assert_called_once()
        client.connect.assert_called_once()
    finally:
        integration.async_track_time_interval = original_tracker
