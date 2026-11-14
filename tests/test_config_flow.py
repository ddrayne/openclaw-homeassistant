"""Config-flow tests for one entry per gateway, agent and session (#13).

Home Assistant is not installed for the test suite, so the HA modules
``config_flow.py`` imports are stubbed while it loads; ``sys.modules`` is
restored afterwards so other test modules keep their own stubs.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

_BASE = Path(__file__).parent.parent / "custom_components" / "openclaw"
_PKG = "custom_components.openclaw"


class AbortFlow(Exception):
    """Stand-in for homeassistant.data_entry_flow.AbortFlow."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _Selector:
    """Selector stub: a pass-through validator."""

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def __call__(self, value):
        return value


def _ha_stubs() -> dict[str, ModuleType]:
    config_entries = ModuleType("homeassistant.config_entries")

    class ConfigFlow:
        def __init_subclass__(cls, domain: str | None = None, **kwargs) -> None:
            super().__init_subclass__(**kwargs)
            cls.DOMAIN = domain

        def __init__(self) -> None:
            self.context: dict = {}
            self.unique_id: str | None = None

        async def async_set_unique_id(self, unique_id, raise_on_progress=True):
            self.unique_id = unique_id

        def _abort_if_unique_id_configured(self) -> None:
            for entry in self.hass.config_entries.async_entries(self.DOMAIN):
                if entry.unique_id == self.unique_id:
                    raise AbortFlow("already_configured")

        def async_create_entry(self, *, title, data):
            return {
                "type": "create_entry",
                "title": title,
                "data": data,
                "unique_id": self.unique_id,
            }

        def async_show_form(self, *, step_id, data_schema=None, errors=None, **_kw):
            return {"type": "form", "step_id": step_id, "errors": errors or {}}

    class OptionsFlow:
        def async_create_entry(self, *, title, data):
            return {"type": "create_entry", "title": title, "data": data}

        def async_show_form(self, *, step_id, data_schema=None, errors=None, **_kw):
            return {"type": "form", "step_id": step_id, "errors": errors or {}}

    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow
    config_entries.ConfigEntry = object

    const = ModuleType("homeassistant.const")
    const.CONF_HOST = "host"
    const.CONF_PORT = "port"
    const.CONF_TOKEN = "token"
    const.CONF_TIMEOUT = "timeout"

    core = ModuleType("homeassistant.core")
    core.HomeAssistant = object
    core.callback = lambda func: func

    data_entry_flow = ModuleType("homeassistant.data_entry_flow")
    data_entry_flow.FlowResult = dict
    data_entry_flow.AbortFlow = AbortFlow

    selector = ModuleType("homeassistant.helpers.selector")
    for name in (
        "SelectSelector",
        "SelectSelectorConfig",
        "EntitySelector",
        "EntitySelectorConfig",
    ):
        setattr(selector, name, _Selector)
    selector.SelectSelectorMode = SimpleNamespace(DROPDOWN="dropdown", LIST="list")

    aiohttp_client = ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client.async_get_clientsession = MagicMock()

    helpers = ModuleType("homeassistant.helpers")
    helpers.selector = selector
    helpers.aiohttp_client = aiohttp_client

    homeassistant = ModuleType("homeassistant")
    homeassistant.config_entries = config_entries

    aiohttp = ModuleType("aiohttp")
    aiohttp.ClientTimeout = lambda **kwargs: kwargs

    gateway_client = ModuleType(f"{_PKG}.gateway_client")
    gateway_client.OpenClawGatewayClient = MagicMock()

    gateway = ModuleType(f"{_PKG}.gateway")
    gateway.create_ssl_context = MagicMock()

    return {
        "aiohttp": aiohttp,
        "homeassistant": homeassistant,
        "homeassistant.config_entries": config_entries,
        "homeassistant.const": const,
        "homeassistant.core": core,
        "homeassistant.data_entry_flow": data_entry_flow,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.selector": selector,
        "homeassistant.helpers.aiohttp_client": aiohttp_client,
        f"{_PKG}.gateway": gateway,
        f"{_PKG}.gateway_client": gateway_client,
    }


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_config_flow() -> ModuleType:
    stubs = _ha_stubs()
    keys = [
        *stubs,
        "custom_components",
        _PKG,
        f"{_PKG}.const",
        f"{_PKG}.exceptions",
        f"{_PKG}.config_flow",
    ]
    saved = {key: sys.modules.get(key) for key in keys}
    try:
        sys.modules.update(stubs)
        sys.modules["custom_components"] = ModuleType("custom_components")
        sys.modules[_PKG] = ModuleType(_PKG)
        _load(f"{_PKG}.const", _BASE / "const.py")
        _load(f"{_PKG}.exceptions", _BASE / "exceptions.py")
        return _load(f"{_PKG}.config_flow", _BASE / "config_flow.py")
    finally:
        for key, module in saved.items():
            if module is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = module


