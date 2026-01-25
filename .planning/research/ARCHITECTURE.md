# Test Architecture for Home Assistant Integration

**Domain:** Home Assistant Custom Integration Testing
**Researched:** 2026-01-25
**Confidence:** HIGH (based on Home Assistant official patterns and pytest best practices)

## Recommended Test Architecture

### Directory Structure

```
clawd-homeassistant/
├── custom_components/
│   └── clawd/                    # Production code
│       ├── __init__.py
│       ├── config_flow.py
│       ├── conversation.py
│       ├── gateway.py
│       ├── gateway_client.py
│       ├── exceptions.py
│       └── const.py
├── tests/                         # Test suite root
│   ├── conftest.py               # Shared fixtures and pytest config
│   ├── __init__.py
│   │
│   ├── fixtures/                 # Test data and mock objects
│   │   ├── __init__.py
│   │   ├── gateway_responses.py  # Sample Gateway protocol responses
│   │   └── mock_gateway.py       # Mock Gateway server implementation
│   │
│   ├── test_init.py              # Tests for __init__.py (setup/teardown)
│   ├── test_config_flow.py       # Tests for config_flow.py
│   ├── test_conversation.py      # Tests for conversation.py
│   ├── test_gateway.py           # Tests for gateway.py (protocol layer)
│   ├── test_gateway_client.py    # Tests for gateway_client.py
│   └── test_exceptions.py        # Tests for exception hierarchy
│
├── pytest.ini                     # Pytest configuration
└── pyproject.toml                 # Build config (if adding test dependencies)
```

**Rationale:**
- **Parallel structure**: `tests/` mirrors `custom_components/clawd/` with `test_*.py` naming
- **Fixtures isolation**: Dedicated `fixtures/` directory separates test data from test logic
- **conftest.py centralization**: Shared fixtures available to all test modules
- **Flat test hierarchy**: Home Assistant integrations are typically simple enough for flat structure

### Component Test Boundaries

| Component | Test File | Responsibility | Dependencies to Mock |
|-----------|-----------|----------------|---------------------|
| Integration setup/teardown | `test_init.py` | async_setup_entry(), async_unload_entry(), reload | HomeAssistant hass, ConfigEntry, GatewayClient |
| Configuration flow | `test_config_flow.py` | User input validation, connection testing, options | GatewayClient.connect(), GatewayClient.health() |
| Conversation entity | `test_conversation.py` | Message handling, emoji stripping, error responses | GatewayClient.send_agent_request(), ConversationInput |
| Gateway protocol | `test_gateway.py` | WebSocket handshake, reconnection, event dispatch | websockets.connect(), WebSocket messages |
| Gateway client | `test_gateway_client.py` | AgentRun buffering, request correlation, timeouts | GatewayProtocol.send_request(), event callbacks |
| Exception hierarchy | `test_exceptions.py` | Exception types, inheritance, string representation | None (pure logic) |

### Test Data Flow

**Unit Test Flow (per component):**

```
1. Arrange: Setup fixtures (mock hass, mock client, test data)
2. Act: Call component function (async_setup_entry, send_agent_request, etc.)
3. Assert: Verify expected behavior (state changes, method calls, return values)
4. Cleanup: Fixtures auto-cleanup via pytest teardown
```

**Integration Test Flow (cross-component):**

```
1. Arrange: Setup mock Gateway server + real GatewayProtocol + real GatewayClient
2. Act: Send real WebSocket messages through the stack
3. Assert: Verify end-to-end behavior (events buffered, response returned)
4. Cleanup: Disconnect and cleanup mock server
```

## Fixture Organization

### conftest.py Structure

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================

pytest_plugins = "pytest_homeassistant_custom_component"

# ============================================================================
# HOME ASSISTANT FIXTURES
# ============================================================================

@pytest.fixture
def hass(event_loop):
    """Fixture for Home Assistant instance."""
    # pytest-homeassistant-custom-component provides this
    # Or manually create mock if plugin not available
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}
    hass.loop = event_loop
    return hass

@pytest.fixture
def config_entry():
    """Fixture for ConfigEntry with standard test data."""
    return ConfigEntry(
        version=1,
        domain="clawd",
        title="Clawd Gateway (192.168.1.100)",
        data={
            "host": "192.168.1.100",
            "port": 18789,
            "token": "test-token-123",
            "use_ssl": False,
            "timeout": 30,
            "session_key": "main",
            "strip_emojis": True,
        },
        source="user",
        entry_id="test-entry-id",
    )

