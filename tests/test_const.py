"""Minimal tests for integration constants that affect user config."""

import importlib.util
import sys
from pathlib import Path

import pytest

# Load const.py directly to avoid triggering custom_components.openclaw.__init__
# which imports homeassistant
_const_path = Path(__file__).parent.parent / "custom_components" / "openclaw" / "const.py"
_spec = importlib.util.spec_from_file_location("openclaw_const", _const_path)
_const = importlib.util.module_from_spec(_spec)
sys.modules["openclaw_const"] = _const
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
CONF_TTS_MAX_CHARS = _const.CONF_TTS_MAX_CHARS


class TestDomain:
    def test_domain_is_openclaw(self) -> None:
        assert DOMAIN == "openclaw"


class TestConfigurationKeys:
    def test_conf_keys(self) -> None:
        assert CONF_HOST == "host"
        assert CONF_PORT == "port"
        assert CONF_TOKEN == "token"
        assert CONF_USE_SSL == "use_ssl"
        assert CONF_TIMEOUT == "timeout"
        assert CONF_SESSION_KEY == "session_key"
        assert CONF_STRIP_EMOJIS == "strip_emojis"
        assert CONF_TTS_MAX_CHARS == "tts_max_chars"


class TestBackgroundWorkDefaults:
    def test_timeout_default_raised_to_300(self) -> None:
        assert _const.DEFAULT_TIMEOUT == 300

    def test_background_conf_keys(self) -> None:
        assert _const.CONF_BACKGROUND_ENABLED == "background_enabled"
        assert _const.CONF_BACKGROUND_GRACE == "background_grace"
        assert _const.CONF_HOLDING_PHRASE == "holding_phrase"

    def test_background_defaults(self) -> None:
        assert _const.DEFAULT_BACKGROUND_ENABLED is True
        assert _const.DEFAULT_BACKGROUND_GRACE == 10
        assert _const.DEFAULT_HOLDING_PHRASE
        assert _const.BACKGROUND_ERROR_PHRASE
        assert _const.BACKGROUND_TIMEOUT_PHRASE
