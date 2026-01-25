# Test Feature Landscape: Home Assistant Custom Integration

**Domain:** Home Assistant Custom Integration (WebSocket-based conversation agent)
**Researched:** 2026-01-25
**Confidence:** HIGH (based on Home Assistant testing patterns and integration architecture analysis)

## Executive Summary

Home Assistant custom integrations require comprehensive test coverage across five critical dimensions: config flow validation, entity behavior, protocol handling, error recovery, and Home Assistant lifecycle integration. For this WebSocket-based conversation integration, the highest-risk areas are connection handling, event buffering, and async coordination—all requiring careful testing to prevent production failures.

**Critical insight:** Home Assistant's testing philosophy emphasizes testing the integration contract (setup, config flow, entity APIs) separate from business logic. Tests must validate both happy paths and failure modes, as HA installations run 24/7 with unpredictable network conditions.

## Table Stakes

Features users expect in any mature Home Assistant integration test suite. Missing = tests are incomplete.

| Test Type | Why Expected | Complexity | Notes |
|-----------|--------------|------------|-------|
| **Config Flow Tests** | HA requires validated config flows | Medium | Test user step, validation, errors, unique_id handling |
| **Setup/Unload Tests** | Lifecycle contract with HA | Low | Must verify clean setup and teardown |
| **Entity Tests** | Core integration value | Medium | Test entity creation, availability, attributes |
| **Connection Handling** | WebSocket reliability critical | High | Connect, disconnect, reconnect scenarios |
| **Error Path Coverage** | Production failures happen | Medium | All exception types, timeout scenarios |
| **Async Coordination** | Python asyncio correctness | High | Event loops, futures, cancellation |
| **Message Parsing** | Protocol correctness | Low | Valid/invalid message formats |
| **Authentication Tests** | Security requirement | Low | Valid token, invalid token, missing token |
| **Fixture Setup** | Test maintainability | Low | Mock HA instance, config entries, entities |

### Detail: Config Flow Tests (REQUIRED)

Home Assistant config flows are the user-facing setup experience. Every error path must be tested.

**Test scenarios:**
- User step: Form display with defaults
- Valid input: Successful entry creation
- Duplicate prevention: unique_id collision handling
- Connection errors: cannot_connect, timeout, invalid_auth
- Validation errors: Invalid port range, malformed host
- Options flow: Updating existing configuration
- Security warnings: Non-SSL remote connections

**Why critical:** Config flow bugs prevent users from setting up the integration. HA submissions require config flow tests.

**Complexity: Medium** - Requires mocking HA config_entries flow, simulating user input, validating error mapping.

### Detail: Setup/Unload Tests (REQUIRED)

Tests verify the integration properly integrates with HA lifecycle.

**Test scenarios:**
- `async_setup_entry` success: Client created, platforms loaded
- `async_setup_entry` failure: Connection fails, setup aborted
- `async_unload_entry`: Platforms unloaded, client disconnected, data cleaned
- `async_reload_entry`: Unload then setup sequence
- Entry data storage: Gateway client stored in hass.data correctly

**Why critical:** Improper teardown causes resource leaks. Failed setup must not leave partial state.

**Complexity: Low** - Standard HA test patterns, well-documented fixtures available.

### Detail: Entity Tests (REQUIRED)

Conversation entity is the user-facing feature. Must validate all entity behaviors.

**Test scenarios:**
- Entity creation: ConversationEntity instantiated with correct attributes
- Entity availability: Reports unavailable when gateway disconnected
- Message handling: User input -> gateway request -> response formatting
- Error responses: Network errors produce user-friendly error messages
- TTS emoji stripping: Emoji pattern removal when configured
- Chat log integration: Assistant responses added to conversation history

**Why critical:** Entity bugs directly impact user experience. All error paths must degrade gracefully.

**Complexity: Medium** - Requires mocking conversation.ConversationInput, intent.IntentResponse, gateway client.

### Detail: Connection Handling (REQUIRED)

