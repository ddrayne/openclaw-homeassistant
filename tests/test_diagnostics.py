"""Tests for diagnostics output without HA runtime."""

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
async def test_diagnostics_redacts_token_and_includes_health() -> None:
    if _ensure_ha_stubs():
        _stub_module("homeassistant")
        config_entries_mod = _stub_module("homeassistant.config_entries")
        core_mod = _stub_module("homeassistant.core")
        config_entries_mod.ConfigEntry = object
        core_mod.HomeAssistant = object

    base = Path(__file__).parent.parent / "custom_components" / "clawd"
    sys.modules.setdefault("custom_components", ModuleType("custom_components"))
    sys.modules.setdefault("custom_components.clawd", ModuleType("custom_components.clawd"))

    _load_module("custom_components.clawd.const", base / "const.py")
    _load_module("custom_components.clawd.exceptions", base / "exceptions.py")
    _load_module("custom_components.clawd.gateway", base / "gateway.py")
    _load_module("custom_components.clawd.gateway_client", base / "gateway_client.py")
    diagnostics = _load_module("custom_components.clawd.diagnostics", base / "diagnostics.py")

    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"host": "localhost", "token": "secret"}
    entry.options = {"token": "secret2"}

    client = AsyncMock()
    client.connected = True
    client.health = AsyncMock(return_value={"status": "ok"})

    hass = MagicMock()
    hass.data = {"clawd": {"entry-1": client}}

    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)

    assert result["config"]["token"] == "REDACTED"
    assert result["options"]["token"] == "REDACTED"
    assert result["connected"] is True
    assert result["health"] == {"status": "ok"}
