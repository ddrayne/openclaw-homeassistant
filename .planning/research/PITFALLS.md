# Async Testing Pitfalls

**Domain:** Async WebSocket-based Home Assistant Integration
**Researched:** 2026-01-25
**Confidence:** MEDIUM (based on codebase analysis + training knowledge, web sources unavailable)

## Critical Pitfalls

Mistakes that cause flaky tests, false positives, or test suite failures.

### Pitfall 1: Event Loop Fixture Scope Mismatch

**What goes wrong:** Test creates async fixtures at function scope while pytest-asyncio uses module/session scope event loop. Results in "Event loop is closed" errors or tasks attached to wrong loop.

**Why it happens:**
- pytest-asyncio defaults to function-scoped event loops
- Home Assistant test framework uses custom event loop management
- Creating background tasks in fixtures that outlive their event loop

**Consequences:**
- Tests fail with "Event loop is closed" RuntimeError
- Background tasks (like `_connection_loop`) never stop between tests
- Cleanup handlers fail silently
- Flaky tests that pass/fail based on execution order

**Prevention:**
```python
# Use Home Assistant's event loop fixture
@pytest.fixture
async def gateway_client(hass):
    """Create gateway client using HA's event loop."""
    client = ClawdGatewayClient(...)
    await client.connect()
    yield client
    # CRITICAL: Cleanup must happen before event loop closes
    await client.disconnect()

# NOT this:
@pytest.fixture(scope="module")  # Wrong scope
async def gateway_client():
    client = ClawdGatewayClient(...)
    await client.connect()
    yield client
    # Cleanup happens after event loop closed - FAILS
```

**Detection:**
- Error messages mentioning "Event loop is closed"
- Tests fail only when run together (pytest -x passes, full suite fails)
- Warnings about unclosed resources
- Coroutines that never complete

**Phase mapping:** Phase 1 (Test Infrastructure Setup)

---

### Pitfall 2: Not Awaiting Background Tasks Before Assertions

**What goes wrong:** Test sends WebSocket message and immediately asserts result, before async event handlers complete.

**Why it happens:**
```python
# In gateway.py line 74:
self._connect_task = asyncio.create_task(self._connection_loop())

# In gateway_client.py line 89:
self._gateway.on_event("agent", self._handle_agent_event)
```

Background tasks and event handlers execute independently. Test assertions run before they complete.

**Consequences:**
- Assertions fail because state hasn't updated yet
- Adding `await asyncio.sleep(0.1)` as "fix" (creates race conditions)
- Tests pass locally (fast machine) but fail in CI (slower)
- False negatives (missing bugs because test races past them)

**Prevention:**
```python
# BAD: Race condition
await gateway.send_request("agent", {...})
assert len(client._agent_runs) == 1  # FLAKY: May not be set yet

# GOOD: Wait for expected state
await gateway.send_request("agent", {...})
await asyncio.wait_for(
    wait_for_condition(lambda: len(client._agent_runs) == 1),
    timeout=1.0
)
assert len(client._agent_runs) == 1

# BETTER: Use event synchronization
run_started = asyncio.Event()
original_handler = client._handle_agent_event
def wrapped_handler(event):
    original_handler(event)
    if event.get("payload", {}).get("runId"):
        run_started.set()
client._handle_agent_event = wrapped_handler

await gateway.send_request("agent", {...})
await asyncio.wait_for(run_started.wait(), timeout=1.0)
assert len(client._agent_runs) == 1
```

**Detection:**
- Tests with `await asyncio.sleep(0.x)` (code smell)
- Intermittent failures with timing-related assertion errors
- Tests that fail in CI but pass locally
- Using `time.sleep()` in async tests (extremely bad)

**Phase mapping:** Phase 2 (Basic Tests), Phase 3 (WebSocket Tests)

---

### Pitfall 3: WebSocket Mock Not Matching Real Behavior

