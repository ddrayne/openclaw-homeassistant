# Changelog

## 1.10.0 — 2026-11-14

Stable release of everything in the three betas below. There are no code
changes since 1.10.0-beta.3. Compared with 1.9.0, in short:

- Chinese, Japanese and Korean replies are no longer erased by emoji stripping
  (#22).
- The holding line can be the agent's own words, and a reply that goes quiet
  hands off to the background.
- Settings screens and built-in spoken phrases in 13 languages.
- Optional mTLS client certificates (#27), clearable token and model override
  (#26), and session changes without a reload (#28).

## 1.10.0-beta.3 — 2026-11-14

### Added

- **Translated settings screens** in German, French, Spanish, Italian, Dutch,
  Polish, Brazilian Portuguese, Swedish, Japanese, Korean, and Simplified and
  Traditional Chinese. The translations are machine-generated; tests keep
  every language complete and stop names and identifiers being translated.
- **Built-in spoken phrases follow the language of the request**, in the same
  languages: the holding phrase and the messages for a timeout, a connection
  or authentication problem, an agent error and an empty reply.

### Changed (default behaviours)

- **The default holding phrase is now spoken in the request's language.** A
  holding phrase you have typed under Configure is still used exactly as
  written; only the untouched English default is replaced.

### Fixed

- **Follow-up questions in Chinese, Japanese and Arabic keep the mic open.**
  Only the Western `?` was recognised.
- **The holding line works for Chinese and Japanese replies.** Their sentence
  endings (`。！？`, with no following space) were not recognised, so the
  agent's own words were never used.

## 1.10.0-beta.2 — 2026-11-14

### Added

- **Client certificates (mTLS)** (#27). Optional **Client certificate path**
  and **Client private key path** for gateways behind a proxy that requires a
  client certificate. Needs **Use SSL**. The files are validated when the form
  is saved, a bad certificate or key stops with a clear error instead of being
  retried forever, and a passphrase-protected key is rejected rather than
  prompting on the terminal.

### Fixed

- **The gateway token and model override can be cleared** in the options form
  (#26). Once set, they could not be emptied again.
- **Changing only the session no longer reloads the integration** (#28). The
  new session is applied to the live connection; any other change still
  reloads as before.
- **Chinese, Japanese and Korean replies were never shown or spoken (#22).**
  With **Strip emojis** on (the default), the emoji pattern's `U+24C2–U+1F251`
  range also matched every CJK ideograph, kana and Hangul syllable, so the
  whole reply was stripped and Assist showed "...". The pattern now lists emoji
  blocks only. It also removes newer emoji it used to miss (🦞), whole ZWJ
  sequences and flags, and a reply that is nothing but emoji is no longer
  turned into an empty response.

### Thanks

- @NsCDE — mTLS, clearable options and the session change without a reload
  (#26, #27, #28), split out of #17 with tests
- @Dandeguin — the debug log that pinned down #22

## 1.10.0-beta.1 — 2026-11-07

### Changed (default behaviours)

- **The holding line can be the agent's own words.** Background work used to
  defer a request only when the agent said nothing within the grace period. An
  agent that replied "Let me go through your inbox." and then spent minutes in
  a tool call kept the satellite waiting inline for up to the Agent Timeout.
  Now a reply that goes quiet for the grace period is deferred too: the turn
  ends with what the agent has said, up to its last complete sentence, and the
  rest of the answer is announced when it finishes, without repeating what was
  already said. If the agent stopped mid-sentence, the configured holding phrase
  is used instead.
- **A deferred turn never reopens the satellite's mic**, even if the holding
  line is a question, because the agent is still working.

## 1.9.0 — 2026-11-07

### Added

- **Several agents on one gateway (#13).** Add the integration again for the
  same gateway and pick a different **Agent** (or **Session Key**): each becomes
  its own conversation agent, so each can have its own Assist pipeline, TTS
  voice and wake word. Entries are now unique per gateway + agent + session;
  existing entries keep working (one set to a specific agent moves to the new
  ID automatically). Entry titles name the agent when one is set.
- **Streaming responses (opt-in).** A new **Streaming responses** option streams
  replies into Home Assistant's chat log via `ChatLog.async_add_delta_content_stream`
  (HA 2025.6+), so a voice pipeline starts speaking while the agent is still
  writing. Previously the integration probed for a `response_stream` API that
  Home Assistant never shipped, so streaming silently never ran (#14). Off by
  default; needs **TTS max characters** at `0`. When streamed, an agent's
  separate reply items (text before a tool call, then the answer) are separated
  by a paragraph break instead of running together.

### Fixed

- **The integration icon shows again (#22).** Home Assistant 2026.3+ reads a
  custom integration's icon from its `brand/` folder; the icons were at the
  integration root, where it never looks.
- **An empty reply no longer leaves Assist showing "..." (#22).** A run that
  finishes without any text now answers "I didn't get a reply from OpenClaw.
  Please try again." and logs a warning, instead of an empty response.
- **Errors in the options form show text instead of raw keys** (`invalid_auth`,
  `cannot_connect`, …) — the options flow had no error translations.
- **Replies on OpenClaw 2026.10+ were cut to their first fragment** — Voice PE
  speaking only "He" for "Heute leichter Regen…". Newer gateways send the text
  snapshot only on an item's first event and `delta` alone afterwards; deltas
  are now appended, including for a new `itemId` (#18, #19).
- **Fast replies could be lost before the request was acknowledged.** When the
  agent RPC's acknowledgement and the run's first events arrived together, the
  events were handled before the run was registered and dropped, leaving the
  request waiting for a completion that had already happened. They are now
  buffered while an agent request is pending and replayed in order.
- **A token a proxy keeps refusing (HTTP 401/403) now opens reauth at setup**
  instead of retrying setup forever with "may not be reachable". Setup counts
  refusals across its retries and gives up after the same budget as the
  connection loop; the setup error now names the HTTP status.
- **`wss://` connections no longer load certificates on the event loop.** The
  TLS context is built once in a worker thread and reused, removing Home
  Assistant's blocking-call warning on every connect.
- **`openclaw.reconnect` reports an authentication failure as an error** with
  the fix, instead of "still in progress".
- **Multi-item replies no longer log a warning** ("Non-cumulative text update").
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

- **Adding an exact duplicate entry is rejected after the session step**
  instead of on the first screen, because the agent and session are chosen
  there.
- **HTTP 401/403 on the WebSocket upgrade is retried** up to
  `UPGRADE_AUTH_RETRY_ATTEMPTS` (4) times with backoff before a repair issue is
  raised, because a reverse proxy can reject a valid token for a few seconds
  while a Gateway or proxy restart reloads its configuration. A genuinely wrong
  token is still reported: about 75 s later on a running entry, or after a few
  setup retries at startup, instead of immediately. Auth and protocol errors
  returned *inside* the handshake remain fatal.
- **Transient reconnect failures back off from 5 s, doubling to a 60 s ceiling**,
  and the counters reset on a successful handshake. The first retry after a
  single Gateway restart is still 5 s; a Gateway that stays down produces at most
  one log line per minute instead of twelve.

### Thanks

- @lanquarden — connection recovery after Gateway/proxy restarts, with field
  evidence and regression tests (#20, #21)
- @chotaling1 — delta-only assistant events (#19)
- @biacz — ChatLog streaming (#14), plus the captured gateway event sequence now
  used as a regression test (#16)
- @albaintor — buffering early agent events, and the opt-in streaming design
  (#15)