WebSocket connections are inherently unreliable. All connection states must be tested.

**Test scenarios:**
- Initial connection: Successful WebSocket handshake
- Connection timeout: Handshake times out after 10s
- Authentication success: Valid token accepted
- Authentication failure: Invalid token rejected with GatewayAuthenticationError
- Disconnection handling: Clean disconnect, resources released
- Automatic reconnection: Connection dropped, auto-reconnect after delay
- Reconnect on restart: Gateway restart (code 1012) triggers reconnect
- Fatal errors: Auth/protocol errors don't retry infinitely
- Connection state tracking: `connected` property reflects actual state

**Why critical:** Connection bugs cause cryptic errors and connection leaks. 24/7 operations require robust reconnection.

**Complexity: High** - Async WebSocket mocking, timing-dependent behavior, state machine testing.

### Detail: Error Path Coverage (REQUIRED)

Production systems encounter all possible errors. Tests must validate error handling.

**Test scenarios:**
- `GatewayConnectionError`: Connection refused, network unreachable
- `GatewayAuthenticationError`: Invalid token, missing token
- `GatewayTimeoutError`: Request timeout, slow response
- `AgentExecutionError`: Agent failure, malformed response
- `ProtocolError`: Version mismatch, invalid message format
- WebSocket close codes: Normal close, abnormal close, restart (1012)
- JSON decode errors: Malformed JSON in messages
- Timeout handling: `asyncio.wait_for` timeout paths

**Why critical:** Uncaught exceptions crash the integration. Error messages must be specific and actionable.

**Complexity: Medium** - Requires mocking various failure modes, validating exception types and messages.

### Detail: Async Coordination (REQUIRED)

Python asyncio is complex. All async patterns must be tested for correctness.

**Test scenarios:**
- Future resolution: Request/response correlation via futures
- Event signaling: `asyncio.Event` coordination between coroutines
- Task cancellation: Clean cancellation of connection/receive tasks
- Timeout handling: `asyncio.wait_for` with various timeout values
- Event loop handling: No blocking operations on event loop
- Concurrent requests: Multiple simultaneous agent requests
- Event buffering: AgentRun cumulative text buffering correctness

**Why critical:** Async bugs cause deadlocks, race conditions, resource leaks. Very hard to debug in production.

**Complexity: High** - Requires understanding asyncio internals, careful timing control in tests.

## Differentiators

Features that set comprehensive test suites apart. Not expected, but highly valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Integration Tests** | End-to-end flow validation | High | Mock Gateway server, full request/response cycle |
| **Property-Based Tests** | Edge case discovery | High | Hypothesis/QuickCheck for message parsing, validation |
| **Reconnection Scenarios** | Realistic failure simulation | High | Network blips, partial writes, slow responses |
| **Performance Tests** | Latency/throughput validation | Medium | Measure request handling time, concurrent load |
| **Logging Verification** | Debug observability | Low | Verify debug/warning/error logs at correct levels |
| **Type Checking Tests** | Static analysis integration | Low | mypy/pyright validation in CI |
| **Memory Leak Tests** | Long-running stability | High | Monitor object creation over many connections |
| **Race Condition Tests** | Concurrent behavior validation | High | Stress tests with rapid connect/disconnect |

### Detail: Integration Tests

Full end-to-end tests with mock Gateway server responding to real WebSocket protocol.

**Value:** Validates complete request/response flow, protocol compliance, event handling.

**Complexity: High** - Requires mock WebSocket server implementation, protocol message generation, timing coordination.

**When to implement:** After unit tests provide safety net. High value for catching integration bugs.

### Detail: Property-Based Tests

Generative testing that creates random inputs to discover edge cases.

**Value:** Finds corner cases that manual test design misses. Especially valuable for parsing, validation logic.

**Complexity: High** - Requires hypothesis library, property invariants definition, shrinking configuration.

**When to implement:** For parsing logic (message formats) and validation (config input ranges).

### Detail: Reconnection Scenarios

