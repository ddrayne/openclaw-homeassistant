# Project Research Summary

**Project:** Clawd Home Assistant Integration Test Suite
**Domain:** Async WebSocket-based Home Assistant Custom Integration Testing
**Researched:** 2026-01-25
**Confidence:** HIGH

## Executive Summary

Home Assistant custom integrations require comprehensive test coverage across five critical dimensions: config flow validation, entity behavior, protocol handling, error recovery, and integration lifecycle. For this WebSocket-based conversation agent integration, the highest-risk areas are async coordination, connection state management, and event buffering—areas where production failures are difficult to debug and often manifest as race conditions or resource leaks.

The recommended testing stack centers on pytest with async support (pytest-asyncio), Home Assistant test utilities (pytest-homeassistant-custom-component), and careful WebSocket mocking using unittest.mock.AsyncMock. The `websockets` library (not aiohttp) requires manual async mocks rather than pytest-aiohttp. Coverage should target ~90% with emphasis on error paths and async coordination over line-count metrics. The architecture follows a layered mocking strategy: mock one layer up from what you're testing, use real instances for business logic (AgentRun, emoji stripping), and reserve integration tests for true end-to-end flows.

Critical risks center on async testing pitfalls: event loop scope mismatches causing "Event loop is closed" errors, background task cleanup failures leading to resource leaks, and WebSocket mocks that don't reflect real reconnection behavior. These are foundational issues—getting them wrong early compounds through the entire test suite. Mitigation requires establishing cleanup patterns, realistic WebSocket test doubles, and short timeouts for test speed.

## Key Findings

### Recommended Stack

**Core Testing Framework:**
- **pytest ^8.0**: Industry standard test framework with excellent async support, required by Home Assistant ecosystem
- **pytest-asyncio ^0.23**: Essential for testing async Home Assistant code, handles event loops correctly
- **pytest-cov ^4.1**: Coverage reporting with branch coverage support
- **pytest-timeout ^2.2**: Prevents hanging async tests, essential for WebSocket timeout scenarios

**Home Assistant Testing:**
- **pytest-homeassistant-custom-component ^0.13**: Provides critical fixtures (hass, config entries, entity test utilities) - this is the standard for custom component testing
- **homeassistant latest**: Required to test integration, use same version as minimum supported

**Mocking Strategy:**
- **unittest.mock.AsyncMock**: For WebSocket connections (websockets library uses different patterns than aiohttp)
- **freezegun ^1.4**: Datetime mocking for timeouts and time-based logic (HA ecosystem standard over time-machine)

**WebSocket Testing Approach:** Since this integration uses `websockets>=12.0` (not aiohttp), mock at the GatewayProtocol level using `unittest.mock.AsyncMock` to replace the WebSocket client. pytest-aiohttp is for aiohttp-based WebSockets and won't work here.

