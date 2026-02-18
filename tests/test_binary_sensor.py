"""Tests for the binary sensor entity (HA-free)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

_BASE = Path(__file__).parent.parent / "custom_components" / "openclaw"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ── stub out homeassistant packages ──

_ha = MagicMock()

_bs_mod = ModuleType("homeassistant.components.binary_sensor")


class _BinarySensorDeviceClass:
    CONNECTIVITY = "connectivity"


class _BinarySensorEntity:
    pass


_bs_mod.BinarySensorDeviceClass = _BinarySensorDeviceClass  # type: ignore[attr-defined]
_bs_mod.BinarySensorEntity = _BinarySensorEntity  # type: ignore[attr-defined]

_const_mod = ModuleType("homeassistant.const")
_const_mod.EntityCategory = type("EntityCategory", (), {"DIAGNOSTIC": "diagnostic"})  # type: ignore[attr-defined]

for mod_name in (
    "homeassistant",
    "homeassistant.components",
    "homeassistant.config_entries",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.entity_platform",
):
    sys.modules.setdefault(mod_name, _ha)

sys.modules["homeassistant.components.binary_sensor"] = _bs_mod
sys.modules["homeassistant.const"] = _const_mod

sys.modules.setdefault("custom_components", ModuleType("custom_components"))
sys.modules.setdefault("custom_components.openclaw", ModuleType("custom_components.openclaw"))

_const = _load_module("custom_components.openclaw.const", _BASE / "const.py")
_exceptions = _load_module("custom_components.openclaw.exceptions", _BASE / "exceptions.py")
_device_auth = _load_module("custom_components.openclaw.device_auth", _BASE / "device_auth.py")
_gateway = _load_module("custom_components.openclaw.gateway", _BASE / "gateway.py")
_gateway_client = _load_module(
    "custom_components.openclaw.gateway_client", _BASE / "gateway_client.py"
)
_binary_sensor = _load_module(
    "custom_components.openclaw.binary_sensor", _BASE / "binary_sensor.py"
)

OpenClawGatewayConnectivitySensor = _binary_sensor.OpenClawGatewayConnectivitySensor
OpenClawGatewayClient = _gateway_client.OpenClawGatewayClient


class TestOpenClawGatewayConnectivitySensor:
    def _make_sensor(self, connected: bool):
        client = OpenClawGatewayClient("localhost", 1, None)
        client._gateway._connected = connected
        config_entry = MagicMock()
        config_entry.entry_id = "test_entry"
        return OpenClawGatewayConnectivitySensor(config_entry, client)

    def test_is_on_when_connected(self) -> None:
        sensor = self._make_sensor(True)
        assert sensor.is_on is True

    def test_is_off_when_disconnected(self) -> None:
        sensor = self._make_sensor(False)
        assert sensor.is_on is False

    def test_unique_id(self) -> None:
        sensor = self._make_sensor(False)
        assert sensor._attr_unique_id == "test_entry_gateway_connectivity"

    def test_device_info(self) -> None:
        sensor = self._make_sensor(False)
        info = sensor.device_info
        assert ("openclaw", "test_entry") in info["identifiers"]
        assert info["name"] == "OpenClaw Gateway"

    def test_device_class(self) -> None:
        sensor = self._make_sensor(False)
        assert sensor._attr_device_class == "connectivity"

    def test_entity_category(self) -> None:
        sensor = self._make_sensor(False)
        assert sensor._attr_entity_category == "diagnostic"

    def test_should_poll(self) -> None:
        sensor = self._make_sensor(False)
        assert sensor._attr_should_poll is True