# ============================================================================
# GATEWAY MOCK FIXTURES
# ============================================================================

@pytest.fixture
def mock_gateway_protocol():
    """Fixture for mocked GatewayProtocol."""
    with patch("custom_components.clawd.gateway_client.GatewayProtocol") as mock:
        instance = mock.return_value
        instance.connected = True
        instance._connected_event = AsyncMock()
        instance.connect = AsyncMock()
        instance.disconnect = AsyncMock()
        instance.send_request = AsyncMock()
        yield instance

@pytest.fixture
def mock_websocket():
    """Fixture for mocked WebSocket connection."""
    with patch("websockets.connect") as mock:
        ws = AsyncMock()
        ws.send = AsyncMock()
        ws.recv = AsyncMock()
        ws.close = AsyncMock()
        mock.return_value.__aenter__.return_value = ws
        yield ws

# ============================================================================
# TEST DATA FIXTURES
# ============================================================================

@pytest.fixture
def agent_request_ack():
    """Fixture for successful agent request acknowledgment."""
    return {
        "type": "res",
        "id": "request-123",
        "ok": True,
        "payload": {
            "runId": "run-abc-123",
        },
    }

@pytest.fixture
def agent_output_event():
    """Fixture for agent output event."""
    return {
        "type": "event",
        "event": "agent",
        "payload": {
            "runId": "run-abc-123",
            "output": "Hello, I'm Claude!",
            "data": {
                "text": "Hello, I'm Claude!",
                "phase": "responding",
            },
        },
    }

@pytest.fixture
def agent_complete_event():
    """Fixture for agent completion event."""
    return {
        "type": "event",
        "event": "agent",
        "payload": {
            "runId": "run-abc-123",
            "status": "ok",
            "summary": "Hello, I'm Claude!",
        },
    }

# ============================================================================
# ASYNC TEST UTILITIES
# ============================================================================

@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
```

**Fixture Categories:**

1. **Home Assistant Fixtures**: Mock hass, config_entry, entity registry
2. **Gateway Mock Fixtures**: mock_gateway_protocol, mock_websocket, mock responses
3. **Test Data Fixtures**: Sample Gateway messages, error responses, edge cases
4. **Async Utilities**: event_loop, timeout helpers, async context managers

### Fixture Scope Strategy

| Fixture | Scope | Reason |
|---------|-------|--------|
| `hass` | function | Each test needs isolated state |
| `config_entry` | function | Tests modify entry data |
| `mock_gateway_protocol` | function | Reset mock call counts per test |
| `mock_websocket` | function | Reset message queues per test |
| `event_loop` | function | Isolated async context per test |
| `agent_request_ack` | session | Immutable test data, can reuse |

**Anti-pattern to avoid**: Session-scoped fixtures for stateful objects (leads to test pollution)

## Mock Patterns for WebSocket and Home Assistant

### Pattern 1: Mock WebSocket Connection

**Use case:** Test protocol layer without real WebSocket

```python
# tests/test_gateway.py
import pytest
from custom_components.clawd.gateway import GatewayProtocol

@pytest.mark.asyncio
async def test_handshake_success(mock_websocket):
    """Test successful handshake."""
    # Arrange
    mock_websocket.recv.return_value = json.dumps({
        "type": "res",
        "id": "request-123",
        "ok": True,
        "payload": {"protocol": 1},
    })

    protocol = GatewayProtocol("localhost", 18789, None, False)

    # Act
    async with websockets.connect(...) as ws:
        await protocol._handshake()

    # Assert
    assert mock_websocket.send.called
    assert protocol.connected
```

**Pattern characteristics:**
- **Mock websockets.connect()** context manager
- **Control recv() return values** to simulate Gateway responses
- **Verify send() calls** to check outgoing messages
- **Use AsyncMock** for async methods

### Pattern 2: Mock Home Assistant Core

**Use case:** Test integration setup without real Home Assistant

```python
# tests/test_init.py
import pytest
from custom_components.clawd import async_setup_entry

@pytest.mark.asyncio
async def test_setup_entry_success(hass, config_entry, mock_gateway_protocol):
    """Test successful integration setup."""
    # Arrange
    mock_gateway_protocol.connect.return_value = None
    mock_gateway_protocol._connected_event.wait.return_value = None

    # Act
    result = await async_setup_entry(hass, config_entry)

    # Assert
    assert result is True
    assert "clawd" in hass.data
    assert config_entry.entry_id in hass.data["clawd"]
    mock_gateway_protocol.connect.assert_called_once()