**What goes wrong:** Test mocks WebSocket as simple request/response, missing real async message patterns, reconnection, and event interleaving.

**Why it happens:**
Real WebSocket behavior (from gateway.py):
- Line 115: Auto-reconnection loop (`async for websocket in websockets.connect()`)
- Line 228-240: Events can arrive during handshake
- Line 302-313: Connection closes can happen mid-operation
- Line 334-337: Responses can arrive after timeout cleanup

Mock doesn't simulate these patterns.

**Consequences:**
- Tests pass but code fails in production
- Reconnection logic never tested
- Race conditions around connection state never exercised
- Event handlers during handshake not tested

**Prevention:**
```python
# BAD: Oversimplified mock
class MockWebSocket:
    async def send(self, data):
        pass

    async def recv(self):
        return '{"type": "res", "ok": true}'

# GOOD: Realistic mock with async behavior
class MockWebSocket:
    def __init__(self):
        self._send_queue = asyncio.Queue()
        self._recv_queue = asyncio.Queue()
        self._connected = True

    async def send(self, data):
        if not self._connected:
            raise ConnectionClosedError(None, None)
        await self._send_queue.put(data)

    async def recv(self):
        # Simulate events arriving during handshake
        if random.random() < 0.2:
            return '{"type": "event", "event": "status"}'
        return await self._recv_queue.get()

    async def close(self):
        self._connected = False

# BETTER: Use pytest-websocket or similar library
# that handles async message patterns correctly
```

**Detection:**
- Tests don't cover reconnection scenarios
- No tests for events during handshake
- Mock always returns success (no error paths tested)
- Tests use synchronous WebSocket mock for async code

**Phase mapping:** Phase 3 (WebSocket Tests), Phase 5 (Reconnection Tests)

---

### Pitfall 4: Not Cleaning Up Background Tasks

**What goes wrong:** Test finishes but `_connection_loop` and `_receive_task` keep running, causing:
- Next test gets events from previous test
- Resource leaks (open sockets, tasks)
- "Task was destroyed but it is pending" warnings

**Why it happens:**
Looking at gateway.py disconnect logic (lines 76-109):
```python
async def disconnect(self) -> None:
    if self._receive_task:
        self._receive_task.cancel()
        try:
            await self._receive_task
        except asyncio.CancelledError:
            pass
```

If test doesn't call `disconnect()`, tasks never cancelled.

**Consequences:**
- Test isolation broken (test N affects test N+1)
- Memory leaks in test suite
- pytest warnings about unclosed resources
- CI fails with resource exhaustion

**Prevention:**
```python
# BAD: No cleanup
@pytest.fixture
async def gateway():
    g = GatewayProtocol(...)
    await g.connect()
    yield g
    # Missing disconnect - tasks keep running!

# GOOD: Always cleanup
@pytest.fixture
async def gateway():
    g = GatewayProtocol(...)
    await g.connect()
    yield g
    await g.disconnect()

# BETTER: Cleanup even on test failure
@pytest.fixture
async def gateway():
    g = GatewayProtocol(...)
    try:
        await g.connect()
        yield g
    finally:
        await g.disconnect()

# BEST: Use Home Assistant's async_test pattern
async def test_something(hass):
    gateway = GatewayProtocol(...)
    # hass fixture ensures cleanup on teardown
    hass.data["test_gateway"] = gateway
    await gateway.connect()
    # ... test code ...
    # No explicit cleanup needed - hass handles it
```

**Detection:**
- pytest warnings: "coroutine was never awaited"
- "Task was destroyed but it is pending"
- Tests leak resources (check with `pytest --log-cli-level=DEBUG`)
- Using `ps aux | grep pytest` shows growing memory

**Phase mapping:** Phase 1 (Test Infrastructure Setup)

---

### Pitfall 5: Testing Timeout Paths with Actual Timeouts

**What goes wrong:** Test wants to verify timeout handling, so sets timeout=30 and waits 31 seconds. Test suite takes forever.

