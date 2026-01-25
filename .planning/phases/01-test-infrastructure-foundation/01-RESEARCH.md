# Phase 1: Test Infrastructure Foundation - Research

**Researched:** 2026-01-25
**Domain:** pytest, pytest-asyncio, pytest-homeassistant-custom-component, async testing patterns
**Confidence:** HIGH

## Summary

This phase establishes test infrastructure for a Home Assistant custom component that communicates with a WebSocket-based gateway. The standard stack is pytest with pytest-homeassistant-custom-component, which extracts testing utilities directly from Home Assistant core. This provides the `hass` fixture, `MockConfigEntry`, and other HA-specific test helpers.

Key challenges are: (1) proper async event loop handling to prevent "Event loop is closed" errors, (2) mocking WebSocket connections for the gateway client, and (3) ensuring fixtures properly cleanup async resources. The pytest-homeassistant-custom-component package handles most HA-specific setup automatically when configured correctly.

**Primary recommendation:** Use pytest-homeassistant-custom-component with `asyncio_mode = "auto"` and `asyncio_default_fixture_loop_scope = "function"` configuration. Create custom fixtures for WebSocket mocking using `unittest.mock.AsyncMock`.

## Standard Stack

The established libraries/tools for Home Assistant custom component testing:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | ^9.0.0 | Test framework | Industry standard, required by HA testing |
| pytest-asyncio | ^1.0.0 | Async test support | Required for testing async HA code |
| pytest-homeassistant-custom-component | ^0.13.289+ | HA testing utilities | Extracts fixtures directly from HA core |
| pytest-cov | ^7.0.0 | Coverage reporting | Standard coverage solution for pytest |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-mock | ^3.12.0 | Mock utilities | Simplified patching syntax |
| aioresponses | ^0.7.4 | HTTP mocking | If testing HTTP calls (not WebSocket) |
| syrupy | ^4.0.0 | Snapshot testing | For complex response validation (optional) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pytest-homeassistant-custom-component | Manual fixtures | Much more setup work, may miss HA patterns |
| AsyncMock | asynctest.CoroutineMock | asynctest is deprecated, AsyncMock is stdlib |
| pytest-cov | coverage alone | pytest-cov integrates better with pytest |

**Installation:**
```bash
pip install pytest pytest-asyncio pytest-homeassistant-custom-component pytest-cov pytest-mock
```

**Note on Python version:** pytest-homeassistant-custom-component tracks Home Assistant core releases. As of January 2026, the latest version (0.13.308) requires Python >=3.13. For Python 3.11/3.12, use an older version aligned with HA releases that support those Python versions (e.g., 0.13.200 range for Python 3.12).

## Architecture Patterns

### Recommended Project Structure
```
clawd-homeassistant/
├── custom_components/
│   └── clawd/
│       ├── __init__.py
│       ├── config_flow.py
│       ├── conversation.py
│       ├── gateway.py
│       ├── gateway_client.py
│       └── ...
├── tests/
│   ├── __init__.py           # Required for pytest discovery
│   ├── conftest.py           # Shared fixtures
│   ├── fixtures/             # JSON/data fixtures for load_fixture()
│   │   └── ...
│   ├── test_const.py         # Unit tests (Phase 2)
│   ├── test_exceptions.py    # Unit tests (Phase 2)
│   └── ...
├── custom_components/__init__.py  # May be required for discovery
└── pyproject.toml            # All configuration here
```

### Pattern 1: Enable Custom Integrations Fixture
**What:** Auto-enable custom integrations for all tests
**When to use:** Always - required for testing custom components
**Example:**
```python
# tests/conftest.py
# Source: https://github.com/MatthewFlamm/pytest-homeassistant-custom-component

import pytest

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations defined in the test dir."""
    yield
```

### Pattern 2: Mock Config Entry Factory
**What:** Factory fixture for creating MockConfigEntry instances
**When to use:** Any test needing a config entry
**Example:**
```python
# tests/conftest.py
# Source: Home Assistant core patterns

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.clawd.const import DOMAIN

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
```

### Pattern 3: WebSocket Mock Fixture
**What:** AsyncMock-based WebSocket simulation
**When to use:** Testing gateway protocol without real connections
**Example:**
```python
# tests/conftest.py
# Source: websockets testing patterns + AsyncMock

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

@pytest.fixture
def mock_websocket():
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
def mock_websocket_connect(mock_websocket):
    """Patch websockets.connect to return mock."""
    with patch("websockets.connect") as mock_connect:
        # websockets.connect returns an async iterator for reconnection
        async def async_gen():
            yield mock_websocket
        mock_connect.return_value = async_gen()
        yield mock_connect, mock_websocket
```