Realistic network failure simulation: partial writes, connection drops mid-request, slow responses.

**Value:** Validates production resilience. Real networks have these issues constantly.

**Complexity: High** - Requires WebSocket mock with timing control, partial message simulation.

**When to implement:** After basic connection tests pass. Critical for 24/7 reliability.

## Anti-Features

Features to explicitly NOT test. Common mistakes in integration testing.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Testing websockets library** | External dependency, already tested | Mock WebSocket interface, test your usage patterns |
| **Testing Home Assistant core** | HA has own tests | Test integration contract only (setup, config_flow, entity APIs) |
| **Testing Gateway server behavior** | Outside integration scope | Mock expected Gateway responses, document assumptions |
| **100% line coverage obsession** | Diminishing returns | Focus on critical paths, error handling, edge cases |
| **Testing private methods directly** | Implementation detail coupling | Test public API behavior, private methods tested implicitly |
| **Synchronous sleep for timing** | Flaky tests, slow CI | Use async mocks, control time explicitly |
| **Real network connections in unit tests** | Slow, unreliable, external dependency | Mock WebSocket, use fixtures |
| **Testing every log message** | Brittle to logging changes | Test error conditions that cause logs, not log text |

### Detail: Testing websockets Library

**Mistake:** Testing that `websockets.connect()` creates connections correctly.

**Why avoid:** The `websockets` library has its own comprehensive test suite. Your tests should assume it works and test how you use it.

**Correct approach:** Mock `websockets.connect()` to return a mock WebSocket. Test that your code sends correct messages, handles responses, reacts to connection errors.

### Detail: Testing Home Assistant Core

**Mistake:** Testing that `hass.config_entries.async_forward_entry_setups()` loads platforms.

**Why avoid:** HA's platform loading is tested by HA core. You don't need to verify HA works.

**Correct approach:** Test that your `async_setup_entry` calls the correct HA APIs with correct parameters. Mock the HA APIs to return expected values.

### Detail: 100% Line Coverage Obsession

**Mistake:** Adding tests just to hit coverage percentage targets without thinking about value.

**Why avoid:** High coverage doesn't guarantee quality. Error handling and edge cases matter more than hitting every line.

**Correct approach:** Prioritize testing:
1. Error paths (most likely to have bugs)
2. Async coordination (hardest to debug)
3. Protocol handling (external contract)
4. User-facing behavior (entity, config flow)

Coverage is a side effect of good testing, not the goal.

### Detail: Testing Private Methods Directly

**Mistake:** Writing tests like `test_gateway_handle_message_parsing()` that call `_handle_message()` directly.

**Why avoid:** Private methods are implementation details. If you refactor and rename/remove them, tests break unnecessarily.

**Correct approach:** Test public API (`send_request()`, `connect()`, `disconnect()`). The private methods get tested implicitly through public API usage. Only test private methods if they contain complex logic isolated from public API.

## Test Dependencies

```
pytest                       # Test runner (HA standard)
    └── pytest-asyncio       # Async test support (required for HA)
    └── pytest-homeassistant-custom-component  # HA test utilities (fixtures, mocking)
    └── pytest-cov           # Coverage reporting (optional but standard)

unittest.mock                # Python stdlib mocking (asyncio.Future, websockets)
pytest-aiohttp               # Async HTTP test support (if using aiohttp)

Type checking (optional but valuable):
    └── mypy                 # Static type checking
    └── pytest-mypy-plugins  # Test type annotations
```

**Critical dependency:** `pytest-homeassistant-custom-component` provides fixtures for `hass`, `config_entry`, standard entity testing utilities. This makes HA integration testing dramatically easier.

**Async testing:** `pytest-asyncio` is required. All HA integration code is async.

## MVP Test Recommendation

For MVP test coverage, prioritize in this order:

### Phase 1: Foundation (MUST HAVE)
1. **Config flow tests** - User setup experience must work
   - Test `async_step_user` with valid input
   - Test all error paths (cannot_connect, timeout, invalid_auth)
   - Test duplicate entry prevention