**Why it happens:**
Code has multiple timeout paths:
- gateway_client.py line 79: `timeout: int = 30`
- gateway_client.py line 164: `await asyncio.wait_for(agent_run.complete_event.wait(), timeout=self._timeout)`
- gateway.py line 98: `await asyncio.wait_for(self._gateway._connected_event.wait(), timeout=5.0)`

Testing these naively makes tests slow.

**Consequences:**
- Test suite takes minutes instead of seconds
- Developers skip running tests locally
- CI times out
- Coverage drops because timeout tests are too slow to write

**Prevention:**
```python
# BAD: Actually wait for timeout
async def test_timeout():
    client = ClawdGatewayClient(..., timeout=30)
    with pytest.raises(GatewayTimeoutError):
        await client.send_agent_request("test")  # Waits 30 seconds!

# GOOD: Mock time advancement
async def test_timeout():
    client = ClawdGatewayClient(..., timeout=0.1)  # Short timeout for tests
    with pytest.raises(GatewayTimeoutError):
        await client.send_agent_request("test")  # Fails in 0.1s

# BETTER: Use freezegun or pytest-timeout
@pytest.mark.timeout(1)  # Fail if test takes >1s
async def test_timeout(freezer):
    client = ClawdGatewayClient(..., timeout=30)
    task = asyncio.create_task(client.send_agent_request("test"))
    freezer.tick(31)  # Advance time without waiting
    with pytest.raises(GatewayTimeoutError):
        await task
```

**Detection:**
- Test suite takes >10 seconds to run
- Tests have long `await asyncio.sleep()` calls
- Timeout values in tests match production values (30s)
- Using `time.sleep()` anywhere in async tests

**Phase mapping:** Phase 4 (Error Handling Tests), Phase 6 (Timeout Tests)

---

### Pitfall 6: Mocking asyncio.Event Incorrectly

**What goes wrong:** Test mocks `asyncio.Event` as synchronous boolean, breaking event-driven synchronization.

**Why it happens:**
Code uses Events for synchronization:
- gateway.py line 50: `self._connected_event = asyncio.Event()`
- gateway_client.py line 26: `self.complete_event = asyncio.Event()`

Tests mock them naively:
```python
# BAD
mock_event = MagicMock()
mock_event.is_set.return_value = True
```