cf = _load_config_flow()
entry_unique_id = cf.entry_unique_id


def _entry(entry_id: str, unique_id: str, **data):
    return SimpleNamespace(
        entry_id=entry_id,
        unique_id=unique_id,
        data={"host": "gw.local", "port": 18789, **data},
        options={},
    )


def _hass(*entries):
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=list(entries))
    hass.config_entries.async_update_entry = MagicMock()
    return hass


GATEWAY = {"host": "gw.local", "port": 18789, "token": "t", "use_ssl": False}


# ---------- unique IDs ----------


def test_default_agent_and_session_keep_the_legacy_id() -> None:
    """Existing entries must keep their unique ID."""
    assert entry_unique_id("gw.local", 18789, None, "main") == "gw.local:18789"
    assert entry_unique_id("gw.local", 18789, "", None) == "gw.local:18789"


def test_agent_or_session_scope_the_id() -> None:
    ids = {
        entry_unique_id("gw.local", 18789, None, "main"),
        entry_unique_id("gw.local", 18789, "voice", "main"),
        entry_unique_id("gw.local", 18789, "kids", "main"),
        entry_unique_id("gw.local", 18789, None, "ha-partner"),
    }
    assert len(ids) == 4


# ---------- config flow ----------


async def _finish_flow(hass, session_input: dict):
    flow = cf.OpenClawConfigFlow()
    flow.hass = hass
    flow._config_data = dict(GATEWAY)
    flow._config_title = "OpenClaw Gateway (gw.local)"
    return await flow.async_step_session(dict(session_input))


async def test_same_gateway_can_be_added_for_another_agent() -> None:
    """#13: each agent on one gateway becomes its own assistant."""
    hass = _hass(_entry("e1", "gw.local:18789"))

    result = await _finish_flow(hass, {"session_key": "main", "agent_id": "voice"})

    assert result["type"] == "create_entry"
    assert result["unique_id"] == "gw.local:18789|agent=voice|session=main"
    assert result["title"] == "OpenClaw Gateway (gw.local) — voice"


async def test_same_gateway_agent_and_session_is_still_rejected() -> None:
    hass = _hass(_entry("e1", "gw.local:18789"))

    with pytest.raises(AbortFlow, match="already_configured"):
        await _finish_flow(hass, {"session_key": "main", "agent_id": ""})


async def test_user_step_no_longer_rejects_a_known_gateway(monkeypatch) -> None:
    """The duplicate check moved to the session step, where the agent is known."""
    hass = _hass(_entry("e1", "gw.local:18789"))
    monkeypatch.setattr(
        cf, "validate_connection", AsyncMock(return_value={"title": "OpenClaw Gateway (gw.local)"})
    )
    monkeypatch.setattr(cf, "_async_fetch_sessions", AsyncMock(return_value=[]))
    flow = cf.OpenClawConfigFlow()
    flow.hass = hass

    result = await flow.async_step_user(dict(GATEWAY))

    assert result["type"] == "form"
    assert result["step_id"] == "session"


async def test_title_names_a_non_default_session() -> None:
    result = await _finish_flow(
        _hass(), {"session_key": "ha-partner", "agent_id": ""}
    )

    assert result["title"] == "OpenClaw Gateway (gw.local) — session ha-partner"


# ---------- options flow ----------


def _options_flow(hass, entry):
    flow = cf.OpenClawOptionsFlowHandler()
    flow.hass = hass
    flow.config_entry = entry
    return flow


def _options_input(**overrides) -> dict:
    return {
        **GATEWAY,
        "timeout": 300,
        "session_key": "main",
        "agent_id": "",
        "strip_emojis": True,
        "tts_max_chars": 0,
        **overrides,
    }


async def test_options_reject_switching_to_another_entrys_agent(monkeypatch) -> None:
    monkeypatch.setattr(cf, "validate_connection", AsyncMock(return_value={}))
    monkeypatch.setattr(cf, "_async_fetch_sessions", AsyncMock(return_value=[]))
    default = _entry("e1", "gw.local:18789")
    voice = _entry("e2", "gw.local:18789|agent=voice|session=main", agent_id="voice")
    hass = _hass(default, voice)

    result = await _options_flow(hass, default).async_step_init(
        _options_input(agent_id="voice")
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "already_configured"}
    hass.config_entries.async_update_entry.assert_not_called()


async def test_options_save_the_agent_scoped_id(monkeypatch) -> None:
    monkeypatch.setattr(cf, "validate_connection", AsyncMock(return_value={}))
    entry = _entry("e1", "gw.local:18789")
    hass = _hass(entry)

    result = await _options_flow(hass, entry).async_step_init(
        _options_input(agent_id="voice")
    )

    assert result["type"] == "create_entry"
    kwargs = hass.config_entries.async_update_entry.call_args.kwargs
    assert kwargs["unique_id"] == "gw.local:18789|agent=voice|session=main"

