"""Unit tests for Clawd integration exceptions.

These tests verify the exception hierarchy in exceptions.py works correctly
for error handling patterns used throughout the codebase.

Note: Uses direct module loading to avoid triggering __init__.py imports
which require the homeassistant package.
"""

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

# All exception classes for parametrized tests
ALL_EXCEPTIONS = [
    ClawdError,
    GatewayConnectionError,
    GatewayAuthenticationError,
    GatewayTimeoutError,
    AgentExecutionError,
    ProtocolError,
]

# Subclasses only (excludes base ClawdError)
SUBCLASS_EXCEPTIONS = [
    GatewayConnectionError,
    GatewayAuthenticationError,
    GatewayTimeoutError,
    AgentExecutionError,
    ProtocolError,
]


class TestClawdErrorBase:
    """Tests for the ClawdError base exception class.

    ClawdError is the base for all Clawd-specific exceptions.
    It must inherit from Exception for standard error handling.
    """

    def test_inherits_from_exception(self):
        """ClawdError must inherit from Exception."""
        assert issubclass(ClawdError, Exception)

    def test_can_instantiate_without_message(self):
        """ClawdError can be raised without a message."""
        error = ClawdError()
        assert isinstance(error, ClawdError)
        assert str(error) == ""

    def test_can_instantiate_with_message(self):
        """ClawdError can carry an error message."""
        message = "Something went wrong"
        error = ClawdError(message)
        assert str(error) == message

    def test_can_instantiate_with_multiple_args(self):
        """ClawdError can carry multiple arguments like standard Exception."""
        error = ClawdError("error", 42, "details")
        assert error.args == ("error", 42, "details")

    def test_can_raise_and_catch(self):
        """ClawdError can be raised and caught."""
        with pytest.raises(ClawdError) as exc_info:
            raise ClawdError("test error")
        assert str(exc_info.value) == "test error"


class TestExceptionHierarchy:
    """Tests for the exception class hierarchy.

    All specific exceptions must inherit from ClawdError.
    This enables catching all Clawd errors with a single except clause.
    """

    @pytest.mark.parametrize(
        "exception_class",
        SUBCLASS_EXCEPTIONS,
        ids=[e.__name__ for e in SUBCLASS_EXCEPTIONS],
    )
    def test_inherits_from_clawd_error(self, exception_class):
        """All subclasses must inherit from ClawdError."""
        assert issubclass(exception_class, ClawdError)

    @pytest.mark.parametrize(
        "exception_class",
        SUBCLASS_EXCEPTIONS,
        ids=[e.__name__ for e in SUBCLASS_EXCEPTIONS],
    )
    def test_inherits_from_exception(self, exception_class):
        """All subclasses must ultimately inherit from Exception."""
        assert issubclass(exception_class, Exception)

    def test_all_exceptions_are_distinct_classes(self):
        """Each exception class is distinct (not the same class)."""
        assert len(ALL_EXCEPTIONS) == len(set(ALL_EXCEPTIONS))

    def test_hierarchy_depth_is_two(self):
        """Subclasses are exactly one level below ClawdError."""
        for exc_class in SUBCLASS_EXCEPTIONS:
            mro = exc_class.__mro__
            # MRO should be: [SubClass, ClawdError, Exception, BaseException, object]
            assert mro[0] == exc_class
            assert mro[1] == ClawdError


class TestExceptionInstantiation:
    """Tests for exception instantiation with messages.

    All exceptions must be able to carry error details for debugging.
    """

    @pytest.mark.parametrize(
        "exception_class",
        ALL_EXCEPTIONS,
        ids=[e.__name__ for e in ALL_EXCEPTIONS],
    )
    def test_can_instantiate_without_message(self, exception_class):
        """All exceptions can be instantiated without a message."""
        error = exception_class()
        assert isinstance(error, exception_class)

    @pytest.mark.parametrize(
        "exception_class",
        ALL_EXCEPTIONS,
        ids=[e.__name__ for e in ALL_EXCEPTIONS],
    )
    def test_can_instantiate_with_message(self, exception_class):
        """All exceptions can carry error messages."""
        message = f"Test error for {exception_class.__name__}"
        error = exception_class(message)
        assert str(error) == message

    @pytest.mark.parametrize(
        "exception_class,sample_message",
        [
            (GatewayConnectionError, "Cannot connect to ws://localhost:8765"),
            (GatewayAuthenticationError, "Invalid token: authentication failed"),
            (GatewayTimeoutError, "Request timed out after 30 seconds"),
            (AgentExecutionError, "Agent 'clawdbot' execution failed: timeout"),
            (ProtocolError, "Protocol version 2 not supported (min: 3, max: 3)"),
        ],
        ids=[
            "connection-error",
            "auth-error",
            "timeout-error",
            "agent-error",
            "protocol-error",
        ],
    )
    def test_realistic_error_messages(self, exception_class, sample_message):
        """Exceptions can carry realistic error messages used in the codebase."""
        error = exception_class(sample_message)
        assert str(error) == sample_message