```

**Pattern characteristics:**
- **Mock hass.data** as plain dict
- **Mock async_forward_entry_setups** to skip platform loading
- **Verify client stored** in hass.data[DOMAIN][entry_id]
- **Assert connection called** on client

### Pattern 3: Mock Gateway Client Responses

**Use case:** Test conversation entity without real Gateway

```python
# tests/test_conversation.py
import pytest
from custom_components.clawd.conversation import ClawdConversationEntity

@pytest.mark.asyncio
async def test_message_handling_success(config_entry, mock_gateway_client):
    """Test successful message handling."""
    # Arrange
    mock_gateway_client.send_agent_request.return_value = "Hello! 👋"
    entity = ClawdConversationEntity(config_entry, mock_gateway_client)

    user_input = ConversationInput(
        text="Hello",
        conversation_id="test-conv-123",
        language="en",
        agent_id="clawd",
    )
    chat_log = ChatLog()

    # Act
    result = await entity._async_handle_message(user_input, chat_log)

    # Assert
    assert result.response.speech["plain"]["speech"] == "Hello!"  # Emoji stripped
    mock_gateway_client.send_agent_request.assert_called_once_with("Hello")
```

**Pattern characteristics:**
- **Mock send_agent_request()** return value
- **Verify emoji stripping** based on config
- **Check error handling** with exception side effects
- **Validate intent response** format

### Pattern 4: Real Gateway Protocol + Mock WebSocket (Hybrid)

**Use case:** Test client layer with real protocol logic but fake transport

```python
# tests/test_gateway_client.py
import pytest
from custom_components.clawd.gateway_client import ClawdGatewayClient, AgentRun

@pytest.mark.asyncio
async def test_agent_run_buffering(mock_websocket):
    """Test AgentRun cumulative text buffering."""
    # Arrange
    agent_run = AgentRun("run-123")

    # Act: Simulate cumulative text updates (Gateway behavior)
    agent_run.add_output("Hello")
    agent_run.add_output("Hello, I'm")
    agent_run.add_output("Hello, I'm Claude!")

    # Assert: Text accumulated correctly
    assert agent_run.get_response() == "Hello, I'm Claude!"
```

**Pattern characteristics:**
- **Test real AgentRun logic** without mocking
- **Simulate cumulative updates** matching Gateway protocol
- **Verify edge cases**: non-cumulative updates, empty strings, duplicate text

### Pattern 5: Mock Gateway Server (Integration Testing)

**Use case:** End-to-end test with real WebSocket but controlled responses

```python
# tests/fixtures/mock_gateway.py
import asyncio
import json
import websockets

