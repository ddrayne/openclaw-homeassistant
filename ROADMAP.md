# Roadmap & Enhancement Plan

Release scope and future ideas for the OpenClaw Home Assistant integration. This
file reflects what is **actually shipped** — earlier versions of this document
listed features (cron/spawn services, usage sensors) that were never implemented.

## Shipped today

- **Conversation entity** — voice/text Assist agent backed by the OpenClaw Gateway,
  with streaming responses (and a fallback for older HA), per-request model/thinking
  overrides, and session selection.
- **Multi-turn voice** — keeps the satellite mic open when the agent's reply asks a
  follow-up question (`continue_conversation`).
- **Proactive voice** (opt-in) — the agent can speak first on a satellite
  (`assist_satellite.announce` / `start_conversation`) for cron/background/follow-up
  turns. See the README "Proactive Voice" section.
- **TTS hygiene** — emoji stripping and optional length trimming.
- **Auth** — token + Ed25519 device pairing, with reauth and pairing flows; auto for
  local connections.
- **Connection** — persistent WebSocket with keepalive and automatic reconnect.
- **Services** — `openclaw.reconnect`, `openclaw.set_session`.
- **Diagnostic sensors** — gateway uptime, connected clients, health; connectivity
  binary sensor; config-entry diagnostics.

## Ideas (not yet built)

These are candidates, not commitments. The gateway exposes far more than the
integration currently uses; the most natural next steps for *Home Assistant users*:

### Voice-first
- Smarter follow-up detection than the simple `?` heuristic.
- Per-speaker / per-room sessions.

### Automation platform (for automation authors)
- A `notify` platform wrapping the gateway `send` method (Telegram/WhatsApp/etc.).
  Needs `operator.write` (already held).
- `openclaw.spawn_task` service + `openclaw_task_complete` event, via the `agent`
  method + `agent.wait`. Needs `operator.write` (already held).
- Cron management services. **Note:** cron *writes* (`cron.add/remove/run`) require
  the `operator.admin` scope, which the integration does not currently request —
  adding it would force existing users to re-pair, so this is gated behind a future
  scope-expansion release.

### Approvals
- Surface `exec.approval.requested` as an HA event + a `resolve_approval` service.
  Requires the `operator.approvals` scope (re-pair), so deferred alongside cron-writes.

### Observability
- Token usage / cost sensors, channel-status and model-auth sensors.

## Contributing

1. Open an issue to discuss the approach.
2. Reference this roadmap in your PR.
3. Keep behavior changes opt-in or clearly called out — don't change defaults for
   existing users without a CHANGELOG note.