class TestExceptionRaiseAndCatch:
    """Tests for exception raise and catch patterns.

    These tests verify the error handling patterns used in conversation.py
    and other parts of the codebase work correctly.
    """

    @pytest.mark.parametrize(
        "exception_class",
        SUBCLASS_EXCEPTIONS,
        ids=[e.__name__ for e in SUBCLASS_EXCEPTIONS],
    )
    def test_specific_exception_caught_by_base(self, exception_class):
        """Specific exceptions can be caught by catching ClawdError.

        This is the primary error handling pattern in conversation.py:
        try:
            await gateway.send_prompt(...)
        except ClawdError as e:
            # Handle all Clawd-specific errors uniformly
        """
        with pytest.raises(ClawdError):
            raise exception_class("test error")

    @pytest.mark.parametrize(
        "exception_class",
        SUBCLASS_EXCEPTIONS,
        ids=[e.__name__ for e in SUBCLASS_EXCEPTIONS],
    )
    def test_specific_exception_caught_specifically(self, exception_class):
        """Specific exceptions can also be caught individually.

        This allows fine-grained error handling when needed:
        try:
            await gateway.connect(...)
        except GatewayConnectionError:
            # Handle connection failures specifically
        except GatewayAuthenticationError:
            # Handle auth failures differently
        """
        with pytest.raises(exception_class):
            raise exception_class("test error")

    def test_base_error_not_caught_by_subclass(self):
        """ClawdError is NOT caught when catching only a specific subclass.

        This ensures the hierarchy works correctly in both directions.
        """
        with pytest.raises(ClawdError):
            try:
                raise ClawdError("base error")
            except GatewayConnectionError:
                pytest.fail("ClawdError should not be caught by GatewayConnectionError")

    def test_multi_catch_pattern(self):
        """Multiple specific exceptions can be caught in a tuple.

        Example pattern from the codebase:
        except (GatewayConnectionError, GatewayTimeoutError) as e:
            # Handle network-related errors
        """
        for exc_class in (GatewayConnectionError, GatewayTimeoutError):
            with pytest.raises((GatewayConnectionError, GatewayTimeoutError)):
                raise exc_class("network error")


class TestExceptionDocstrings:
    """Tests for exception class documentation.

    Each exception should have a docstring explaining when it's raised.
    """

    @pytest.mark.parametrize(
        "exception_class",
        ALL_EXCEPTIONS,
        ids=[e.__name__ for e in ALL_EXCEPTIONS],
    )
    def test_has_docstring(self, exception_class):
        """All exception classes must have docstrings."""
        assert exception_class.__doc__ is not None
        assert len(exception_class.__doc__.strip()) > 0

    def test_clawd_error_docstring(self):
        """ClawdError docstring describes it as the base exception."""
        assert "Base" in ClawdError.__doc__ or "base" in ClawdError.__doc__

    def test_gateway_connection_error_docstring(self):
        """GatewayConnectionError docstring mentions connection."""
        doc = GatewayConnectionError.__doc__.lower()
        assert "connect" in doc

    def test_gateway_authentication_error_docstring(self):
        """GatewayAuthenticationError docstring mentions authentication."""
        doc = GatewayAuthenticationError.__doc__.lower()
        assert "auth" in doc or "token" in doc

    def test_gateway_timeout_error_docstring(self):
        """GatewayTimeoutError docstring mentions timeout."""
        doc = GatewayTimeoutError.__doc__.lower()
        assert "timeout" in doc

    def test_agent_execution_error_docstring(self):
        """AgentExecutionError docstring mentions agent or execution."""
        doc = AgentExecutionError.__doc__.lower()
        assert "agent" in doc or "execution" in doc

    def test_protocol_error_docstring(self):
        """ProtocolError docstring mentions protocol."""
        doc = ProtocolError.__doc__.lower()
        assert "protocol" in doc
