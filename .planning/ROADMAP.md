# Roadmap: Clawd Voice Assistant Test Coverage & Robustness

## Overview

Add focused test coverage and robustness improvements to this Home Assistant integration. Prioritize integration tests that exercise real user flows over comprehensive unit test coverage.

## Phases

- [x] **Phase 1: Test Infrastructure Foundation** - pytest config, fixtures, and cleanup patterns
- [x] **Phase 2: Simple Unit Tests** - Pure logic tests (exceptions, emoji stripping, constants)
- [x] **Phase 3: Integration Tests** - Config flow, conversation entity, connection handling (32 tests)
- [ ] **Phase 4: Robustness Features** - Retry logic, typed exceptions, error messages

## Phase Details

### Phase 1: Test Infrastructure Foundation
**Goal**: Establish test framework foundation with pytest configuration, core fixtures, and cleanup patterns that prevent async pitfalls
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05
**Status**: Complete
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md - Create pytest configuration and test directory structure
- [x] 01-02-PLAN.md - Create core test fixtures (hass, config entry, WebSocket mocks)
- [x] 01-03-PLAN.md - Verify infrastructure with smoke tests

### Phase 2: Simple Unit Tests
**Goal**: Build confidence with tests for pure logic (no async, no external dependencies) covering exceptions, constants, and text processing
**Depends on**: Phase 1
**Requirements**: UNIT-01, UNIT-02, UNIT-03
**Status**: Complete
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md - Constants and exceptions tests (UNIT-01, UNIT-02)
- [x] 02-02-PLAN.md - Emoji stripping tests (UNIT-03)

### Phase 3: Integration Tests
**Goal**: Test the real user flows with mocked WebSocket - config setup, sending messages, handling errors
**Depends on**: Phase 2
**Requirements**: INTG-01, INTG-02, INTG-04, INTG-05, INTG-08
**Success Criteria** (what must be TRUE):
  1. Config flow accepts valid configuration and rejects invalid (bad host, auth failure)
  2. User can send a message and receive a response through conversation entity
  3. Connection errors surface as helpful messages to the user
  4. Reconnection works after connection drops
**Plans**: 1 plan

Plans:
- [x] 03-01-PLAN.md - Config flow and conversation tests (32 tests)

### Phase 4: Robustness Features
**Goal**: Add retry logic, typed exception handling, and user-friendly error messages
**Depends on**: Phase 3
**Requirements**: ROBU-01, ROBU-02, ROBU-03
**Success Criteria** (what must be TRUE):
  1. Failed requests automatically retry with exponential backoff
  2. Broad exception handlers replaced with typed exception catching
  3. Common failure modes produce specific, actionable error messages
**Plans**: TBD

Plans:
- [ ] TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Test Infrastructure Foundation | 3/3 | Complete | 2026-01-25 |
| 2. Simple Unit Tests | 2/2 | Complete | 2026-01-25 |
| 3. Integration Tests | 1/1 | Complete | 2026-01-25 |
| 4. Robustness Features | 0/0 | Not started | - |