async def test_options_can_clear_token_and_model(monkeypatch) -> None:
    """Clearing optional fields persists None in data and options."""
    monkeypatch.setattr(
        cf, "validate_connection", AsyncMock(return_value={})
    )

    entry = _entry("e1", "gw.local:18789")
    hass = _hass(entry)

    result = await _options_flow(hass, entry).async_step_init(
        _options_input(token="", model="")
    )

    assert result["type"] == "create_entry"

    kwargs = hass.config_entries.async_update_entry.call_args.kwargs

    assert kwargs["data"]["token"] is None
    assert kwargs["data"]["model"] is None
    assert kwargs["options"]["token"] is None
    assert kwargs["options"]["model"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"use_ssl": True, "client_cert": "/tmp/client.crt"},
        {
            "use_ssl": False,
            "client_cert": "/tmp/client.crt",
            "client_key": "/tmp/client.key",
        },
    ],
)
async def test_options_reject_invalid_mtls_settings(
    monkeypatch, overrides
) -> None:
    """Reject incomplete mTLS settings and mTLS without SSL."""
    monkeypatch.setattr(
        cf,
        "_async_fetch_sessions",
        AsyncMock(return_value=[]),
    )

    entry = _entry("e1", "gw.local:18789")
    hass = _hass(entry)

    result = await _options_flow(hass, entry).async_step_init(
        _options_input(**overrides)
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_mtls"}
    hass.config_entries.async_update_entry.assert_not_called()

@pytest.mark.asyncio
async def test_options_reject_missing_mtls_certificate(monkeypatch) -> None:
    """Missing certificate must produce a specific config-flow error."""
    monkeypatch.setattr(
        cf,
        "_async_fetch_sessions",
        AsyncMock(return_value=[]),
    )

    entry = _entry("e1", "gw.local:18789")
    hass = _hass(entry)

    GatewayTLSConfigurationError = cf.GatewayTLSConfigurationError

    monkeypatch.setattr(
        cf,
        "create_ssl_context",
        MagicMock(
            side_effect=GatewayTLSConfigurationError(
                "Invalid TLS configuration: certificate not found"
            )
        ),
    )

    result = await _options_flow(hass, entry).async_step_init(
        _options_input(
            use_ssl=True,
            client_cert="/nonexistent/openclaw-test-client.crt",
            client_key="/nonexistent/openclaw-test-client.key",
        )
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_mtls_files"}
    hass.config_entries.async_update_entry.assert_not_called()

@pytest.mark.asyncio
async def test_validate_connection_with_mtls(monkeypatch) -> None:
    """Valid mTLS credentials reach the Gateway client."""
    ssl_helper = MagicMock(return_value=object())
    monkeypatch.setattr(cf, "create_ssl_context", ssl_helper)

    client = MagicMock()
    client.connect = AsyncMock()
    client.health = AsyncMock()
    client.disconnect = AsyncMock()

    client_factory = MagicMock(return_value=client)
    monkeypatch.setattr(cf, "OpenClawGatewayClient", client_factory)

    result = await cf.validate_connection(
        MagicMock(),
        {
            **GATEWAY,
            "use_ssl": True,
            "client_cert": "/tmp/client.crt",
            "client_key": "/tmp/client.key",
        },
    )

    assert result["title"] == "OpenClaw Gateway (gw.local)"

    ssl_helper.assert_called_once_with(
        "/tmp/client.crt", "/tmp/client.key"
    )

    kwargs = client_factory.call_args.kwargs
    assert kwargs["client_cert"] == "/tmp/client.crt"
    assert kwargs["client_key"] == "/tmp/client.key"
    assert kwargs["use_ssl"] is True

    client.connect.assert_awaited_once()
    client.health.assert_awaited_once()
    client.disconnect.assert_awaited_once()

@pytest.mark.asyncio
async def test_session_discovery_uses_mtls(monkeypatch) -> None:
    """HTTPS session discovery must use the client TLS context."""
    ssl_context = object()
    ssl_helper = MagicMock(return_value=ssl_context)
    monkeypatch.setattr(cf, "create_ssl_context", ssl_helper)

    response = MagicMock()
    response.status = 200
    response.json = AsyncMock(
        return_value={
            "sessions": [
                {"sessionKey": "main"},
                {"session_key": "personal"},
            ]
        }
    )

    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.get.return_value = context

    monkeypatch.setattr(
        cf.aiohttp_client,
        "async_get_clientsession",
        MagicMock(return_value=session),
    )

    result = await cf._async_fetch_sessions(
        MagicMock(),
        {
            **GATEWAY,
            "use_ssl": True,
            "client_cert": "/tmp/client.crt",
            "client_key": "/tmp/client.key",
        },
    )

    assert result == ["main", "personal"]

    ssl_helper.assert_called_once_with(
        "/tmp/client.crt", "/tmp/client.key"
    )

    args, kwargs = session.get.call_args
    assert args[0] == "https://gw.local:18789/sessions"
    assert kwargs["ssl"] is ssl_context
