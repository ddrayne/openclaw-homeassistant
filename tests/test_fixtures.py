"""Smoke tests for fixture functionality.

These tests verify that fixture patterns work correctly.
They are designed to work both with and without the full
pytest-homeassistant-custom-component framework.

When running with full HA test framework:
- The 'hass' fixture comes from pytest-homeassistant-custom-component
- MockConfigEntry comes from pytest_homeassistant_custom_component.common

When running standalone (HA framework not available):
- Tests marked with pytest.mark.requires_ha are skipped
- Fixtures fall back to MagicMock implementations
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# Import HAS_HA_FRAMEWORK from conftest to check availability
from tests.conftest import HAS_HA_FRAMEWORK

# Marker for tests requiring full HA framework
requires_ha = pytest.mark.skipif(
    not HAS_HA_FRAMEWORK,
    reason="Requires homeassistant package (Windows Long Path support may be needed)",
)


class TestMockConfigEntry:
    """Test mock_config_entry fixture."""

    def test_has_correct_domain(self, mock_config_entry: Any) -> None:
        """Verify mock config entry has expected domain."""
        assert mock_config_entry.domain == "clawd"

    def test_has_correct_host(self, mock_config_entry: Any) -> None:
        """Verify mock config entry has expected host."""
        assert mock_config_entry.data["host"] == "localhost"

    def test_has_correct_port(self, mock_config_entry: Any) -> None:
        """Verify mock config entry has expected port."""
        assert mock_config_entry.data["port"] == 8765

    def test_has_token(self, mock_config_entry: Any) -> None:
        """Verify mock config entry has token."""
        assert mock_config_entry.data["token"] == "test-token"

    def test_has_unique_id(self, mock_config_entry: Any) -> None:
        """Verify mock config entry has unique_id."""
        assert mock_config_entry.unique_id == "localhost:8765"


class TestMockWebSocket:
    """Test mock_websocket fixture."""

    def test_send_is_async_mock(self, mock_websocket: AsyncMock) -> None:
        """Verify send method is AsyncMock."""
        assert isinstance(mock_websocket.send, AsyncMock)

    def test_recv_is_async_mock(self, mock_websocket: AsyncMock) -> None:
        """Verify recv method is AsyncMock."""
        assert isinstance(mock_websocket.recv, AsyncMock)

    def test_close_is_async_mock(self, mock_websocket: AsyncMock) -> None:
        """Verify close method is AsyncMock."""
        assert isinstance(mock_websocket.close, AsyncMock)

    def test_supports_async_context_manager(self, mock_websocket: AsyncMock) -> None:
        """Verify mock WebSocket can be used as async context manager."""
        assert isinstance(mock_websocket.__aenter__, AsyncMock)
        assert isinstance(mock_websocket.__aexit__, AsyncMock)


class TestMockWebSocketConnect:
    """Test mock_websocket_connect fixture."""

    def test_returns_tuple(
        self, mock_websocket_connect: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Verify fixture returns (mock_connect, mock_websocket) tuple."""
        mock_connect, mock_ws = mock_websocket_connect
        assert mock_connect is not None
        assert mock_ws is not None

    def test_mock_connect_is_callable(
        self, mock_websocket_connect: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Verify mock_connect is callable."""
        mock_connect, _ = mock_websocket_connect
        assert callable(mock_connect)

    def test_mock_ws_has_async_methods(
        self, mock_websocket_connect: tuple[MagicMock, AsyncMock]
    ) -> None:
        """Verify mock_ws has AsyncMock send/recv/close."""
        _, mock_ws = mock_websocket_connect
        assert isinstance(mock_ws.send, AsyncMock)
        assert isinstance(mock_ws.recv, AsyncMock)
        assert isinstance(mock_ws.close, AsyncMock)


class TestAsyncCleanup:
    """Test async_cleanup fixture."""

    async def test_runs_without_error(self, async_cleanup: None) -> None:
        """Verify async cleanup runs without raising exceptions.

        This validates the cleanup pattern that prevents
        'Event loop is closed' errors.
        """
        # Create a simple task that completes immediately
        async def quick_task():
            return "done"

        result = await quick_task()
        assert result == "done"
        # async_cleanup fixture will run after this

    async def test_allows_multiple_awaits(self, async_cleanup: None) -> None:
        """Verify multiple awaits work with cleanup fixture."""
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        # Should complete without event loop errors


@requires_ha
class TestHAFrameworkFixtures:
    """Test fixtures requiring full Home Assistant framework.

    These tests are skipped when the homeassistant package is not available.
    On Windows, this may require enabling Long Path support.
    """

    def test_hass_fixture_available(self, hass: Any) -> None:
        """Verify hass fixture is available and has expected attributes."""
        assert hass is not None
        assert hasattr(hass, "config_entries")
