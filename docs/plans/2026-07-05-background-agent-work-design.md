# Background agent work — design

**Date:** 2026-07-05
**Status:** Approved, ready for implementation

## Problem

Long-running agent requests speak "The response took too long. Please try
again." on a voice satellite. That message is raised whenever a
`GatewayTimeoutError` bubbles up (`conversation.py:303` / `:433`), which happens
when the agent goes silent longer than the configured timeout (default 120s).

A voice conversation turn is synchronous: the user speaks and Home Assistant's
pipeline expects speech back within the turn. For an agent that browses the web
or fetches mail — work that produces no tokens for tens of seconds — no timeout
value fixes this. The right shape is: **acknowledge quickly, do the work in the
background, and report back when done** — which the integration already has a
primitive for (proactive-voice announce).

## Goal

Turn "block for N seconds or fail" into "acknowledge in ~1s, report back when
done," while leaving quick questions exactly as they are today.

## Flow

Per voice request:

1. Start the agent run and race it against a **grace timer** (default 10s).
2. **Fast path** — first content arrives before the grace timer fires → behave
   exactly as today (streaming result + incremental TTS on streaming-capable HA;
   awaited plain result on older HA).
3. **Slow path** — grace elapses with no content → return a normal result
   speaking a **holding phrase** ("On it — I'll let you know when it's done."),
   ending the turn cleanly, and **detach** the run to a background task.
4. When the detached run finishes, **announce the result** on the satellite the
   user spoke to (resolved from `device_id`), falling back to the configured
   proactive satellite. Emoji-strip + TTS-trim reused from the announce path.
5. If the detached run errors or times out (now 300s), announce a short failure
   rather than staying silent.

**Trigger is "first content within grace," not "completion within grace."** A
chatty agent that starts talking quickly streams inline even if the full answer
is long; only genuinely-silent work is deferred.

## Mechanism — robust race via the existing queue

`AgentRun` already decouples the network stream from the consumer: incoming
gateway events feed `_stream_queue` / `_full_text` regardless of who is consuming
(`gateway_client.py:74-93`), and `complete_event` + `get_response()` expose the
finished result. We lean on that so we never cancel a generator mid-flight.

1. `begin_run(message)` starts the run (`_start_agent_run(..., stream=True)`) and
   returns a small **handle** wrapping the `AgentRun`. Chunks accumulate in the
   queue from this instant.
2. The turn peeks: `first = await asyncio.wait_for(queue.get(), grace)`.
   Cancelling `queue.get()` on timeout is **safe** — nothing dropped, no
   generator to corrupt.
3. **Fast path** (real first chunk): return a streaming result whose generator
   re-yields `first`, then delegates to `iter_stream()`, then raises on error
   status. On non-streaming HA: await completion, return plain result.
4. **Slow path** (`TimeoutError`): hand the handle to a background task, return
   the holding phrase. The background task drains `iter_stream()` to exhaustion
   (reuses the per-chunk 300s timeout and error-raising), then announces
   `get_response()`.
5. Edge cases fall out cleanly: first queue item is the completion sentinel
   `None` → run finished fast (empty or error) → handled inline via status check.
   Cleanup (`_agent_runs.pop`) lives in the handle's `finally` on both paths.

Exactly **one** consumer of `iter_stream` ever exists — the turn's wrapper *or*
the background task, chosen by the race, never both.

The grace-race lives at the run level, so it is independent of whether HA
supports inline streaming; only the fast-path presentation differs.

## Echo suppression

`_handle_session_message` currently suppresses the echo of the user's own turn
only for `PROACTIVE_SUPPRESS_SECONDS` (15s) after `_last_local_turn`
(`gateway_client.py:616`). A detached run finishing after 40s lands outside that
window, so the gateway's `session.message` echo would be announced by the
proactive handler *and* by our detached-report path → double-speak.

Fix: replace the single-timestamp heuristic with an explicit set of in-flight
local run IDs.

- Add `run_id` to `self._active_local_runs` when a local turn (including a
  detached one) starts; remove it on completion.
- `_handle_session_message` suppresses if `_active_local_runs` is non-empty *or*
  within the existing 15s tail (kept, to cover the race between completion and
  the echo arriving).

This models the real rule — "a `session.message` during our own run is its echo"
— and covers detached runs of any duration. No-op when proactive voice is off
(that handler only runs when a proactive callback is registered). The
detached-report path calls `assist_satellite.announce` directly, so background
reporting works even without proactive voice configured.

## Report-back target resolution

- From `user_input.device_id` → `entity_registry.async_entries_for_device` →
  first entity with domain `assist_satellite`.
- If none found (or no `device_id`), fall back to `CONF_PROACTIVE_SATELLITE`.
- If neither exists, log a warning and drop the announce.

## Error handling (detached run)

Always speak something back rather than leaving the request hanging:

- Agent error → "Sorry — that request ran into a problem."
- Timeout (per-chunk 300s exceeded) → "That one took too long, so I stopped."
- Success → assembled `get_response()`, emoji-stripped + TTS-trimmed.
- Satellite offline/unresolvable → log a warning and drop (existing announce
  code already handles this cleanly).

The two failure phrases stay hardcoded (good defaults, not worth a settings row).

## Configuration

**Changed:**

- `DEFAULT_TIMEOUT`: 120 → **300**. Form range max 300 → **600**
  (`config_flow.py:254`).

**New options** (options flow, alongside proactive settings):

- `CONF_BACKGROUND_ENABLED` (`background_enabled`), default **True** — master
  toggle. Off restores today's behavior (long silent work hits "the response
  took too long").
- `CONF_BACKGROUND_GRACE` (`background_grace`), default **10s**, range 3–60.
- `CONF_HOLDING_PHRASE` (`holding_phrase`), default
  "On it — I'll let you know when it's done."

Wiring threads through `__init__.py` (already merges `data` + `options`) into the
conversation entity. `background_grace` and the phrases are read per-request from
merged config, so changes apply without a reload.

## Lifecycle

- Background task created via `hass.async_create_background_task`, tracked on the
  entity, cancelled cleanly on unload/reload.
- Multiple concurrent detached runs allowed; each owns its own announce.

## Testing (TDD, pytest + pytest-asyncio)

1. Fast path — first chunk before grace → streaming result, chunks stream inline.
2. Slow path — no chunk within grace → holding phrase returned; background task
   announces assembled text on the origin satellite.
3. Target resolution — `device_id` → `assist_satellite`; fallback to proactive
   satellite; neither → warning, no announce.
4. Detached error → error phrase announced; detached timeout → timeout phrase
   announced.
5. Echo suppression — while a detached run is in `_active_local_runs`, the
   `session.message` echo is suppressed; after removal + tail window, proactive
   announce works again.
6. Emoji-strip + TTS-trim applied to the detached report.
7. Config — new defaults/ranges, `DEFAULT_TIMEOUT`=300 / max 600,
   `background_enabled=False` restores old behavior.

## Out of scope (broader improvements noticed)

- The `StreamingConversationResult` kwarg-probing (`conversation.py:352-391`) is
  fragile; candidate for a later cleanup.
- Two `*-openclaw-backup.tar.gz` files sit untracked in the repo root; probably
  want gitignoring.
