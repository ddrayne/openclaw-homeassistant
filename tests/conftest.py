"""Fixtures for Clawd integration tests."""

import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.clawd.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations defined in the test dir."""
    yield


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create a mock config entry for Clawd."""
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
    """Patch websockets.connect to return mock WebSocket."""
    with patch("custom_components.clawd.gateway.websockets.connect") as mock_connect:
        # Create async generator that yields the mock once
        async def connect_generator(*args, **kwargs):
            yield mock_websocket

        mock_connect.return_value = connect_generator()
        yield mock_connect, mock_websocket
