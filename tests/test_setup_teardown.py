"""Tests for setup-retry and reconnect-service failure handling (HA-free)."""

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


def _install_ha_stubs():
    """Register the Home Assistant modules the integration imports."""
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

    def _register_admin_service(hass, domain, service, handler, schema) -> None:
        hass.services.async_register(domain, service, handler, schema=schema)

    service_mod.async_register_admin_service = MagicMock(
        side_effect=_register_admin_service
    )
    return exceptions_mod


def _load_integration():
    """Load ``__init__.py`` against a fake gateway client.

    Returns ``(integration, exceptions, exceptions_module, client_class)``; the
    client class records every instance it creates in ``client_class.instances``.
    """
    exceptions_mod = _install_ha_stubs()
    base = Path(__file__).parent.parent / "custom_components" / "openclaw"
    sys.modules.setdefault("custom_components", ModuleType("custom_components"))
    sys.modules.setdefault(
        "custom_components.openclaw", ModuleType("custom_components.openclaw")
    )

    _load_module("custom_components.openclaw.const", base / "const.py")
    exceptions = _load_module(
        "custom_components.openclaw.exceptions", base / "exceptions.py"
    )

    gateway_client_mod = ModuleType("custom_components.openclaw.gateway_client")
    sys.modules["custom_components.openclaw.gateway_client"] = gateway_client_mod

    class FakeGatewayClient:
        instances: list = []
        connect_error = None

        def __init__(self, *args, **kwargs) -> None:
            self.disconnect = AsyncMock()
            self.connect = AsyncMock(side_effect=self._connect)
            self.connected = True
            self._gateway = MagicMock()
            type(self).instances.append(self)

        async def _connect(self) -> None:
            error = type(self).connect_error
            if error is not None:
                raise error

    gateway_client_mod.OpenClawGatewayClient = FakeGatewayClient

    integration = _load_module(
        "custom_components.openclaw.__init__", base / "__init__.py"
    )
    return integration, exceptions, exceptions_mod, FakeGatewayClient


def _make_entry(entry_id: str = "entry-1"):
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {"host": "localhost", "port": 1, "token": None}
    entry.options = {}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock()
    return entry


def _make_hass():
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.services.async_register = MagicMock()
    return hass


def _reconnect_handler(integration, hass):
    handler = None
    for call in hass.services.async_register.call_args_list:
        if call.args[1] == integration.SERVICE_RECONNECT:
            handler = call.args[2]
            break
    assert handler is not None
    return handler


@pytest.mark.asyncio
async def test_setup_failure_disconnects_the_client() -> None:
    """A client that never reached hass.data must not keep retrying."""
    integration, exceptions, exceptions_mod, client_class = _load_integration()
    client_class.instances.clear()
    client_class.connect_error = exceptions.GatewayConnectionError("Connection timeout")

    hass = _make_hass()
    with pytest.raises(exceptions_mod.ConfigEntryNotReady):
        await integration.async_setup_entry(hass, _make_entry())

    client = client_class.instances[-1]
    client.disconnect.assert_awaited_once()
    assert hass.data.get(integration.DOMAIN, {}) == {}


@pytest.mark.asyncio
async def test_setup_auth_failure_disconnects_before_raising() -> None:
    integration, exceptions, exceptions_mod, client_class = _load_integration()
    client_class.instances.clear()
    client_class.connect_error = exceptions.GatewayAuthenticationError("invalid token")

    hass = _make_hass()
    with pytest.raises(exceptions_mod.ConfigEntryAuthFailed):
        await integration.async_setup_entry(hass, _make_entry())

    client = client_class.instances[-1]
    client.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconnect_service_continues_after_one_entry_fails() -> None:
    """One still-recovering entry must not block the others."""
    integration, exceptions, _exceptions_mod, client_class = _load_integration()
    hass = _make_hass()
    await integration.async_setup_entry(hass, _make_entry("entry-1"))

    first = hass.data[integration.DOMAIN]["entry-1"]
    second = client_class()
    hass.data[integration.DOMAIN]["entry-2"] = second

    first.disconnect.reset_mock()
    first.connect.reset_mock()
    first.connect.side_effect = exceptions.GatewayConnectionError("still down")

    handler = _reconnect_handler(integration, hass)
    call = MagicMock()
    call.data = {}

    await handler(call)

    second.connect.assert_awaited_once()
    second.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconnect_service_ignores_unknown_entry() -> None:
    integration, *_ = _load_integration()
    hass = _make_hass()
    await integration.async_setup_entry(hass, _make_entry("entry-1"))
    client = hass.data[integration.DOMAIN]["entry-1"]
    client.connect.reset_mock()
    client.disconnect.reset_mock()
    handler = _reconnect_handler(integration, hass)

    call = MagicMock()
    call.data = {"entry_id": "does-not-exist"}
    await handler(call)

    client.connect.assert_not_awaited()
    client.disconnect.assert_not_awaited()
