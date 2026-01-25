# Clawd Voice Assistant for Home Assistant

## What This Is

A Home Assistant custom integration that connects to Clawdbot Gateway, exposing a full AI agent as a conversation entity for voice and text interactions. Currently functional but lacks test coverage and robustness features needed for production reliability.

## Core Value

Users can reliably talk to their Clawdbot agent through Home Assistant voice interfaces without connection failures or cryptic errors interrupting the experience.

## Requirements

### Validated

- WebSocket connection to Clawdbot Gateway with auto-reconnect — existing
- Token-based authentication with optional SSL — existing
- Home Assistant conversation entity integration — existing
- Emoji stripping for clean TTS output — existing
- Session key routing to different Clawdbot sessions — existing
- Config flow with connection validation — existing
- Configurable agent response timeout — existing

### Active

- [ ] Comprehensive test coverage (~90%) for all modules
- [ ] Automatic retry with exponential backoff for failed requests
- [ ] Specific, helpful error messages instead of generic failures
- [ ] Replace broad exception catching with typed exception handling

### Out of Scope

- Streaming TTS responses — High complexity, marginal UX benefit for voice
- Home automation commands through Clawdbot — HA native intents handle this better
- Connection status sensor/diagnostics — Nice-to-have, not core reliability
- Rate limiting — Gateway handles this, client doesn't need it
- Enforcing SSL for remote — Warning is sufficient, user choice

## Context

**Existing codebase:**
- 7 Python modules in `custom_components/clawd/`
- Layered architecture: Integration → Client → Protocol
- No test files currently exist
- Uses `websockets>=12.0` for WebSocket communication
- Requires Home Assistant 2024.1.0+

**Technical debt identified:**
- Broad `except Exception` blocks hide real errors
- Fixed 5s reconnect delay (no backoff)
- No request retry on transient failures
- Private attribute access between layers (`_connected_event`)

**Codebase analysis:** See `.planning/codebase/` for detailed architecture, conventions, and concerns documentation.

## Constraints

- **Platform**: Must work with Home Assistant 2024.1.0+ and Python 3.11+
- **Dependencies**: Only `websockets>=12.0` as external dependency (keep minimal)
- **Testing**: Use pytest with pytest-asyncio for async testing
- **Compatibility**: Changes must not break existing configurations

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Tests first, then features | Safety net before behavior changes | — Pending |
| pytest + pytest-asyncio | Standard HA testing stack | — Pending |
| Mock WebSocket for unit tests | Avoid real network in tests | — Pending |

---
*Last updated: 2026-01-25 after initialization*