### Pattern 4: Async Cleanup in Fixtures
**What:** Proper teardown of async resources
**When to use:** Any fixture creating async resources (tasks, connections)
**Example:**
```python
# tests/conftest.py
# Source: pytest-asyncio best practices

import pytest
import asyncio

@pytest.fixture
async def gateway_client(hass, mock_config_entry, mock_websocket_connect):
    """Create a gateway client with mocked WebSocket."""
    from custom_components.clawd.gateway_client import ClawdGatewayClient

    client = ClawdGatewayClient(
        host="localhost",
        port=8765,
        token="test-token",
    )

    yield client

    # Cleanup: disconnect and cancel any pending tasks
    await client.disconnect()

    # Give event loop a chance to process cleanup
    await asyncio.sleep(0)
```

### Anti-Patterns to Avoid
- **Creating event_loop fixture:** pytest-homeassistant-custom-component provides this; custom ones conflict
- **Using function scope for expensive fixtures:** Config entries should be function-scoped, but consider session scope for one-time setup
- **Not awaiting cleanup:** Always `await client.disconnect()` in fixture teardown
- **Mocking at wrong level:** Mock `websockets.connect`, not internal methods

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Home Assistant test instance | Custom hass stub | `hass` fixture from pytest-homeassistant-custom-component | HA instance setup is complex, fixture handles all internals |
| Config entry creation | Manual ConfigEntry | `MockConfigEntry` from pytest_homeassistant_custom_component.common | Proper mock with all required methods |
| Async event loop setup | Custom event_loop fixture | pytest-asyncio's built-in loop management | Conflicts with HA's loop policy |
| WebSocket protocol mock | Full protocol implementation | AsyncMock with send/recv | Only mock what you test |
| Test data loading | Manual file reads | `load_fixture()` from pytest_homeassistant_custom_component.common | Handles path resolution, encoding |

**Key insight:** pytest-homeassistant-custom-component extracts the exact testing utilities from Home Assistant core. Using anything else means diverging from how HA itself is tested, risking subtle incompatibilities.

## Common Pitfalls

### Pitfall 1: Event Loop Is Closed Error
**What goes wrong:** Tests fail with `RuntimeError: Event loop is closed` during teardown
**Why it happens:** Async resources (tasks, connections) outlive the event loop; garbage collection triggers cleanup after loop closure
**How to avoid:**
1. Always await cleanup in fixture teardown
2. Cancel pending tasks explicitly before yielding from fixtures
3. Use `await asyncio.sleep(0)` to let cleanup tasks run
4. Set `asyncio_default_fixture_loop_scope = "function"` to ensure fresh loops
**Warning signs:** Errors appear after test passes, not during test execution

### Pitfall 2: Missing enable_custom_integrations
**What goes wrong:** Tests fail to find custom component; `hass.config_entries.async_setup()` fails
**Why it happens:** HA blocks custom components by default in tests
**How to avoid:** Add auto-use fixture that depends on `enable_custom_integrations`
**Warning signs:** "Integration not found" or similar errors

### Pitfall 3: Fixture Order with recorder_mock
**What goes wrong:** Database errors or "recorder not ready" warnings
**Why it happens:** Some fixtures must initialize before `enable_custom_integrations`
**How to avoid:** If using recorder, ensure `recorder_mock` fixture runs first
**Warning signs:** SQLite errors, "recorder" in warning messages

### Pitfall 4: WebSocket Mock Not Awaitable
**What goes wrong:** `TypeError: object MagicMock can't be used in 'await' expression`
**Why it happens:** Using `MagicMock` instead of `AsyncMock` for async methods
**How to avoid:** Use `AsyncMock` for all coroutine methods (send, recv, close, connect)
**Warning signs:** Type errors mentioning await and Mock

### Pitfall 5: Tests Pass Individually But Fail Together
**What goes wrong:** Test suite failures when running all tests, but individual tests pass
**Why it happens:** State leaking between tests, usually from module-scoped fixtures or uncleared hass.data
**How to avoid:** Use function scope for fixtures that hold state; clear `hass.data[DOMAIN]` in teardown
**Warning signs:** Order-dependent failures, "already configured" errors

## Code Examples

Verified patterns from official sources:

