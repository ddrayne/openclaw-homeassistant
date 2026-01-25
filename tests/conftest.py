"""Fixtures for Clawd integration tests.

This module provides test fixtures that work in two modes:
1. Full mode: With pytest-homeassistant-custom-component installed
   - Uses real MockConfigEntry from HA test framework
   - Enables custom integrations automatically
2. Standalone mode: Without HA framework (e.g., Windows Long Path issues)
   - Uses MagicMock-based config entry
   - HA-specific fixtures are no-ops

The HAS_HA_FRAMEWORK flag controls which mode is active.
"""

import asyncio
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import DOMAIN directly to avoid triggering __init__.py imports
# which require homeassistant package
DOMAIN = "clawd"

# Try to import HA test framework - may fail on Windows due to Long Path issues
try:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    HAS_HA_FRAMEWORK = True
except ImportError:
    HAS_HA_FRAMEWORK = False
    MockConfigEntry = MagicMock  # type: ignore[misc, assignment]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request):
    """Enable custom integrations defined in the test dir.

    When HA framework is not available, this is a no-op.
    """
    if HAS_HA_FRAMEWORK:
        # Get the enable_custom_integrations fixture from HA test framework
        enable_fixture = request.getfixturevalue("enable_custom_integrations")
        yield enable_fixture
    else:
        yield None


@pytest.fixture
def mock_config_entry() -> Any:
    """Create a mock config entry for Clawd.

    Returns MockConfigEntry when HA framework is available,
    otherwise returns a MagicMock with equivalent attributes.
    """
    if HAS_HA_FRAMEWORK:
        return MockConfigEntry(
            domain=DOMAIN,
            unique_id="localhost:8765",
            data={
                "host": "localhost",
                "port": 8765,
                "token": "test-token",
                "use_ssl": False,
                "timeout": 30,
                "session_key": "main",
            },
            title="Clawd Gateway (localhost)",
        )
    else:
        # Standalone mode: create a MagicMock with same structure
        entry = MagicMock()
        entry.domain = DOMAIN
        entry.unique_id = "localhost:8765"
        entry.data = {
            "host": "localhost",
            "port": 8765,
            "token": "test-token",
            "use_ssl": False,
            "timeout": 30,
            "session_key": "main",
        }
        entry.title = "Clawd Gateway (localhost)"
        return entry


@pytest.fixture
def mock_websocket() -> AsyncMock:
    """Create a mock WebSocket connection."""
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock()
    ws.close = AsyncMock()
    # For async context manager support
    ws.__aenter__ = AsyncMock(return_value=ws)
    ws.__aexit__ = AsyncMock(return_value=None)
    return ws


@pytest.fixture
def mock_websocket_connect(mock_websocket: AsyncMock) -> Generator:
    """Patch websockets.connect to return mock WebSocket.

    This fixture patches at the websockets library level when the gateway
    module cannot be imported (e.g., when homeassistant is not available).
    When the full HA framework is available, it patches at the gateway module level.
    """
    # Determine patch target based on what's importable
    if HAS_HA_FRAMEWORK:
        patch_target = "custom_components.clawd.gateway.websockets.connect"
    else:
        # Patch websockets library directly when gateway can't be imported
        patch_target = "websockets.connect"

    with patch(patch_target) as mock_connect:
        # Create async generator that yields the mock once
        async def connect_generator(*args, **kwargs):
            yield mock_websocket

        mock_connect.return_value = connect_generator()
        yield mock_connect, mock_websocket


@pytest.fixture
async def async_cleanup():
    """Ensure async cleanup tasks can run.

    Tests with async resources should depend on this fixture to prevent
    "Event loop is closed" errors by ensuring pending callbacks are processed.
    """
    yield
    # Give event loop a chance to process pending callbacks
    await asyncio.sleep(0)
