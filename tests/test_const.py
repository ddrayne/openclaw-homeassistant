"""Minimal tests for integration constants that affect user config."""

import importlib.util
import sys
from pathlib import Path

import pytest

# Load const.py directly to avoid triggering custom_components.clawd.__init__
# which imports homeassistant
_const_path = Path(__file__).parent.parent / "custom_components" / "clawd" / "const.py"
_spec = importlib.util.spec_from_file_location("clawd_const", _const_path)
_const = importlib.util.module_from_spec(_spec)
sys.modules["clawd_const"] = _const
_spec.loader.exec_module(_const)

# Import all constants from the loaded module
DOMAIN = _const.DOMAIN
CONF_HOST = _const.CONF_HOST
CONF_PORT = _const.CONF_PORT
CONF_TOKEN = _const.CONF_TOKEN
CONF_USE_SSL = _const.CONF_USE_SSL
CONF_TIMEOUT = _const.CONF_TIMEOUT
CONF_SESSION_KEY = _const.CONF_SESSION_KEY
CONF_STRIP_EMOJIS = _const.CONF_STRIP_EMOJIS


class TestDomain:
    def test_domain_is_clawd(self) -> None:
        assert DOMAIN == "clawd"


class TestConfigurationKeys:
    def test_conf_keys(self) -> None:
        assert CONF_HOST == "host"
        assert CONF_PORT == "port"
        assert CONF_TOKEN == "token"
        assert CONF_USE_SSL == "use_ssl"
        assert CONF_TIMEOUT == "timeout"
        assert CONF_SESSION_KEY == "session_key"
        assert CONF_STRIP_EMOJIS == "strip_emojis"
