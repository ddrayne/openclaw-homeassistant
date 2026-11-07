# Changelog

## Unreleased

### Fixed

- **A failed connection no longer disables the integration until Home Assistant
  restarts.** Three defects could combine into a permanent outage after a
  Gateway or reverse-proxy restart:
  - `disconnect()` awaited helper tasks that had already ended with
    `ConnectionClosedError` (close code `1012`), so teardown raised and broke
    unload, reload and the `openclaw.reconnect` service;
  - a finished connection loop left `_connect_task` set, so `connect()` — and
    therefore every later recovery attempt — was a silent no-op;
  - a single HTTP 401/403 on the WebSocket upgrade was treated as fatal.
- **Connection loops can no longer leave tasks running.** The connection loop
  stops helper tasks through the same exception-tolerant path as `disconnect()`
  and cancels the loop before its helpers, so a reconnect cannot install an
  untracked heartbeat.
- **A cleanly closed socket is no longer reconnected instantly.** A receive loop
  that returns normally (Gateway accepts and closes) pauses with the same
  backoff, closing a log- and CPU-flood path.
- **Failed setup stops its client.** When `async_setup_entry` gives up, the
  client's still-retrying connection loop is disconnected instead of left
  running outside `hass.data`.
- **`openclaw.reconnect` no longer fails as a whole.** A still-recovering entry
  is logged and the remaining entries are still reconnected.

### Changed (default behaviours)

- **HTTP 401/403 on the WebSocket upgrade is retried** up to
  `UPGRADE_AUTH_RETRY_ATTEMPTS` (4) times with backoff before a repair issue is
  raised, because a reverse proxy can reject a valid token for a few seconds
  while a Gateway or proxy restart reloads its configuration. A genuinely wrong
  token is still reported, about 75 s later instead of immediately. Auth and
  protocol errors returned *inside* the handshake remain fatal.
- **Transient reconnect failures back off from 5 s, doubling to a 60 s ceiling**,
  and the counters reset on a successful handshake. The first retry after a
  single Gateway restart is still 5 s; a Gateway that stays down produces at most
  one log line per minute instead of twelve.
