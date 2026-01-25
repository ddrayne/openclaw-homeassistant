"""Minimal tests for exception hierarchy."""

import importlib.util
import sys
from pathlib import Path

import pytest

# Load exceptions.py directly to avoid triggering custom_components.clawd.__init__
# which imports homeassistant
_exceptions_path = (
    Path(__file__).parent.parent / "custom_components" / "clawd" / "exceptions.py"
)
_spec = importlib.util.spec_from_file_location("clawd_exceptions", _exceptions_path)
_exceptions = importlib.util.module_from_spec(_spec)
sys.modules["clawd_exceptions"] = _exceptions
_spec.loader.exec_module(_exceptions)

# Import all exceptions from the loaded module
ClawdError = _exceptions.ClawdError
GatewayConnectionError = _exceptions.GatewayConnectionError
GatewayAuthenticationError = _exceptions.GatewayAuthenticationError
GatewayTimeoutError = _exceptions.GatewayTimeoutError
AgentExecutionError = _exceptions.AgentExecutionError
ProtocolError = _exceptions.ProtocolError

# Subclasses only (excludes base ClawdError).
SUBCLASS_EXCEPTIONS = [
    GatewayConnectionError,
    GatewayAuthenticationError,
    GatewayTimeoutError,
    AgentExecutionError,
    ProtocolError,
]


class TestExceptionHierarchy:
    @pytest.mark.parametrize(
        "exception_class",
        SUBCLASS_EXCEPTIONS,
        ids=[e.__name__ for e in SUBCLASS_EXCEPTIONS],
    )
    def test_inherits_from_clawd_error(self, exception_class) -> None:
        assert issubclass(exception_class, ClawdError)