**Consequences:**
- `await event.wait()` fails (MagicMock isn't awaitable)
- Event synchronization doesn't work
- Tests crash with "object MagicMock can't be used in await"

**Prevention:**
```python
# BAD: Mock Event as bool
mock_event = MagicMock(is_set=True)
# Fails: await mock_event.wait()

# GOOD: Use real asyncio.Event
real_event = asyncio.Event()
real_event.set()
# Works: await real_event.wait()

# BETTER: Don't mock primitives
# Real asyncio.Event is lightweight and fast
# Only mock external dependencies (WebSocket, HA APIs)
```

**Detection:**
- Errors: "object MagicMock can't be used in await expression"
- Tests using `unittest.mock.MagicMock` for asyncio primitives
- Trying to `.return_value` an async method

**Phase mapping:** Phase 2 (Basic Tests)

---

## Moderate Pitfalls

Mistakes that cause technical debt or harder-to-debug issues.

### Pitfall 7: Not Testing Event Handler Execution Order

**What goes wrong:** Test assumes events processed in send order, but async dispatch can reorder them.

**Why it happens:**
gateway.py line 350-370 shows event handlers are async:
```python
async def _dispatch_event(self, event_name: str, event: dict[str, Any]) -> None:
    for handler in handlers:
        if asyncio.iscoroutinefunction(handler):
            await handler(event)  # Sequential but handler timing varies
```

If handler A takes 100ms and handler B takes 10ms, events can appear out of order to observers.

**Consequences:**
- Assertions on event order are flaky
- State machines break in production
- Race conditions in multi-event scenarios

**Prevention:**
```python
# BAD: Assume order
events = []
gateway.on_event("agent", lambda e: events.append(e))
await send_two_messages()
assert events[0]["runId"] == "first"  # FLAKY

# GOOD: Wait for specific events, not order
await send_two_messages()
await wait_for_condition(
    lambda: any(e["runId"] == "first" for e in events)
)
assert any(e["runId"] == "second" for e in events)
```

**Phase mapping:** Phase 3 (WebSocket Tests), Phase 7 (Integration Tests)

---

### Pitfall 8: Testing with Single Message Pattern Only

**What goes wrong:** Tests send one message, get one response, check result. Misses cumulative text updates.

**Why it happens:**
gateway_client.py lines 28-55 handle cumulative text:
```python
def add_output(self, output: str) -> None:
    # Gateway sends full text each time, only append what's new
    if output.startswith(self._full_text):
        new_text = output[len(self._full_text):]
```

Tests that only check final result miss edge cases in cumulative updates.

**Consequences:**
- Bug in line 36-40 (cumulative text extraction) never caught
- Duplicate text issues not detected (see commit message "Fix duplicate speech")
- Edge cases like empty updates, non-cumulative updates not tested

**Prevention:**
```python
# BAD: Only test final result
response = await client.send_agent_request("test")
assert response == "final text"

# GOOD: Test incremental updates
run = client._agent_runs["test-run-id"]
client._handle_agent_event({
    "payload": {"runId": "test-run-id", "output": "Hello"}
})
assert run._full_text == "Hello"

client._handle_agent_event({
    "payload": {"runId": "test-run-id", "output": "Hello world"}
})
assert run._full_text == "Hello world"  # Not "HelloHello world"

# Edge case: Non-cumulative update
client._handle_agent_event({
    "payload": {"runId": "test-run-id", "output": "Different"}
})
assert run._full_text == "Different"  # Replaced
```

**Phase mapping:** Phase 4 (Error Handling Tests), Phase 7 (Integration Tests)

---

### Pitfall 9: Not Testing Reconnection State Transitions

**What goes wrong:** Test covers "connected" and "disconnected" but not the transitions between them.

**Why it happens:**
gateway.py has complex reconnection logic:
- Line 110-189: Connection loop with retries
- Line 142-163: Different handling for different close codes
- Line 146: Code 1012 = restart, auto-reconnect

Tests often only check steady states.

**Consequences:**
- State corruption during reconnect not caught
- Pending requests during disconnect lost
- Events received during reconnect cause crashes

**Prevention:**
```python
# BAD: Only test steady states
async def test_connected():
    await gateway.connect()
    assert gateway.connected

async def test_disconnected():
    await gateway.disconnect()
    assert not gateway.connected

# GOOD: Test transitions
async def test_disconnect_during_request():
    await gateway.connect()
    request_task = asyncio.create_task(
        gateway.send_request("agent", {...})
    )
    await asyncio.sleep(0.01)  # Let request start
    await gateway.disconnect()

    with pytest.raises(GatewayConnectionError):
        await request_task

async def test_reconnect_preserves_event_handlers():
    gateway.on_event("agent", handler)
    await gateway.connect()
    # Simulate disconnect
    await gateway._websocket.close()
    await asyncio.sleep(0.1)  # Let reconnect happen

    # Handler should still work after reconnect
    await send_event()
    assert handler_called
```

**Phase mapping:** Phase 5 (Reconnection Tests)

---

### Pitfall 10: Home Assistant Test Harness Misuse

**What goes wrong:** Test creates real HA config entries and entities, causing slow tests and interdependencies.

**Why it happens:**
- __init__.py line 24-60: Full setup flow with real config entries
- conversation.py line 41-49: Entity creation and registration
- Not using HA's test helpers properly

**Consequences:**
- Tests take seconds instead of milliseconds
- Tests depend on HA internals (brittle)
- Hard to test error paths (setup must succeed)

**Prevention:**
```python
# BAD: Full integration setup for unit test
async def test_message_handling(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={...})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    # Slow, complex, brittle

# GOOD: Test component directly
async def test_message_handling():
    mock_gateway = MockGatewayClient()
    entity = ClawdConversationEntity(mock_config, mock_gateway)
    result = await entity._async_handle_message(...)
    assert result.response.speech["plain"]["speech"] == "expected"

# Use integration tests ONLY for:
# - Entry setup/teardown
# - Platform registration
# - HA-specific features (reload, etc)
```

**Phase mapping:** Phase 1 (Test Infrastructure Setup), Phase 7 (Integration Tests)

---

## Minor Pitfalls

Mistakes that cause annoyance but are fixable.

### Pitfall 11: Over-Reliant on pytest-asyncio Markers

**What goes wrong:** Test uses `@pytest.mark.asyncio` but Home Assistant provides its own async test infrastructure.

**Why it happens:**
- pytest-asyncio is standard for async tests
- But HA has custom test framework in `homeassistant.helpers.testing`
- Mixing the two causes confusion

**Consequences:**
- Event loop mismatch warnings
- Fixtures don't work as expected
- Tests harder to integrate with HA test suite

**Prevention:**
```python
# BAD: Using pytest-asyncio directly
@pytest.mark.asyncio
async def test_something():
    # Uses pytest-asyncio event loop

# GOOD: Use HA's test decorators
from homeassistant.helpers.testing import async_test

@async_test
async def test_something(hass):
    # Uses HA's event loop and fixtures
```

**Phase mapping:** Phase 1 (Test Infrastructure Setup)

---

### Pitfall 12: Testing Logging Instead of Behavior

**What goes wrong:** Test asserts log messages instead of state changes or return values.

**Why it happens:**
Code has extensive logging:
- gateway_client.py line 134: `_LOGGER.debug("Sending agent request...")`
- gateway.py line 224: `_LOGGER.debug("Sending connect request")`

Tempting to test these instead of actual behavior.

**Consequences:**
- Tests break when log messages change
- Actual bugs not caught (behavior wrong but logs right)
- Tests don't document API contracts

**Prevention:**
```python
# BAD: Testing logs
async def test_connect(caplog):
    await gateway.connect()
    assert "Connecting to Gateway" in caplog.text

# GOOD: Test behavior
async def test_connect():
    await gateway.connect()
    assert gateway.connected
    assert await gateway.send_request("health") is not None

# Logging tests OK for:
# - Error conditions (verify error logged)
# - Debugging features (verify debug info present)
# But never as primary assertion
```

**Phase mapping:** Phase 2 (Basic Tests)

---

### Pitfall 13: Not Testing Both Sync and Async Event Handlers

**What goes wrong:** Test only uses async handler, misses bug in sync handler path.

**Why it happens:**
gateway.py line 360-363 supports both:
```python
if asyncio.iscoroutinefunction(handler):
    await handler(event)
else:
    handler(event)
```

**Consequences:**
- Sync handler path never tested
- Exception handling differs between paths (line 364-369)

**Prevention:**
```python
# Test both paths
async def test_async_event_handler():
    called = asyncio.Event()

    async def async_handler(event):
        called.set()

    gateway.on_event("test", async_handler)
    await trigger_event()
    await asyncio.wait_for(called.wait(), timeout=1.0)

async def test_sync_event_handler():
    results = []

    def sync_handler(event):
        results.append(event)

    gateway.on_event("test", sync_handler)
    await trigger_event()
    assert len(results) == 1
```

**Phase mapping:** Phase 3 (WebSocket Tests)

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|----------------|------------|
| Test Infrastructure Setup | Event loop scope mismatch (Pitfall 1) | Use HA's event loop fixtures, establish cleanup pattern early |
| Basic Unit Tests | Mocking asyncio.Event (Pitfall 6) | Don't mock asyncio primitives; use real ones |
| WebSocket Tests | Mock doesn't match reality (Pitfall 3) | Create realistic WebSocket test double that simulates reconnects, events during handshake |
| Error Handling | Slow timeout tests (Pitfall 5) | Use short timeouts in tests, document pattern in test utils |
| Reconnection Tests | Missing state transitions (Pitfall 9) | Test matrix: connected->disconnected, disconnected->connected, reconnecting->connected |
| Timeout Tests | Actually waiting for timeouts (Pitfall 5) | Use freezegun or short test timeouts |
| Integration Tests | Full HA setup for unit-level tests (Pitfall 10) | Reserve HA test harness for true integration tests only |

---

## Testing Anti-Patterns Specific to This Codebase

### Anti-Pattern 1: Not Testing `_pending_requests` Cleanup

**Risk:** High - Memory leak if requests timeout but futures aren't cleaned

**Location:** gateway.py line 432: `self._pending_requests.pop(request_id, None)`

**Test coverage needed:**
- Request times out → future removed from dict
- Response arrives after timeout → doesn't crash
- Disconnect while pending → all futures failed

---

### Anti-Pattern 2: Not Testing Duplicate Handler Registration

**Risk:** Medium - Event handler registered multiple times fires multiple times

**Location:** gateway.py line 377-388: Duplicate handler prevention

**Test coverage needed:**
- Register same handler twice → only fires once
- Different handlers for same event → both fire
- Handler registered after event fired → doesn't fire for past events

---

### Anti-Pattern 3: Not Testing Unknown Run ID Events

**Risk:** Low - Log spam but no functional issue

**Location:** gateway_client.py line 218-222: Unknown run event handling

**Test coverage needed:**
- Event for unknown runId → logged, doesn't crash
- Event arrives after run cleanup → handled gracefully

---

## Confidence Assessment

| Area | Confidence | Source |
|------|------------|--------|
| Async event loop issues | HIGH | Codebase analysis + training knowledge |
| WebSocket mock patterns | HIGH | Codebase analysis + training knowledge |
| Home Assistant specifics | MEDIUM | Codebase analysis only (official docs unavailable) |
| pytest-asyncio pitfalls | HIGH | Training knowledge + observed patterns |
| Race conditions | HIGH | Codebase analysis shows multiple concurrent task patterns |
| Timeout testing | HIGH | Training knowledge + observed timeout usage |

## Sources

**Codebase Analysis:**
- `custom_components/clawd/gateway.py` - WebSocket protocol, reconnection, event handling
- `custom_components/clawd/gateway_client.py` - Request/response, event buffering, timeout handling
- `custom_components/clawd/conversation.py` - HA integration patterns
- `custom_components/clawd/__init__.py` - Setup/teardown patterns

**Training Knowledge:**
- pytest-asyncio event loop scoping
- asyncio task management and cleanup
- WebSocket testing patterns
- Race condition detection in async code
- Home Assistant testing framework patterns

**Limitations:**
- Could not access official pytest-asyncio documentation (web access denied)
- Could not access Home Assistant testing documentation (web access denied)
- Recommendations based on training knowledge + codebase analysis only
- Some HA-specific patterns inferred from code rather than docs

## Recommended Reading

For the team implementing tests:
1. pytest-asyncio documentation on fixture scoping
2. Home Assistant testing guidelines at developers.home-assistant.io
3. This codebase's cleanup patterns (gateway.py disconnect method is exemplary)
4. asyncio task lifecycle management (official Python docs)
5. WebSocket testing strategies for async Python

## Next Steps

Before starting test implementation:
1. Establish event loop fixture pattern (resolve Pitfall 1 first)
2. Create WebSocket test double (resolve Pitfall 3 early)
3. Document timeout testing strategy (resolve Pitfall 5)
4. Set up cleanup helpers (resolve Pitfall 4)
5. Then proceed with test implementation

These four patterns are foundational - getting them wrong compounds through entire test suite.
