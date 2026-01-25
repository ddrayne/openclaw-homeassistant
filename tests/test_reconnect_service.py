"""Tests for reconnect service registration (HA-free)."""

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
async def test_reconnect_service_calls_clients() -> None:
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

    class ClawdGatewayClient:
        def __init__(self, *args, **kwargs) -> None:
            self.disconnect = AsyncMock()
            self.connect = AsyncMock()
            self.connected = True

    gateway_client_mod.ClawdGatewayClient = ClawdGatewayClient

    integration = _load_module("custom_components.clawd.__init__", base / "__init__.py")

    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.services.async_register = MagicMock()
    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"host": "localhost", "port": 1, "token": None}
    entry.options = {}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock()

    await integration.async_setup_entry(hass, entry)

    handler = None
    for call in hass.services.async_register.call_args_list:
        if call.args[1] == integration.SERVICE_RECONNECT:
            handler = call.args[2]
            break
    assert handler is not None
    client = hass.data[integration.DOMAIN]["entry-1"]
    client.connect.reset_mock()
    client.disconnect.reset_mock()

    call = MagicMock()
    call.data = {}
    await handler(call)

    client.disconnect.assert_called_once()
    client.connect.assert_called_once()
