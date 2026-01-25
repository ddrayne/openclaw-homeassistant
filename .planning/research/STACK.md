# Technology Stack: Home Assistant Integration Testing

**Project:** Clawd Voice Assistant Integration
**Researched:** 2025-01-25
**Confidence:** MEDIUM (based on training data and project inspection, unable to verify latest versions via external sources)

## Executive Summary

Home Assistant custom integrations use a specific testing stack centered around pytest with async support. For this WebSocket-based integration, the stack needs to handle:
1. Async test execution (pytest-asyncio)
2. Home Assistant test fixtures and mocking (pytest-homeassistant-custom-component)
3. WebSocket connection mocking (pytest-aiohttp or manual async mocks)
4. Code coverage measurement (pytest-cov)
5. Time-based testing (freezegun for datetime mocking)

## Recommended Stack

### Core Testing Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pytest | ^8.0.0 | Test framework | Industry standard, excellent async support, required by Home Assistant ecosystem |
| pytest-asyncio | ^0.23.0 | Async test support | Essential for testing async Home Assistant code, handles event loops correctly |
| pytest-cov | ^4.1.0 | Coverage reporting | Generates coverage reports, integrates with pytest, supports branch coverage |
| pytest-timeout | ^2.2.0 | Test timeout enforcement | Prevents hanging async tests, essential for WebSocket tests |

### Home Assistant Testing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pytest-homeassistant-custom-component | ^0.13.0 | HA test fixtures | Provides hass fixture, mock config entries, standard HA test utilities |
| homeassistant | latest | HA core for testing | Required to test integration, use same version as minimum supported |

**Note on pytest-homeassistant-custom-component**: This package provides critical fixtures like `hass` (mocked Home Assistant instance), `aioclient_mock`, and helpers for config entries. It's the standard for custom component testing.

### Mocking Libraries

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pytest-aiohttp | ^1.0.5 | Async HTTP/WebSocket mocking | Provides `aiohttp_client` fixture, can mock WebSocket connections |
| aioresponses | ^0.7.6 | HTTP request mocking | Mocks aiohttp client sessions, useful for external API calls |
| asynctest | N/A (deprecated) | Async mocking | **DO NOT USE** - deprecated, use unittest.mock with async support instead |

**WebSocket Mocking Strategy**: For `websockets>=12.0` library (not aiohttp), use `unittest.mock.AsyncMock` to mock WebSocket connections. The `pytest-aiohttp` library is for aiohttp-based WebSockets, not the `websockets` library.

### Time and State Mocking

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| freezegun | ^1.4.0 | Datetime mocking | Freeze time for testing timeouts, schedules, time-based logic |
| time-machine | ^2.13.0 | Alternative time mocking | More feature-rich than freezegun, but freezegun is HA standard |

**Recommendation**: Use `freezegun` as it's more widely adopted in the HA ecosystem, despite `time-machine` having better async support.

### Code Quality

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pytest-xdist | ^3.5.0 | Parallel test execution | Speed up test suite, run tests in parallel |
| coverage[toml] | ^7.4.0 | Coverage engine | Core coverage library, pytest-cov uses this |

## Supporting Tools (Dev Dependencies)

| Technology | Version | Purpose | When to Use |
|------------|---------|---------|-------------|
| mypy | ^1.8.0 | Type checking | Run alongside tests, catch type errors |
| ruff | ^0.1.0 | Linting | Fast Python linter, replaces flake8/black/isort |
| pre-commit | ^3.6.0 | Git hooks | Run tests/linting before commits |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Async testing | pytest-asyncio | trio-testing | Home Assistant uses asyncio, not trio |
| WebSocket mocking | unittest.mock.AsyncMock | websocket-mock | websocket-mock is unmaintained, manual mocks more flexible |
| Coverage | pytest-cov | coverage.py directly | pytest-cov provides better integration |
| Time mocking | freezegun | time-machine | freezegun is HA ecosystem standard |
| Async mocking | unittest.mock | asynctest | asynctest deprecated since Python 3.8 |

## Installation

### Core Testing Dependencies

```toml
# Add to pyproject.toml [project.optional-dependencies]
[project.optional-dependencies]
test = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "pytest-timeout>=2.2.0",
    "pytest-homeassistant-custom-component>=0.13.0",
    "pytest-aiohttp>=1.0.5",
    "freezegun>=1.4.0",
    "pytest-xdist>=3.5.0",
]
```

### Alternative: requirements_test.txt