### pyproject.toml Configuration
```toml
# Source: pytest-asyncio docs + pytest-cov docs + HA patterns

[project]
name = "clawd-homeassistant"
version = "0.1.0"
requires-python = ">=3.11"

[project.optional-dependencies]
test = [
    "pytest>=9.0.0",
    "pytest-asyncio>=1.0.0",
    "pytest-homeassistant-custom-component>=0.13.200",
    "pytest-cov>=7.0.0",
    "pytest-mock>=3.12.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
addopts = [
    "--strict-markers",
    "-ra",
    "--cov=custom_components/clawd",
    "--cov-report=term-missing",
    "--cov-report=html",
]

[tool.coverage.run]
source = ["custom_components/clawd"]
branch = true

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.:",
]
show_missing = true

[tool.coverage.html]
directory = "htmlcov"
```

### Complete conftest.py Template
```python
# tests/conftest.py
# Source: pytest-homeassistant-custom-component patterns + HA core patterns

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
```

### Basic Test Using Fixtures
```python
# tests/test_example.py
# Source: pytest-homeassistant-custom-component patterns

"""Example test demonstrating fixture usage."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_websocket_connect,
) -> None:
    """Test setting up the integration."""
    mock_connect, mock_ws = mock_websocket_connect

    # Setup expected handshake response
    mock_ws.recv.return_value = '{"type": "res", "id": "test", "ok": true}'

    # Add entry to hass and setup
    mock_config_entry.add_to_hass(hass)

    # This is how you would test setup (actual implementation in later phases)
    # await hass.config_entries.async_setup(mock_config_entry.entry_id)
    # await hass.async_block_till_done()

    # Assert setup succeeded
    # assert mock_config_entry.state is ConfigEntryState.LOADED
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `asyncio_mode = "strict"` | `asyncio_mode = "auto"` | pytest-asyncio 1.0 (May 2025) | Auto mode treats all async def as asyncio fixtures |
| Custom event_loop fixture | Built-in loop management | pytest-asyncio 0.24+ | Don't create custom event_loop fixtures |
| `@pytest_asyncio.fixture` | `@pytest.fixture` for async | pytest-asyncio 1.0 auto mode | Standard decorator works for async in auto mode |
| asynctest.CoroutineMock | unittest.mock.AsyncMock | Python 3.8+ | asynctest is unmaintained, AsyncMock is stdlib |

**Deprecated/outdated:**
- `asynctest` library: Use stdlib `unittest.mock.AsyncMock` instead
- Custom `event_loop` fixtures: Conflicts with pytest-homeassistant-custom-component
- `pytest.ini` file: Use `pyproject.toml` with `[tool.pytest.ini_options]`

## Open Questions

Things that couldn't be fully resolved:

1. **Exact pytest-homeassistant-custom-component version for Python 3.11**
   - What we know: Version 0.13.308 requires Python 3.13; older versions support older Python
   - What's unclear: Exact version cutoff for Python 3.11 support
   - Recommendation: Test with version range `>=0.13.150,<0.13.250` for Python 3.11, or upgrade to Python 3.13

2. **Session-scoped event loop for performance**
   - What we know: Function scope is safest; session scope faster but can leak state
   - What's unclear: Whether HA fixtures work correctly with session-scoped loops
   - Recommendation: Start with function scope; optimize later if test suite becomes slow

3. **WebSocket mock complexity for reconnection tests**
   - What we know: Basic connect/disconnect is straightforward to mock
   - What's unclear: How to properly mock the reconnection iterator pattern in websockets library
   - Recommendation: Start simple; build complexity as Phase 5 (Protocol Layer Tests) requires it

## Sources

### Primary (HIGH confidence)
- [pytest-homeassistant-custom-component GitHub](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component) - Fixture patterns, enable_custom_integrations
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/en/latest/reference/configuration.html) - Configuration options
- [Home Assistant Developer Docs - Testing](https://developers.home-assistant.io/docs/development_testing/) - HA testing patterns

### Secondary (MEDIUM confidence)
- [pytest-asyncio Event Loop Issues](https://github.com/pytest-dev/pytest-asyncio/issues/991) - Cleanup patterns for "Event loop is closed"
- [Home Assistant core conftest.py](https://github.com/home-assistant/core/blob/dev/tests/conftest.py) - verify_cleanup, hass fixture details
- [websockets library testing discussion](https://github.com/aaugustin/websockets/issues/282) - WebSocket mock patterns

### Tertiary (LOW confidence)
- [onyx-homeassistant-integration pyproject.toml](https://github.com/muhlba91/onyx-homeassistant-integration/blob/main/pyproject.toml) - Example configuration (may differ from best practices)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Direct from official documentation and PyPI
- Architecture: HIGH - Patterns from HA core and pytest-homeassistant-custom-component
- Pitfalls: MEDIUM - Gathered from GitHub issues and community discussions

**Research date:** 2026-01-25
**Valid until:** 2026-02-25 (30 days - stable domain, but check pytest-asyncio releases)
