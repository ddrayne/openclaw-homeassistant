# Requirements: Clawd Voice Assistant Testing & Robustness

**Defined:** 2026-01-25
**Core Value:** Users can reliably talk to their Clawdbot agent through Home Assistant voice interfaces without connection failures or cryptic errors interrupting the experience.

## v1 Requirements

Requirements for comprehensive test coverage and robustness improvements.

### Test Infrastructure

- [x] **INFRA-01**: pytest configuration with asyncio mode and proper event loop scope
- [x] **INFRA-02**: Common fixtures for mock hass object and mock config entry
- [x] **INFRA-03**: WebSocket mock fixtures for gateway protocol testing
- [x] **INFRA-04**: Test cleanup patterns to prevent resource leaks and flaky tests
- [x] **INFRA-05**: Nice test runner with clear output, coverage reporting, and easy CLI invocation

### Unit Tests

- [x] **UNIT-01**: Tests for const.py constants and configuration values
- [x] **UNIT-02**: Tests for exceptions.py exception hierarchy
- [x] **UNIT-03**: Tests for emoji stripping regex patterns and edge cases
- [ ] **UNIT-04**: Tests for protocol message parsing and validation
- [ ] **UNIT-05**: Tests for handshake request/response handling

### Integration Tests

- [x] **INTG-01**: Config flow user step validation tests
- [x] **INTG-02**: Config flow error handling tests (connection, auth, timeout)
- [ ] **INTG-03**: Config flow options flow tests
- [x] **INTG-04**: Conversation entity message handling tests
- [x] **INTG-05**: Conversation entity response formatting tests
- [ ] **INTG-06**: Gateway client request/response tests
- [ ] **INTG-07**: Gateway client timeout handling tests
- [x] **INTG-08**: Reconnection behavior tests (disconnect, reconnect, state recovery)
- [ ] **INTG-09**: Connection state change handling tests

### Robustness

- [ ] **ROBU-01**: Retry failed requests with exponential backoff
- [ ] **ROBU-02**: Specific, user-friendly error messages for common failure modes
- [ ] **ROBU-03**: Replace broad exception catching with typed exception handling

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced Testing

- **ADV-01**: Mock WebSocket server for end-to-end integration tests
- **ADV-02**: Performance/stress tests for concurrent requests
- **ADV-03**: CI/CD integration with GitHub Actions

### Additional Robustness

- **ADV-04**: Rate limiting for burst traffic protection
- **ADV-05**: JSON message size limits for security
- **ADV-06**: Connection status diagnostics entity

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Streaming TTS | High complexity, marginal UX benefit for voice |
| Home automation through Clawdbot | HA native intents handle device control better |
| SSL enforcement | Warning is sufficient, user choice preserved |
| AgentRun buffering unit tests | Lower priority, covered by integration tests |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Complete |
| INFRA-02 | Phase 1 | Complete |
| INFRA-03 | Phase 1 | Complete |
| INFRA-04 | Phase 1 | Complete |
| INFRA-05 | Phase 1 | Complete |
| UNIT-01 | Phase 2 | Complete |
| UNIT-02 | Phase 2 | Complete |
| UNIT-03 | Phase 2 | Complete |
| UNIT-04 | Deferred | - |
| UNIT-05 | Deferred | - |
| INTG-01 | Phase 3 | Complete |
| INTG-02 | Phase 3 | Complete |
| INTG-03 | Deferred | - |
| INTG-04 | Phase 3 | Complete |
| INTG-05 | Phase 3 | Complete |
| INTG-06 | Deferred | - |
| INTG-07 | Deferred | - |
| INTG-08 | Phase 3 | Complete |
| INTG-09 | Deferred | - |
| ROBU-01 | Phase 4 | Pending |
| ROBU-02 | Phase 4 | Pending |
| ROBU-03 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 22 total
- Mapped to phases: 22
- Unmapped: 0

---
*Requirements defined: 2026-01-25*
*Last updated: 2026-01-25 after Phase 3 completion (roadmap slimmed to 4 phases)*
