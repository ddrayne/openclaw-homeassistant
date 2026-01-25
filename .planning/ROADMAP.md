# Roadmap: Clawd Voice Assistant Test Coverage & Robustness

## Overview

Transform a functional but untested Home Assistant integration into a production-ready component through comprehensive test coverage (~90%) and robustness improvements. The journey establishes test infrastructure, builds unit test coverage for pure logic, layers in integration tests for async coordination and WebSocket protocol handling, then adds retry logic and typed error handling once tests provide a safety net for behavior changes.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 4, 5, 6, 7): Planned milestone work
- Decimal phases (e.g., 2.1): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Test Infrastructure Foundation** - pytest config, fixtures, and cleanup patterns
- [ ] **Phase 2: Simple Unit Tests** - Pure logic tests (exceptions, emoji stripping, constants)
- [ ] **Phase 3: Protocol Mocking Infrastructure** - WebSocket and client mock fixtures
- [ ] **Phase 4: Entity & Config Flow Tests** - HA integration points with mocked dependencies
- [ ] **Phase 5: Protocol Layer Tests** - Complex WebSocket behavior with realistic mocks
- [ ] **Phase 6: Integration Tests** - End-to-end flows with mock Gateway server
- [ ] **Phase 7: Robustness Features** - Retry logic, typed exceptions, error messages

## Phase Details

### Phase 1: Test Infrastructure Foundation
**Goal**: Establish test framework foundation with pytest configuration, core fixtures, and cleanup patterns that prevent async pitfalls
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05
**Success Criteria** (what must be TRUE):
  1. Tests can be run with a single CLI command that shows coverage report
  2. Mock Home Assistant (hass) object is available as reusable fixture
  3. Mock config entries can be created without manual setup in each test
  4. WebSocket mock fixtures exist and can simulate basic connect/disconnect
  5. All test fixtures properly cleanup async resources (no "Event loop is closed" errors)
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md - Create pytest configuration and test directory structure
- [x] 01-02-PLAN.md - Create core test fixtures (hass, config entry, WebSocket mocks)
- [x] 01-03-PLAN.md - Verify infrastructure with smoke tests

### Phase 2: Simple Unit Tests
**Goal**: Build confidence with tests for pure logic (no async, no external dependencies) covering exceptions, constants, and text processing
**Depends on**: Phase 1
**Requirements**: UNIT-01, UNIT-02, UNIT-03
**Success Criteria** (what must be TRUE):
  1. All exception classes can be instantiated and carry expected error details
  2. All constants in const.py have documented expected values
  3. Emoji stripping removes all common emoji characters while preserving normal text
  4. Emoji stripping handles edge cases (empty strings, emoji-only text, multiple consecutive emojis)
**Plans**: TBD

Plans:
- [ ] TBD

### Phase 3: Protocol Mocking Infrastructure
**Goal**: Create reusable mock fixtures for GatewayProtocol and WebSocket connections that enable client layer testing
**Depends on**: Phase 2
**Requirements**: UNIT-04, UNIT-05, INTG-06, INTG-07
**Success Criteria** (what must be TRUE):
  1. Mock GatewayProtocol can simulate successful handshake sequence
  2. Mock GatewayProtocol can simulate connection failures and timeouts
  3. ClawdGatewayClient can send requests and receive responses with mocked protocol
  4. Client timeout behavior works correctly (request times out after configured duration)
  5. AgentRun buffering correctly accumulates cumulative text updates without duplication
**Plans**: TBD

Plans:
- [ ] TBD

### Phase 4: Entity & Config Flow Tests
**Goal**: Test Home Assistant integration points (conversation entity and config flow) with mocked gateway client
**Depends on**: Phase 3
**Requirements**: INTG-01, INTG-02, INTG-03, INTG-04, INTG-05
**Success Criteria** (what must be TRUE):
  1. Config flow validates connection before accepting configuration
  2. Config flow shows appropriate error messages for connection, auth, and timeout failures
  3. Options flow allows updating configuration after initial setup
  4. Conversation entity receives user messages and returns formatted responses
  5. Conversation entity strips emojis from responses when configured
  6. Conversation entity returns helpful error messages when agent requests fail
**Plans**: TBD

Plans:
- [ ] TBD

### Phase 5: Protocol Layer Tests
**Goal**: Test complex WebSocket protocol behavior including reconnection, authentication, and event dispatch
**Depends on**: Phase 3
**Requirements**: INTG-08, INTG-09
**Success Criteria** (what must be TRUE):
  1. Protocol successfully completes handshake with valid token
  2. Protocol rejects connection with invalid token (authentication error)
  3. Protocol automatically reconnects after connection loss
  4. Protocol transitions through connection states correctly (disconnected, connecting, connected)
  5. Protocol dispatches incoming events to registered handlers
  6. Background tasks (connection loop, receive task) cleanup properly on disconnect
**Plans**: TBD

Plans:
- [ ] TBD

### Phase 6: Integration Tests
**Goal**: Validate end-to-end request/response flows with mock WebSocket server simulating real Gateway behavior
**Depends on**: Phase 4, Phase 5
**Requirements**: None directly (validation of overall integration)
**Success Criteria** (what must be TRUE):
  1. Complete agent request flows from conversation entity through protocol to mock server and back
  2. Reconnection scenarios work correctly (disconnect mid-request, reconnect, retry)
  3. Multiple concurrent requests are handled correctly without interference
  4. Integration setup and teardown complete without resource leaks
  5. Coverage reports show ~90% overall coverage with gaps identified
**Plans**: TBD

Plans:
- [ ] TBD

### Phase 7: Robustness Features
**Goal**: Add retry logic, typed exception handling, and user-friendly error messages with test coverage
**Depends on**: Phase 6
**Requirements**: ROBU-01, ROBU-02, ROBU-03
**Success Criteria** (what must be TRUE):
  1. Failed requests automatically retry with exponential backoff (up to configured max retries)
  2. Broad exception handlers replaced with typed exception catching throughout codebase
  3. Common failure modes produce specific, actionable error messages (not generic "connection failed")
  4. All robustness features have test coverage verifying behavior
  5. Existing tests still pass after robustness changes (regression prevention)
**Plans**: TBD

Plans:
- [ ] TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Test Infrastructure Foundation | 3/3 | Complete | 2026-01-25 |
| 2. Simple Unit Tests | 0/0 | Not started | - |
| 3. Protocol Mocking Infrastructure | 0/0 | Not started | - |
| 4. Entity & Config Flow Tests | 0/0 | Not started | - |
| 5. Protocol Layer Tests | 0/0 | Not started | - |
| 6. Integration Tests | 0/0 | Not started | - |
| 7. Robustness Features | 0/0 | Not started | - |