**Key Configuration:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
timeout = 30
addopts = ["--cov=custom_components.clawd", "--cov-report=term-missing", "--cov-branch"]
```

### Expected Features

**Must have (table stakes):**
- **Config Flow Tests**: User step validation, connection errors, duplicate prevention, authentication - config flow bugs prevent setup, HA submissions require these tests
- **Setup/Unload Tests**: Integration lifecycle contract - improper teardown causes resource leaks, failed setup must not leave partial state
- **Entity Tests**: Conversation entity behavior, availability tracking, error response formatting - entity bugs directly impact user experience
- **Connection Handling**: WebSocket connect/disconnect/reconnect, timeout, authentication success/failure - connection bugs cause cryptic errors in 24/7 operations
- **Error Path Coverage**: All exception types (GatewayConnectionError, GatewayAuthenticationError, GatewayTimeoutError, AgentExecutionError, ProtocolError) - uncaught exceptions crash the integration
- **Async Coordination**: Future resolution, event signaling, task cancellation, timeout handling - async bugs cause deadlocks and race conditions, very hard to debug in production
- **Message Parsing**: Valid/invalid message formats, JSON decode errors - protocol correctness critical
- **Authentication Tests**: Valid token, invalid token, missing token - security requirement

**Should have (competitive):**
- **Integration Tests**: End-to-end flow validation with mock Gateway server - validates complete request/response flow, protocol compliance
- **Reconnection Scenarios**: Network blips, partial writes, slow responses - validates production resilience for 24/7 reliability
- **Logging Verification**: Debug/warning/error logs at correct levels - improves observability
- **Type Checking Tests**: mypy/pyright validation in CI - catches type errors statically
- **Performance Tests**: Latency/throughput validation - measure request handling time, concurrent load

**Defer (v2+):**
- **Property-Based Tests**: Hypothesis library for edge case discovery in parsing/validation - high value but high effort, add after core coverage
- **Memory Leak Tests**: Long-running stability monitoring - long-term reliability, not critical for initial release
- **Race Condition Stress Tests**: Rapid connect/disconnect scenarios - valuable but requires mature test infrastructure

**Anti-features (explicitly avoid):**
- Testing websockets library internals (already tested by library authors)
- Testing Home Assistant core functionality (HA has its own tests)
- Testing Gateway server behavior (outside integration scope)
- 100% line coverage obsession (diminishing returns, focus on critical paths)
- Testing private methods directly (couples to implementation)
- Real network connections in unit tests (slow, unreliable)

### Architecture Approach

Tests follow a **layered mocking strategy** where you mock one layer up from what you're testing. The test suite mirrors the production code structure with `tests/` paralleling `custom_components/clawd/` using `test_*.py` naming convention. Fixtures are centralized in `conftest.py` with test data separated into `fixtures/` directory.

**Major components:**
1. **Test Infrastructure** (conftest.py, pytest.ini) — Shared fixtures (hass, config_entry, event_loop), mock Gateway protocol/WebSocket, test data fixtures
2. **Unit Tests** (test_*.py files) — Test each module in isolation with mocked dependencies: exceptions, conversation entity, gateway client, gateway protocol, config flow, integration setup
3. **Integration Tests** (test_integration.py) — End-to-end tests with mock Gateway server, validates full WebSocket flow, reconnection logic, concurrent requests
4. **Mock Infrastructure** (fixtures/mock_gateway.py) — Realistic WebSocket test double that simulates Gateway protocol, async message patterns, reconnection scenarios

**Mock vs Real Decision Matrix:**
- websockets.connect(): Mock in unit tests, real in integration tests
- GatewayProtocol: Mock in client tests, real in integration tests
- ClawdGatewayClient: Mock in conversation tests, real in integration tests
- Home Assistant hass: Always mock (too heavyweight)
- AgentRun: Never mock (core logic under test)

**Test organization:**
```
tests/
├── conftest.py              # Shared fixtures
├── test_init.py            # Integration setup/teardown
├── test_config_flow.py     # Config flow tests
├── test_conversation.py    # Conversation entity tests
├── test_gateway.py         # Protocol layer tests
├── test_gateway_client.py  # Client layer tests
├── test_exceptions.py      # Exception hierarchy
└── fixtures/
    ├── gateway_responses.py  # Sample Gateway responses
    └── mock_gateway.py       # Mock WebSocket server