class MockGatewayServer:
    """Mock Gateway server for integration testing."""

    def __init__(self, host="localhost", port=18790):
        self.host = host
        self.port = port
        self.server = None
        self.messages_sent = []

    async def start(self):
        """Start mock Gateway server."""
        self.server = await websockets.serve(
            self._handle_connection,
            self.host,
            self.port,
        )

    async def stop(self):
        """Stop mock Gateway server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _handle_connection(self, websocket, path):
        """Handle WebSocket connection."""
        async for message in websocket:
            request = json.loads(message)

            # Mock handshake response
            if request["method"] == "connect":
                response = {
                    "type": "res",
                    "id": request["id"],
                    "ok": True,
                    "payload": {},
                }
                await websocket.send(json.dumps(response))

            # Mock agent request
            elif request["method"] == "agent":
                # Send acknowledgment
                ack = {
                    "type": "res",
                    "id": request["id"],
                    "ok": True,
                    "payload": {"runId": "test-run-123"},
                }
                await websocket.send(json.dumps(ack))

                # Send agent output event
                event = {
                    "type": "event",
                    "event": "agent",
                    "payload": {
                        "runId": "test-run-123",
                        "output": "Mock response",
                        "status": "ok",
                    },
                }
                await websocket.send(json.dumps(event))

# tests/test_integration.py
@pytest.mark.asyncio
async def test_end_to_end_agent_request():
    """Test full request/response flow with mock Gateway."""
    # Arrange
    mock_server = MockGatewayServer()
    await mock_server.start()

    client = ClawdGatewayClient("localhost", 18790, None, False)
    await client.connect()

    try:
        # Act
        response = await client.send_agent_request("test message")

        # Assert
        assert response == "Mock response"
    finally:
        await client.disconnect()
        await mock_server.stop()
```

**Pattern characteristics:**
- **Real WebSocket connection** between client and mock server
- **Control response timing** to test timeouts
- **Verify protocol compliance** end-to-end
- **Test reconnection logic** by stopping/restarting server

## Mock vs Real Decision Matrix

| Layer | Mock | Real | Rationale |
|-------|------|------|-----------|
| **websockets.connect()** | ✓ (unit tests) | ✓ (integration tests) | Unit: isolate protocol logic; Integration: verify WebSocket handling |
| **GatewayProtocol** | ✓ (client tests) | ✓ (integration tests) | Client tests focus on buffering; Integration tests verify full stack |
| **ClawdGatewayClient** | ✓ (conversation tests) | ✓ (integration tests) | Conversation tests focus on response formatting |
| **Home Assistant hass** | ✓ (always) | Never | Too heavyweight; mock suffices for state storage verification |
| **AgentRun** | Never | ✓ (always) | Core logic under test; mocking defeats purpose |
| **Event handlers** | ✓ (protocol tests) | ✓ (client tests) | Protocol: verify dispatch; Client: verify buffering logic |

**General rule**: Mock one layer up from what you're testing. If testing GatewayClient, mock GatewayProtocol. If testing GatewayProtocol, mock websockets.

## Async Testing Patterns

### Pattern 1: pytest-asyncio Decorator

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    """Test async function."""
    result = await some_async_function()
    assert result == expected
```

**Use for**: All async test functions

### Pattern 2: Async Context Managers

```python
@pytest.mark.asyncio
async def test_connection_lifecycle():
    """Test connection setup and teardown."""
    client = ClawdGatewayClient("localhost", 18789, None, False)

    # Act
    await client.connect()
    assert client.connected

    # Cleanup
    await client.disconnect()
    assert not client.connected
```

**Use for**: Resource lifecycle tests (connect/disconnect)

### Pattern 3: Timeout Testing with asyncio.wait_for

```python
@pytest.mark.asyncio
async def test_request_timeout():
    """Test request timeout handling."""
    client = ClawdGatewayClient("localhost", 18789, None, False, timeout=0.1)

    # Mock never completes
    with patch.object(client._gateway, "send_request") as mock_send:
        mock_send.return_value = asyncio.Future()  # Never resolves

        # Act & Assert
        with pytest.raises(GatewayTimeoutError):
            await client.send_agent_request("test")
```

**Use for**: Testing timeout behavior in send_agent_request(), handshake, etc.

### Pattern 4: Event Coordination

```python
@pytest.mark.asyncio
async def test_event_coordination():
    """Test asyncio.Event signaling."""
    agent_run = AgentRun("run-123")

    # Setup completion in background
    async def complete_later():
        await asyncio.sleep(0.1)
        agent_run.set_complete("ok", "Done")

    asyncio.create_task(complete_later())

    # Wait for completion
    await asyncio.wait_for(agent_run.complete_event.wait(), timeout=1.0)
    assert agent_run.status == "ok"
```

**Use for**: Testing AgentRun completion signaling, connection event coordination

### Pattern 5: Async Mock Side Effects

```python
@pytest.mark.asyncio
async def test_connection_error_handling():
    """Test handling of connection errors."""
    mock_gateway = AsyncMock()
    mock_gateway.send_request.side_effect = GatewayConnectionError("Connection lost")

    client = ClawdGatewayClient("localhost", 18789, None, False)
    client._gateway = mock_gateway

    # Act & Assert
    with pytest.raises(AgentExecutionError):
        await client.send_agent_request("test")
```

**Use for**: Testing error paths with async exceptions

## Suggested Build Order for Test Implementation

### Phase 1: Foundation (Test Infrastructure)

**Why first:** Enables all subsequent testing

**Files:**
1. `pytest.ini` - Basic pytest config
2. `tests/conftest.py` - Core fixtures (hass, config_entry, event_loop)
3. `tests/__init__.py` - Empty marker file

**Validation:** `pytest --collect-only` shows 0 tests but no errors

### Phase 2: Simple Units (Pure Logic)

**Why next:** No async, no mocking complexity

**Files:**
1. `tests/test_exceptions.py` - Exception hierarchy tests
2. `tests/test_conversation.py` (emoji stripping only) - Pure regex logic

**Tests:**
- Exception inheritance chain
- Exception string representations
- Emoji pattern matching edge cases

**Validation:** `pytest tests/test_exceptions.py -v` passes

### Phase 3: Client Layer (AgentRun Buffering)

**Why next:** Real logic with async but minimal dependencies

**Files:**
1. `tests/test_gateway_client.py` (AgentRun only)

**Tests:**
- Cumulative text buffering
- Completion event signaling
- Non-cumulative text handling
- Status vs phase completion signals

**Validation:** `pytest tests/test_gateway_client.py::test_agent_run_* -v` passes

### Phase 4: Mock Gateway Protocol

**Why next:** Establishes mocking pattern for complex dependencies

**Files:**
1. `tests/conftest.py` (add mock_gateway_protocol fixture)
2. `tests/test_gateway_client.py` (send_agent_request with mocks)

**Tests:**
- send_agent_request() happy path
- Timeout handling
- Error response handling
- Request correlation

**Validation:** `pytest tests/test_gateway_client.py -v` passes

### Phase 5: Conversation Entity

**Why next:** Builds on client mocks, adds Home Assistant types

**Files:**
1. `tests/conftest.py` (add ConversationInput, ChatLog fixtures)
2. `tests/test_conversation.py` (full entity tests)

**Tests:**
- Message handling success
- Emoji stripping configuration
- Error handling (connection, timeout, agent errors)
- Intent response formatting

**Validation:** `pytest tests/test_conversation.py -v` passes

### Phase 6: Config Flow

**Why next:** Complex Home Assistant integration, multiple paths

**Files:**
1. `tests/test_config_flow.py`

**Tests:**
- User step with valid input
- Connection validation failure
- Duplicate entry prevention
- SSL warning on remote connections
- Options flow

**Validation:** `pytest tests/test_config_flow.py -v` passes

### Phase 7: Integration Setup/Teardown

**Why next:** Tests full integration lifecycle

**Files:**
1. `tests/test_init.py`

**Tests:**
- async_setup_entry() success
- Setup with connection failure
- async_unload_entry() cleanup
- Reload entry

**Validation:** `pytest tests/test_init.py -v` passes

### Phase 8: Protocol Layer (Complex WebSocket Mocking)

**Why next:** Most complex mocking, benefits from prior patterns

**Files:**
1. `tests/conftest.py` (add mock_websocket fixture)
2. `tests/test_gateway.py`

**Tests:**
- Handshake success/failure
- Authentication error handling
- Message dispatch (response vs event)
- Event handler registration
- Request timeout

**Validation:** `pytest tests/test_gateway.py -v` passes

### Phase 9: Mock Gateway Server

**Why next:** Infrastructure for integration tests

**Files:**
1. `tests/fixtures/mock_gateway.py`
2. `tests/conftest.py` (add mock_gateway_server fixture)

**Tests:**
- Mock server start/stop
- Handshake exchange
- Agent request/response flow
- Event streaming

**Validation:** Mock server runs and accepts connections

### Phase 10: Integration Tests

**Why last:** Requires all prior infrastructure

**Files:**
1. `tests/test_integration.py`

**Tests:**
- End-to-end agent request
- Connection lifecycle (connect, disconnect, reconnect)
- Timeout with slow mock server
- Multiple concurrent requests

**Validation:** `pytest tests/test_integration.py -v` passes

### Build Order Summary

| Phase | Complexity | Async | Mocking | Dependencies |
|-------|-----------|-------|---------|--------------|
| 1. Infrastructure | Low | No | No | None |
| 2. Simple units | Low | No | No | Infrastructure |
| 3. AgentRun | Medium | Yes | No | Infrastructure |
| 4. Client mocked | Medium | Yes | Protocol | Phase 3 |
| 5. Conversation | Medium | Yes | Client | Phase 4 |
| 6. Config flow | High | Yes | Client, HA | Phase 4 |
| 7. Init | Medium | Yes | Client, HA | Phase 4 |
| 8. Protocol | High | Yes | WebSocket | Phase 4 |
| 9. Mock server | High | Yes | No | Phase 8 |
| 10. Integration | High | Yes | Server | Phase 9 |

**Dependencies graph:**
```
Infrastructure (1)
    ↓
Simple Units (2) → AgentRun (3)
                       ↓
                   Mock Protocol (4)
                       ↓
            ┌──────────┼──────────┬──────────┐
            ↓          ↓          ↓          ↓
    Conversation (5)  Config (6)  Init (7)  Protocol (8)
                                              ↓
                                         Mock Server (9)
                                              ↓
                                         Integration (10)
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Mocking Too Much

**Bad:**
```python
@pytest.mark.asyncio
async def test_agent_run_buffering():
    mock_run = MagicMock(spec=AgentRun)
    mock_run.add_output.return_value = None
    mock_run.get_response.return_value = "test"
    # Test does nothing - just verifies mock behavior
```

**Good:**
```python
@pytest.mark.asyncio
async def test_agent_run_buffering():
    agent_run = AgentRun("run-123")  # Real instance
    agent_run.add_output("Hello")
    agent_run.add_output("Hello, world")
    assert agent_run.get_response() == "Hello, world"
```

**Why:** AgentRun is the logic under test. Mocking it defeats the purpose.

### Anti-Pattern 2: Session-Scoped Stateful Fixtures

**Bad:**
```python
@pytest.fixture(scope="session")
def hass():
    """Reused across all tests - will accumulate state!"""
    return MagicMock(spec=HomeAssistant, data={})
```

**Good:**
```python
@pytest.fixture(scope="function")
def hass():
    """Fresh instance per test - isolated state."""
    return MagicMock(spec=HomeAssistant, data={})
```

**Why:** hass.data accumulates across tests, causing pollution and order-dependent failures.

### Anti-Pattern 3: Ignoring Async Cleanup

**Bad:**
```python
@pytest.mark.asyncio
async def test_connection():
    client = ClawdGatewayClient("localhost", 18789, None, False)
    await client.connect()
    assert client.connected
    # No disconnect - leaks resources!
```

**Good:**
```python
@pytest.mark.asyncio
async def test_connection():
    client = ClawdGatewayClient("localhost", 18789, None, False)
    try:
        await client.connect()
        assert client.connected
    finally:
        await client.disconnect()
```

**Why:** Unclosed connections leak resources and cause flaky tests.

### Anti-Pattern 4: Testing Implementation Details

**Bad:**
```python
@pytest.mark.asyncio
async def test_internal_handler():
    protocol = GatewayProtocol("localhost", 18789, None, False)
    message = {"type": "res", "id": "123", "ok": True}
    await protocol._handle_message(message)  # Testing private method
```

**Good:**
```python
@pytest.mark.asyncio
async def test_request_response_correlation():
    protocol = GatewayProtocol("localhost", 18789, None, False)
    # Test via public API that exercises _handle_message internally
    response = await protocol.send_request("health")
    assert response["ok"]
```

**Why:** Testing private methods couples tests to implementation, makes refactoring fragile.

### Anti-Pattern 5: Broad Exception Catching in Tests

**Bad:**
```python
@pytest.mark.asyncio
async def test_connection_error():
    try:
        await client.send_agent_request("test")
    except Exception:  # Too broad!
        pass  # Expected
```

**Good:**
```python
@pytest.mark.asyncio
async def test_connection_error():
    with pytest.raises(GatewayConnectionError):
        await client.send_agent_request("test")
```

**Why:** Broad catch hides unexpected errors (like AttributeError from bugs).

## Architecture Patterns

### Pattern 1: Layered Mocking Strategy

**Principle:** Mock one layer up from what you're testing

```
Test Layer          | Mock                    | Real
--------------------|-------------------------|------------------------
Conversation Entity | ClawdGatewayClient      | emoji stripping, response formatting
Client (send)       | GatewayProtocol         | AgentRun buffering, timeout logic
Client (AgentRun)   | Nothing                 | Full AgentRun class
Protocol            | websockets.connect()    | Handshake, event dispatch, message correlation
Integration         | Nothing or Mock Server  | Full stack
```

### Pattern 2: Fixture Composition

**Principle:** Build complex fixtures from simple ones

```python
@pytest.fixture
def basic_config():
    """Minimal config."""
    return {"host": "localhost", "port": 18789}

@pytest.fixture
def auth_config(basic_config):
    """Config with auth."""
    return {**basic_config, "token": "test-token"}

@pytest.fixture
def full_config(auth_config):
    """Complete config with all options."""
    return {
        **auth_config,
        "use_ssl": True,
        "timeout": 60,
        "session_key": "custom",
        "strip_emojis": False,
    }
```

**Benefits:** DRY, flexible test parameterization, clear intent

### Pattern 3: Error Path Parametrization

**Principle:** Test all error paths with single test function

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("exception,expected_message", [
    (GatewayConnectionError("Lost connection"), "trouble connecting"),
    (GatewayTimeoutError("Timeout"), "took too long"),
    (AgentExecutionError("Failed"), "error while processing"),
])
async def test_conversation_error_handling(exception, expected_message, mock_client):
    """Test all error paths in conversation handler."""
    mock_client.send_agent_request.side_effect = exception
    entity = ClawdConversationEntity(config_entry, mock_client)

    result = await entity._async_handle_message(user_input, chat_log)

    assert expected_message in result.response.speech["plain"]["speech"]
```

**Benefits:** Complete coverage, prevents error path gaps, maintainable

## Test Quality Metrics

**Code coverage targets:**
- **Overall**: 80%+ (goal: 90%)
- **Core logic** (AgentRun, emoji stripping): 95%+
- **Error paths**: 85%+ (all exception types covered)
- **Integration setup**: 75%+ (config flow, platform setup)

**Test count estimates:**
| Module | Unit Tests | Integration Tests | Total |
|--------|-----------|-------------------|-------|
| exceptions.py | 5 | 0 | 5 |
| conversation.py | 8 | 2 | 10 |
| gateway_client.py | 15 | 3 | 18 |
| gateway.py | 12 | 3 | 15 |
| config_flow.py | 10 | 2 | 12 |
| __init__.py | 6 | 2 | 8 |
| **Total** | **56** | **12** | **68** |

**Performance targets:**
- **Unit test suite**: < 5 seconds
- **Integration test suite**: < 15 seconds
- **Full test suite**: < 20 seconds

## Roadmap Implications

### Phase Structure Recommendation

**Phase 1: Test Infrastructure + Simple Units (1 week)**
- Setup pytest, conftest.py, basic fixtures
- Test exceptions, emoji stripping
- **Deliverable**: Infrastructure validated, first tests passing

**Phase 2: Core Logic Tests (1 week)**
- AgentRun buffering tests
- Mock GatewayProtocol
- Test gateway_client.py with mocks
- **Deliverable**: Client layer fully tested

**Phase 3: Integration Layer Tests (1 week)**
- Conversation entity tests
- Config flow tests
- Integration setup/teardown tests
- **Deliverable**: Home Assistant integration tested

**Phase 4: Protocol Layer Tests (1 week)**
- Mock WebSocket tests
- Protocol handshake, reconnection, event dispatch
- **Deliverable**: Full protocol layer coverage

**Phase 5: Integration Tests + CI (1 week)**
- Mock Gateway server
- End-to-end integration tests
- CI configuration (GitHub Actions)
- **Deliverable**: Complete test suite, automated CI

**Total estimated effort:** 5 weeks

### Dependencies Between Phases

- **Phase 2** depends on **Phase 1** (fixtures required)
- **Phase 3** depends on **Phase 2** (client mocks required)
- **Phase 4** can run parallel to **Phase 3** (independent)
- **Phase 5** depends on **Phases 2, 3, 4** (requires full unit test suite)

### Risk Factors

**High complexity areas:**
1. **Protocol layer mocking**: WebSocket async context managers, message timing
2. **Event coordination**: asyncio.Event signaling, race conditions in tests
3. **Home Assistant fixtures**: pytest-homeassistant-custom-component may have breaking changes

**Mitigation:**
- Start with simpler layers (AgentRun, emoji stripping) to build confidence
- Use real AgentRun and GatewayProtocol in integration tests (less mocking)
- Pin pytest-homeassistant-custom-component version in requirements

## Sources

**Confidence Level: HIGH**

This architecture is based on:
1. **Home Assistant official testing patterns** (pytest + pytest-asyncio standard)
2. **Existing codebase analysis** (`.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/TESTING.md`)
3. **pytest best practices** (fixture scoping, parametrization, async patterns)
4. **WebSocket testing patterns** (mock servers, async mocking)

**Source hierarchy:**
- Codebase structure analysis (direct examination)
- Home Assistant conventions (standard for custom integrations)
- pytest-asyncio patterns (documented library usage)
- General pytest patterns (well-established practices)

**Verification notes:**
- No WebSearch or WebFetch used (permission denied)
- Based entirely on codebase examination and established patterns
- Recommendations are conservative and proven