2. **Setup/unload tests** - Lifecycle contract
   - Test successful setup
   - Test connection failure during setup
   - Test clean unload
3. **Connection tests** - WebSocket reliability
   - Test successful connection and handshake
   - Test authentication failure
   - Test connection timeout

### Phase 2: Core Behavior (SHOULD HAVE)
4. **Entity tests** - User-facing functionality
   - Test message handling happy path
   - Test error response generation
   - Test emoji stripping
5. **Message parsing tests** - Protocol correctness
   - Test response message parsing
   - Test event message parsing
   - Test malformed JSON handling
6. **Error handling tests** - Production resilience
   - Test all exception types
   - Test timeout scenarios

### Phase 3: Robustness (NICE TO HAVE)
7. **Reconnection tests** - Long-running stability
   - Test automatic reconnection after disconnect
   - Test reconnection backoff (if implemented)
8. **Concurrent request tests** - Multi-user scenarios
   - Test multiple simultaneous agent requests
9. **Integration tests** - End-to-end validation
   - Mock Gateway server, full request/response flow

Defer to post-MVP:
- **Property-based tests**: High value but high effort, add after core coverage
- **Performance tests**: Optimize after correctness established
- **Memory leak tests**: Long-term reliability, not critical for initial release

## Test Organization

Recommended test file structure:

```
tests/
├── conftest.py                      # Shared fixtures (mock hass, gateway, config entries)
├── test_config_flow.py              # Config flow and options flow tests
├── test_init.py                     # Setup, unload, reload tests
├── test_conversation.py             # ConversationEntity tests
├── test_gateway.py                  # GatewayProtocol tests (connection, handshake, messages)
├── test_gateway_client.py           # ClawdGatewayClient tests (agent runs, buffering)
├── fixtures/
│   ├── messages.json                # Sample Gateway messages for parsing tests
│   └── responses.json               # Sample agent responses
└── integration/
    └── test_full_flow.py            # End-to-end integration tests
```

**Rationale:**
- One test file per module (follows codebase structure)
- Shared fixtures in `conftest.py` (DRY principle)
- Integration tests separated (different scope, slower)
- Test data in fixtures directory (maintainable, reusable)

## Coverage Targets

Realistic coverage targets by module:

| Module | Target | Rationale |
|--------|--------|-----------|
| `config_flow.py` | 95%+ | User-facing, all error paths critical |
| `__init__.py` | 90%+ | Lifecycle contract, setup/unload must work |
| `conversation.py` | 90%+ | User-facing entity, error handling critical |
| `gateway.py` | 85%+ | Complex async, some error paths hard to trigger |
| `gateway_client.py` | 90%+ | Business logic, all buffering paths testable |
| `exceptions.py` | 100% | Trivial, exception definitions |
| `const.py` | N/A | Constants, no logic to test |

**Overall target:** 90% coverage across testable code.

**Why not 100%?** Some error paths in connection handling are difficult to trigger reliably (specific WebSocket close codes, race conditions). Focus on testing common failures and critical paths.

## Sources

**Confidence: HIGH** - Based on:
- Home Assistant integration architecture patterns (analyzed codebase structure)
- Python asyncio testing best practices (pytest-asyncio, unittest.mock patterns)
- WebSocket testing patterns (mocking strategies for async WebSocket libraries)
- Custom integration testing requirements (config flow, setup/unload lifecycle)
- Integration codebase analysis (identified specific test needs from code review)

**Note:** Unable to access external sources (WebSearch/WebFetch disabled). Analysis based on:
1. Direct codebase analysis (all 7 modules reviewed)
2. Existing `.planning/codebase/TESTING.md` analysis
3. Home Assistant integration patterns from training data (January 2025 cutoff)
4. Python asyncio testing patterns (standard pytest ecosystem)

**Validation needed:** Home Assistant developer documentation for current testing requirements (2026). Training data current through January 2025, framework may have evolved.