```txt
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-cov>=4.1.0
pytest-timeout>=2.2.0
pytest-homeassistant-custom-component>=0.13.0
pytest-aiohttp>=1.0.5
freezegun>=1.4.0
pytest-xdist>=3.5.0
```

### Install Command

```bash
# Using pip
pip install -e ".[test]"

# Or with requirements file
pip install -r requirements_test.txt
```

## Configuration Files

### pytest.ini or pyproject.toml

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
timeout = 30
addopts = [
    "--cov=custom_components.clawd",
    "--cov-report=term-missing",
    "--cov-report=html",
    "--cov-branch",
    "-v",
]
```

### .coveragerc or pyproject.toml

```toml
[tool.coverage.run]
source = ["custom_components/clawd"]
omit = [
    "tests/*",
    "*/__pycache__/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]
```

## WebSocket Testing Strategy

Since this integration uses `websockets>=12.0` (not aiohttp), the mocking approach is:

1. **Mock at the GatewayProtocol level**: Use `unittest.mock.AsyncMock` to replace the WebSocket client
2. **Mock websockets.connect()**: Patch the connect function to return a mock WebSocket
3. **Simulate message flow**: Mock send/recv to simulate Gateway protocol
4. **Test connection states**: Mock connection/disconnection scenarios

### Example Mock Structure

```python
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection."""
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock()
    ws.close = AsyncMock()
    return ws

@pytest.fixture
def mock_websocket_connect(mock_websocket):
    """Mock websockets.connect()."""
    with patch("websockets.connect") as mock_connect:
        # Return async context manager
        mock_connect.return_value.__aenter__.return_value = mock_websocket
        yield mock_connect
```

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures
├── test_init.py            # Integration setup/teardown tests
├── test_config_flow.py     # Config flow tests
├── test_conversation.py    # Conversation entity tests
├── test_gateway.py         # Low-level WebSocket protocol tests
├── test_gateway_client.py  # High-level client tests
└── fixtures/
    ├── gateway_responses.json  # Sample Gateway responses
    └── agent_events.json       # Sample agent events
```

## Running Tests

```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest tests/test_gateway.py

# Run with parallel execution
pytest -n auto

# Run with verbose output
pytest -v

# Run only async tests
pytest -k "async"

# Generate HTML coverage report
pytest --cov-report=html
open htmlcov/index.html
```

## Coverage Target

**Goal: ~90% coverage**

Focus areas for high coverage:
- Core logic: gateway.py, gateway_client.py (aim for 95%+)
- Integration glue: __init__.py, conversation.py (aim for 90%+)
- Config flow: config_flow.py (aim for 85%+)

Acceptable lower coverage:
- Exception handlers (hard to trigger all edge cases)
- Reconnection logic (complex async timing)
- Error recovery paths (may require integration tests)

## Confidence Assessment

| Component | Confidence | Notes |
|-----------|-----------|-------|
| pytest ecosystem | HIGH | Standard Python testing, well-documented |
| pytest-homeassistant-custom-component | HIGH | Official HA testing package |
| WebSocket mocking approach | MEDIUM | Correct approach but version numbers unverified |
| Version numbers | LOW | Unable to verify latest versions without external access |
| Home Assistant compatibility | MEDIUM | Based on manifest.json analysis |

## Verification Needed

The following should be verified before finalizing:

1. **Latest pytest-homeassistant-custom-component version**: Check PyPI for current version
2. **Home Assistant minimum version compatibility**: Verify test fixtures work with HA 2024.1.0+
3. **websockets library testing patterns**: Review websockets documentation for recommended test approaches
4. **pytest-asyncio compatibility**: Ensure version compatible with Python 3.13.9 (detected in environment)

## Sources

**Primary sources:**
- Project inspection: manifest.json, existing code structure
- Home Assistant development patterns (from training data)
- pytest and pytest-asyncio documentation (from training data)

**Unable to verify (external sources blocked):**
- Home Assistant developer documentation (developers.home-assistant.io)
- PyPI latest versions
- Current community practices (GitHub, forums)

**Recommendation**: Verify all version numbers with PyPI before installation.

## Next Steps for Implementation

1. Create `pyproject.toml` with test dependencies
2. Set up `pytest.ini` with async configuration
3. Create `tests/conftest.py` with shared fixtures
4. Implement WebSocket mock fixtures
5. Write initial tests for gateway.py (protocol layer)
6. Add tests for gateway_client.py (client layer)
7. Test integration setup/teardown
8. Add config flow tests
9. Test conversation entity
10. Measure coverage and fill gaps
