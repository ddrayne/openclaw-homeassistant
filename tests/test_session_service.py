"""Tests for session switching service registration (HA-free)."""

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
async def test_set_session_service_updates_client() -> None:
    sys.modules.setdefault("homeassistant", ModuleType("homeassistant"))
    config_entries_mod = ModuleType("homeassistant.config_entries")
    const_mod = ModuleType("homeassistant.const")
    core_mod = ModuleType("homeassistant.core")
    exceptions_mod = ModuleType("homeassistant.exceptions")
    event_mod = ModuleType("homeassistant.helpers.event")
    issue_mod = ModuleType("homeassistant.helpers.issue_registry")
    service_mod = ModuleType("homeassistant.helpers.service")
    sys.modules["homeassistant.config_entries"] = config_entries_mod
    sys.modules["homeassistant.const"] = const_mod
    sys.modules["homeassistant.core"] = core_mod
    sys.modules["homeassistant.exceptions"] = exceptions_mod
    sys.modules["homeassistant.helpers.event"] = event_mod
    sys.modules["homeassistant.helpers.issue_registry"] = issue_mod
    sys.modules["homeassistant.helpers.service"] = service_mod
    sys.modules.setdefault("homeassistant.helpers", ModuleType("homeassistant.helpers"))

    class Platform:
        BINARY_SENSOR = "binary_sensor"
        CONVERSATION = "conversation"
        SENSOR = "sensor"

    const_mod.CONF_HOST = "host"
    const_mod.CONF_PORT = "port"
    const_mod.CONF_TOKEN = "token"
    const_mod.Platform = Platform
    config_entries_mod.ConfigEntry = object
    core_mod.HomeAssistant = object
    exceptions_mod.ConfigEntryAuthFailed = type("ConfigEntryAuthFailed", (Exception,), {})
    exceptions_mod.ConfigEntryNotReady = type("ConfigEntryNotReady", (Exception,), {})
    event_mod.async_track_time_interval = lambda *args, **kwargs: None
    issue_mod.IssueSeverity = type("IssueSeverity", (), {"ERROR": "error"})()
    issue_mod.async_create_issue = lambda *args, **kwargs: None
    issue_mod.async_delete_issue = lambda *args, **kwargs: None

    service_mod.async_register_admin_service = (
        lambda hass, domain, service, handler, schema: hass.services.async_register(
            domain, service, handler, schema=schema
        )
    )

    base = Path(__file__).parent.parent / "custom_components" / "openclaw"
    sys.modules.setdefault("custom_components", ModuleType("custom_components"))
    sys.modules.setdefault("custom_components.openclaw", ModuleType("custom_components.openclaw"))

    const = _load_module("custom_components.openclaw.const", base / "const.py")
    _load_module("custom_components.openclaw.exceptions", base / "exceptions.py")

    gateway_client_mod = ModuleType("custom_components.openclaw.gateway_client")
    sys.modules["custom_components.openclaw.gateway_client"] = gateway_client_mod

    class OpenClawGatewayClient:
        def __init__(self, *args, **kwargs) -> None:
            self.disconnect = AsyncMock()
            self.connect = AsyncMock()
            self.connected = True
            self.set_session_key = MagicMock()
            self._gateway = MagicMock()

    gateway_client_mod.OpenClawGatewayClient = OpenClawGatewayClient

    integration = _load_module("custom_components.openclaw.__init__", base / "__init__.py")

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
        if call.args[1] == integration.SERVICE_SET_SESSION:
            handler = call.args[2]
            break
    assert handler is not None

    client = hass.data[integration.DOMAIN]["entry-1"]

    call = MagicMock()
    call.data = {const.CONF_SESSION_KEY: "voice-assistant"}
    await handler(call)

    client.set_session_key.assert_called_once_with("voice-assistant")