```

### Critical Pitfalls

1. **Event Loop Fixture Scope Mismatch** — Function-scoped fixtures with background tasks outliving their event loop causes "Event loop is closed" errors. Always cleanup async resources (disconnect, cancel tasks) in fixture teardown using try/finally blocks. Use Home Assistant's event loop fixtures.

2. **Not Awaiting Background Tasks Before Assertions** — Test sends WebSocket message and immediately asserts result before async event handlers complete. Use event synchronization (asyncio.Event) or wait_for_condition helpers instead of arbitrary sleep() calls which create race conditions.

3. **WebSocket Mock Not Matching Real Behavior** — Oversimplified mocks that don't simulate auto-reconnection, events during handshake, or connection closes mid-operation. Create realistic WebSocket test double with async message queues, connection state tracking, and error injection capabilities.

4. **Not Cleaning Up Background Tasks** — Test finishes but `_connection_loop` and `_receive_task` keep running, causing next test to receive events from previous test. Always call disconnect() in fixture teardown, use try/finally for cleanup even on test failure.

5. **Testing Timeout Paths with Actual Timeouts** — Test waits 30+ seconds for timeout to trigger. Use short timeouts in tests (0.1s) or freezegun to advance time without waiting. Enforce test timeout limits with pytest-timeout.

6. **Mocking asyncio.Event Incorrectly** — Using MagicMock for asyncio.Event breaks await event.wait(). Use real asyncio.Event instances (they're lightweight), only mock external dependencies.

**Phase-specific warnings:**
- Phase 1 (Infrastructure): Event loop scope mismatch - establish cleanup pattern early
- Phase 2-3 (Basic/WebSocket Tests): Not awaiting background tasks, incorrect asyncio.Event mocking
- Phase 4 (Error Handling): Slow timeout tests - use short timeouts, document pattern
- Phase 5 (Reconnection): Missing state transition tests - test connected→disconnected, reconnecting→connected
- Phase 7 (Integration): Full HA setup for unit tests - reserve HA harness for true integration tests only

## Implications for Roadmap

Based on research, suggested phase structure follows dependency order and complexity:

### Phase 1: Test Infrastructure Foundation
**Rationale:** Enables all subsequent testing, establishes patterns that prevent critical pitfalls (event loop scope, cleanup)
**Delivers:** pytest.ini, conftest.py with core fixtures (hass, config_entry, event_loop), test dependencies installed
**Addresses:** Foundation for all test types
**Avoids:** Pitfall 1 (event loop scope), Pitfall 4 (cleanup), Pitfall 11 (HA test framework integration)
**Duration:** 1-2 days
**Research needed:** None (standard patterns)

### Phase 2: Simple Units & Core Logic
**Rationale:** No async complexity, no mocking - builds confidence, validates infrastructure
**Delivers:** test_exceptions.py (exception hierarchy), test_conversation.py (emoji stripping logic only), test_gateway_client.py (AgentRun buffering)
**Addresses:** Pure logic tests, cumulative text buffering correctness
**Avoids:** Pitfall 8 (cumulative text edge cases), Pitfall 12 (testing behavior not logs)
**Duration:** 2-3 days
**Research needed:** None (testing real instances)

### Phase 3: Mock Gateway Protocol & Client Tests
**Rationale:** Establishes mocking pattern for complex async dependencies, tests client layer in isolation
**Delivers:** mock_gateway_protocol fixture, test_gateway_client.py (send_agent_request, timeout, error handling)
**Addresses:** Client layer with mocked protocol, request correlation, timeout handling
**Avoids:** Pitfall 2 (awaiting background tasks), Pitfall 5 (timeout test speed), Pitfall 6 (asyncio.Event mocking)
**Duration:** 3-4 days
**Research needed:** None (AsyncMock patterns well-documented)

### Phase 4: Conversation Entity & Config Flow
**Rationale:** Builds on client mocks, adds Home Assistant integration testing patterns
**Delivers:** test_conversation.py (full entity), test_config_flow.py (all config flow paths)
**Addresses:** User-facing functionality, config flow validation, error responses
**Avoids:** Pitfall 10 (HA test harness misuse)
**Duration:** 3-4 days
**Research needed:** Minimal (HA config flow testing patterns standard)

### Phase 5: Integration Setup & Teardown
**Rationale:** Tests full integration lifecycle, validates clean setup/unload
**Delivers:** test_init.py (async_setup_entry, async_unload_entry, reload)
**Addresses:** Integration lifecycle contract, resource cleanup
**Avoids:** Pitfall 4 (background task cleanup)
**Duration:** 2 days
**Research needed:** None (standard HA patterns)

### Phase 6: Protocol Layer (Complex WebSocket Mocking)
**Rationale:** Most complex mocking, benefits from established patterns in previous phases
**Delivers:** mock_websocket fixture, test_gateway.py (handshake, authentication, event dispatch, reconnection)
**Addresses:** WebSocket protocol correctness, connection state management
**Avoids:** Pitfall 3 (WebSocket mock realism), Pitfall 9 (state transition testing), Pitfall 13 (sync/async handlers)
**Duration:** 4-5 days
**Research needed:** Moderate (websockets library behavior, realistic async patterns)

### Phase 7: Mock Gateway Server & Integration Tests
**Rationale:** Infrastructure for end-to-end tests, validates complete protocol implementation
**Delivers:** fixtures/mock_gateway.py (WebSocket server), test_integration.py (end-to-end flows)
**Addresses:** Full request/response cycle, reconnection scenarios, concurrent requests
**Avoids:** Pitfall 7 (event handler execution order), Pitfall 9 (reconnection transitions)
**Duration:** 4-5 days
**Research needed:** Moderate (mock WebSocket server implementation, timing control)

### Phase 8: CI Integration & Coverage Optimization
**Rationale:** Automates test execution, measures quality, fills coverage gaps
**Delivers:** GitHub Actions workflow, coverage reports, gap analysis and additional tests
**Addresses:** Automated testing, coverage targets (90% overall, 95%+ core logic)
**Avoids:** Coverage obsession (focus on critical paths)
**Duration:** 2-3 days
**Research needed:** None (standard GitHub Actions patterns)

### Phase Ordering Rationale

**Sequential dependencies:**
- Phase 1 must complete before all others (infrastructure dependency)
- Phase 2 requires Phase 1 (needs fixtures)
- Phase 3 requires Phase 2 (builds on AgentRun tests)
- Phase 4 requires Phase 3 (needs mock_gateway_protocol)
- Phase 5 requires Phase 3 (needs mock_gateway_protocol)
- Phase 6 can run parallel to Phases 4-5 (independent)
- Phase 7 requires Phases 3-6 (needs all mocking patterns)
- Phase 8 requires all previous phases (measures complete suite)

**Complexity progression:** Starts with simple (exceptions), progresses through medium complexity (client with mocks), culminates in high complexity (protocol layer, integration tests). This builds team confidence and establishes patterns before tackling hard problems.

**Risk mitigation:** Critical pitfalls addressed early (Phase 1 establishes cleanup patterns, Phase 3 establishes async mocking patterns) before they can compound through test suite.

**Total estimated effort:** 3-4 weeks for complete test suite with ~68 tests (56 unit, 12 integration)

### Research Flags

**Phases needing deeper research during planning:**
- **Phase 6 (Protocol Layer):** WebSocket library behavior patterns, realistic async message simulation, reconnection state machine testing - moderate complexity
- **Phase 7 (Integration Tests):** Mock WebSocket server implementation, timing control for timeout tests, concurrent request handling - moderate complexity

**Phases with standard patterns (skip research-phase):**
- **Phase 1 (Infrastructure):** pytest configuration, fixture setup - well-documented
- **Phase 2 (Simple Units):** Testing pure Python logic - trivial
- **Phase 3 (Client Mocks):** AsyncMock patterns - well-documented
- **Phase 4 (Conversation/Config):** Home Assistant entity and config flow testing - standard patterns
- **Phase 5 (Integration Setup):** HA lifecycle testing - standard patterns
- **Phase 8 (CI):** GitHub Actions pytest workflow - standard patterns

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | pytest ecosystem standard for HA integrations, versions verified from codebase analysis |
| Features | HIGH | Based on comprehensive codebase analysis, HA integration requirements, async WebSocket patterns |
| Architecture | HIGH | Layered mocking strategy proven for async testing, fixture organization follows pytest best practices |
| Pitfalls | MEDIUM-HIGH | Identified from codebase analysis + async testing experience, unable to verify latest HA testing framework changes |

**Overall confidence:** HIGH

### Gaps to Address

**Version verification:** Unable to verify latest package versions (pytest-homeassistant-custom-component, pytest-asyncio, etc.) without external access. Should verify on PyPI before installing.

**Home Assistant test framework evolution:** Training data current through January 2025, HA testing framework may have evolved in 2026. Review developers.home-assistant.io before Phase 1 to catch any breaking changes in test fixtures.

**websockets library testing patterns:** WebSocket mocking recommendations based on asyncio patterns and training knowledge. Consult websockets documentation for any library-specific testing utilities.

**pytest-asyncio compatibility:** Ensure version compatible with Python 3.13.9 (detected in environment). Check compatibility matrix during Phase 1 setup.

**Handling these gaps:**
- Phase 1: Verify all versions during dependency installation
- Phase 1: Review HA testing docs for any 2026 updates
- Phase 6: Consult websockets docs when implementing protocol tests
- Throughout: Document assumptions and flag for validation during implementation

## Sources

### Primary (HIGH confidence)
- **Codebase analysis** (custom_components/clawd/): Direct examination of gateway.py (WebSocket protocol, reconnection), gateway_client.py (request/response, buffering), conversation.py (entity behavior), __init__.py (integration lifecycle), exceptions.py (error types)
- **Existing planning docs** (.planning/codebase/TESTING.md, ARCHITECTURE.md): Integration structure, testing notes, architectural patterns
- **manifest.json**: Home Assistant version requirements, dependency versions

### Secondary (MEDIUM confidence)
- **Home Assistant testing patterns** (training data): pytest-homeassistant-custom-component usage, config flow testing, entity testing patterns (January 2025 cutoff)
- **pytest-asyncio patterns** (training data): Event loop scoping, fixture patterns, async test best practices
- **Python asyncio testing** (training data): Task management, event synchronization, cleanup patterns

### Tertiary (LOW confidence, needs validation)
- **pytest-homeassistant-custom-component ^0.13**: Version number unverified (unable to check PyPI)
- **pytest-asyncio ^0.23**: Version number unverified (unable to check PyPI)
- **Home Assistant 2026 testing framework**: May have evolved beyond training data (January 2025)

---
*Research completed: 2026-01-25*
*Ready for roadmap: yes*
