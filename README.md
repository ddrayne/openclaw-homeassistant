<p align="center">
  <img src="custom_components/openclaw/brand/icon.png" alt="OpenClaw" width="120" height="120">
</p>

<h1 align="center">OpenClaw Voice Assistant for Home Assistant</h1>

<p align="center">
  <b>Your whole OpenClaw agent, in every room.</b><br>
  Ask it anything by voice, let it get on with long jobs, and hear it speak up when it has something to tell you.
</p>

<p align="center">
  <a href="https://github.com/ddrayne/openclaw-homeassistant/releases/latest"><img src="https://img.shields.io/github/v/release/ddrayne/openclaw-homeassistant?label=release" alt="Latest release"></a>
  <a href="https://github.com/ddrayne/openclaw-homeassistant/actions/workflows/tests.yml"><img src="https://github.com/ddrayne/openclaw-homeassistant/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="https://hacs.xyz/"><img src="https://img.shields.io/badge/HACS-custom%20repository-41BDF5" alt="HACS custom repository"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/ddrayne/openclaw-homeassistant" alt="License"></a>
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=ddrayne&repository=openclaw-homeassistant&category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open this repository in HACS"></a>
  &nbsp;
  <a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=openclaw"><img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Add the OpenClaw integration to Home Assistant"></a>
</p>

---

[OpenClaw](https://openclaw.ai/) is an open-source AI agent that runs on your own
machine. It reads your email and calendar, browses the web, works with your files
and notes, and connects to 50+ services, using Claude, GPT or a local model.

This integration makes that agent a **Home Assistant conversation agent**. It is
not a separate chatbot with its own setup: it is the same agent you already talk
to in WhatsApp, Telegram or Discord, with the same skills, memory and context,
now reachable from any voice satellite, the mobile app or the Assist box.

## What it's like

> **You:** "Hey Jarvis, what's on today, and did Sam reply about Friday?"
>
> **OpenClaw:** "You have the dentist at ten and a team review at two. Sam
> replied an hour ago: Friday works, and she suggests the usual place at seven."

> **You:** "Go through my unread email and tell me what actually needs me."
>
> **OpenClaw:** "On it — I'll let you know when it's done."
>
> *…two minutes later, on the same speaker…*
>
> **OpenClaw:** "Three things need you: the insurance renewal is due Thursday…"

> *Unprompted, at 6 pm:*
>
> **OpenClaw:** "Your parcel was delivered to the side door. Want me to remind
> you after dinner?" *(the mic opens so you can just answer)*

## Why you'll like it

| | |
|---|---|
| 🧠 **Your real agent** | Every skill, integration, memory and model you've set up in OpenClaw. Nothing to rebuild for Home Assistant. |
| ⏳ **No more "that took too long"** | Slow requests are acknowledged straight away and the answer is [announced when it's ready](#background-work). |
| 📣 **It can speak first** | Reminders, finished tasks and follow-ups are spoken on a satellite of your choice with [proactive voice](#proactive-voice) (opt-in). |
| 🎙️ **Natural back-and-forth** | When the agent asks a question, the [mic stays open](#multi-turn-voice) so you can answer without the wake word. |
| 👥 **One assistant per agent** | Run [several agents from one gateway](#multiple-gateways-and-agents), each with its own wake word and voice. |
| ⚡ **Faster speech** | Optional [streaming](#response-streaming) starts speaking while the agent is still writing. |
| 🔁 **Stays connected** | Reconnects by itself through gateway and proxy restarts, and raises a Home Assistant repair when it needs you. |
| 🔒 **Private by design** | A direct connection from Home Assistant to your own gateway, with token and device pairing. [Security ›](#security) |

## Quick start

You need Home Assistant with [HACS](https://hacs.xyz/), and OpenClaw with its
Gateway running. Full details are under [Requirements](#requirements).

1. **Install.** Click the button, choose **Download**, then restart Home Assistant.

   [![Open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ddrayne&repository=openclaw-homeassistant&category=integration)

2. **Connect.** Click the button and enter your gateway's host, port and
   [token](#getting-a-gateway-token).

   [![Add the OpenClaw integration to Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=openclaw)

3. **Talk.** In **Settings → Voice assistants**, pick **OpenClaw** as the
   conversation agent for your assistant. That's it.

Prefer to do it by hand? See [Installation](#installation) and the
[setup walkthrough](#setup-walkthrough).

## Contents

- [Features](#features)
- [Entities](#entities)
- [Services](#services)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Setup walkthrough](#setup-walkthrough)
  - [Options reference](#options-reference)
  - [Connect the voice assistant](#connect-the-voice-assistant)
- [Usage](#usage)
  - [Example interactions](#example-interactions)
  - [Call the agent from automations](#call-the-agent-from-automations)
- [Feature guides](#feature-guides)
  - [Multi-turn voice](#multi-turn-voice)
  - [Background work](#background-work)
  - [Proactive voice](#proactive-voice)
  - [Sessions & agent routing](#sessions--agent-routing)
  - [Model & thinking overrides](#model--thinking-overrides)
  - [Emoji stripping](#emoji-stripping)
  - [TTS response trimming](#tts-response-trimming)
  - [Response streaming](#response-streaming)
  - [Voice-optimized session](#voice-optimized-session)
  - [Multiple gateways and agents](#multiple-gateways-and-agents)
- [Remote gateway setup](#remote-gateway-setup)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Security](#security)
- [Contributing](#contributing)
- [Credits & support](#credits--support)

## Features

**Agent**
- **Full agent access** — every skill, integration, memory, and model you've
  configured in OpenClaw, reachable by voice or text.
- **Multi-model** — uses whatever model OpenClaw runs (Claude, GPT, local), with
  optional per-integration model and thinking-mode overrides.

**Conversation**
- **Assist conversation agent** — drop-in agent for any Home Assistant voice
  pipeline or the Assist text box.
- **Streaming responses** *(opt-in)* — streams replies into Home Assistant's
  chat log so speech can start while the agent is still writing (HA 2025.6+).
  Off by default: replies are returned complete. [Details ›](#response-streaming)
- **Multi-turn voice** — when the agent asks a follow-up question, the satellite's
  mic stays open so you can answer without repeating the wake word. Automatic, no
  setup. [Details ›](#multi-turn-voice)
- **Background work** — long-running requests get an "on it" acknowledgment and
  the result is announced on your satellite when it's ready, instead of a
  timeout error. On by default. [Details ›](#background-work)
- **Proactive voice** (opt-in) — let the agent speak *first* on a satellite
  (reminders, "task done", follow-ups) via `assist_satellite.announce` /
  `start_conversation`. [Details ›](#proactive-voice)
- **TTS hygiene** — optional emoji stripping and length trimming for clean speech.

**Connection & auth**
- **Direct WebSocket** — real-time, persistent connection to the OpenClaw Gateway.
- **Token + device identity** — Gateway token plus an Ed25519 device keypair;
  remote devices approve once, local connections auto-approve.
- **Resilient** — keepalive pings, automatic reconnect with exponential backoff,
  retries through a Gateway/proxy restart instead of giving up on the first
  rejected upgrade, and HA repair issues when a token/pairing needs attention.
  A stopped connection loop can always be revived with the `reconnect` service.
- **Sessions & agent routing** — route HA conversations to a specific OpenClaw
  session and/or agent; when no agent is selected, the integration safely scopes
  the session to the gateway's default agent. Switch sessions on the fly.
  [Details ›](#sessions--agent-routing)

**Operations**
- **Diagnostic entities** — gateway uptime, connected clients, health, and a
  connectivity binary sensor. [See entities ›](#entities)
- **Diagnostics download** + UI-based configuration, **multiple gateways**, and a
  `reconnect` service.

## Entities

Each gateway you add creates one device, **OpenClaw Gateway**, with:

| Entity | Type | Category | Reports |
|---|---|---|---|
| `conversation.openclaw` | Conversation | — | Your OpenClaw agent — select it as a conversation agent in Assist |
| OpenClaw Gateway Uptime | Sensor | Diagnostic | Gateway uptime, in seconds |
| OpenClaw Connected Clients | Sensor | Diagnostic | Number of clients connected to the gateway |
| OpenClaw Gateway Health | Sensor | Diagnostic | Health status (e.g. `ok`) with version/uptime attributes |
| Gateway Connectivity | Binary sensor | Diagnostic | `connected` / `disconnected` |

The conversation entity also exposes the active host, port, session, agent, model,
thinking mode, and TTS/proactive settings as state attributes.

> Exact entity IDs are generated by Home Assistant and may differ from the examples
> here — check **Developer Tools → States** for the ones in your install.

## Services

| Service | Fields | Description |
|---|---|---|
| `openclaw.reconnect` | `entry_id` *(optional)* | Force a reconnect for one entry, or all entries if omitted. Restarts the connection loop even after it stopped on an authentication error, so it is the first thing to try when the gateway shows as unavailable. It returns after a short wait; if the Gateway is still coming back, the entries keep retrying in the background and each entry is attempted independently. |
| `openclaw.set_session` | `session_key` *(required)*, `entry_id` *(optional)* | Switch the active OpenClaw session for new requests. |

```yaml
# Example: switch the active session
action: openclaw.set_session
data:
  session_key: "voice-assistant"
```

## Requirements

- **Home Assistant 2024.1.0 or later.** Streaming (HA 2025.6+) and multi-turn
  voice use newer Assist APIs and degrade gracefully on older versions; **proactive voice** needs
  an `assist_satellite` entity (e.g. Home Assistant Voice PE) on a recent HA.
- A configured [OpenClaw](https://openclaw.ai/) install with the **Gateway running**
  (local or remote).
- A **Gateway token** (required since OpenClaw 2026.2.13+).

> OpenClaw runs on macOS, Windows, and Linux. Install and configure it — with your
> chosen model and any service integrations — before connecting Home Assistant.

## Installation

### HACS (recommended)

The quickest way is the button, which opens this repository in your HACS:

[![Open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ddrayne&repository=openclaw-homeassistant&category=integration)

Or add it by hand:

1. Open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add this repository URL with category **Integration**, then **Add**.
3. Search for **OpenClaw Voice Assistant** and **Download**.
4. **Restart Home Assistant.**

> Pre-release builds: enable **Show beta versions** in the integration's HACS page
> to install beta tags (e.g. `1.10.0-beta.2`).

For an existing installation, download the new version from the integration's
HACS page, then restart Home Assistant to load the updated code. If an update is
missing, refresh the repository information in HACS. Versions come from published
GitHub Releases, not tags alone; see [Releasing for HACS](RELEASING.md).

### Manual

1. Copy `custom_components/openclaw` into your Home Assistant `custom_components`
   directory.
2. **Restart Home Assistant.**

### Upgrading from Clawd v1.2.x

See [MIGRATION.md](MIGRATION.md) for the step-by-step rename/upgrade guide.

## Configuration

### Getting a Gateway token

Authentication is mandatory for all connections (including localhost) since
OpenClaw 2026.2.13+.

```bash
# Generate a new token
openclaw doctor --generate-gateway-token
# → prints e.g. 666c291bc8427a2dfb9e16e8871f2eec59f3e2ffee202a5f

# Or read an existing one from the environment
echo $OPENCLAW_GATEWAY_TOKEN
```

To allow connections from a Home Assistant instance on another machine, bind the
gateway to your LAN (and prefer SSL/TLS or an SSH tunnel for anything off-box):

```bash
openclaw gateway --bind lan
```

### Setup walkthrough

1. **Settings → Devices & Services → Add Integration → "OpenClaw Voice Assistant".**
2. **Connection** — enter:
   - **Host** — gateway hostname/IP (e.g. `192.168.1.100`; default `127.0.0.1`)
   - **Port** — gateway port (default `18789`)
   - **Gateway Token** — your token (required)
   - **Use SSL** — enable for `wss://` (recommended for remote)
   - **Agent Timeout** — max seconds to wait for an inline reply (default **300**,
     range 5–600); requests deferred to [background work](#background-work) get
     their own 1-hour budget
3. **Device approval** (first connect only):
   - **Local / localhost** → **auto-approved**, setup continues immediately.
   - **Remote** → a **Device Approval Required** step appears. Approve it, then
     **Submit**:
     ```bash
     openclaw devices list
     openclaw devices approve <device-id>   # or use the OpenClaw Control UI
     ```
     This is a **one-time** step — the device key is persisted and reused on every
     future connection and restart.
4. **Session & speech options** — every field here is optional and can be changed
   later via **Configure**. See the [options reference](#options-reference) for the
   full list (session, agent, model, thinking, emoji/TTS, and proactive voice).

### Options reference

All of these are editable any time via **Settings → Devices & Services → OpenClaw
→ Configure**.

| Option | Default | Description |
|---|---|---|
| **Host** | `127.0.0.1` | Gateway hostname or IP |
| **Port** | `18789` | Gateway port |
| **Gateway Token** | — | Authentication token (required) |
| **Use SSL** | Off | Use `wss://` (recommended for remote) |
| **Client certificate / private key** | *(none)* | Paths to a certificate and key for mTLS, if your gateway or proxy requires a client certificate — see [Client certificates (mTLS)](#client-certificates-mtls) |
| **Agent Timeout** | `300` s | Max wait for an inline reply (5–600); deferred runs get a 1-hour budget instead |
| **Session Key** | `main` | OpenClaw session to route HA conversations to |
| **Agent** | gateway default | Leave blank to resolve the gateway default, or select another agent; sessions are keyed as `agent:<id>:<session>` |
| **Model override** | gateway default | Per-integration model (e.g. `anthropic/claude-...`) |
| **Thinking mode** | gateway default | `off` / `low` / `medium` / `high` |
| **Strip emojis from TTS** | On | Remove emojis from spoken output |
| **TTS max characters** | `0` (no limit) | Trim long spoken replies (0–2000) |
| **Streaming responses** | Off | Stream replies so speech starts sooner (needs TTS max characters `0`) — see [Response streaming](#response-streaming) |
| **Background work** | On | Slow requests answer later via announce instead of timing out |
| **Grace period** | `10` s | Silence before a request is deferred to background (3–60) |
| **Holding phrase** | “On it — I’ll let you know when it’s done.” | Spoken when a request is deferred before the agent has said a complete sentence |
| **Proactive voice** | Off | Let the agent speak first on a satellite |
| **Satellite to speak on** | — | `assist_satellite` entity used for proactive announcements |
| **Proactive mode** | `announce` | `announce` (speak) or `start_conversation` (speak + reopen mic) |

### Connect the voice assistant

1. **Settings → Voice Assistants → Assist** (or your pipeline of choice).
2. Under **Conversation agent**, select **OpenClaw**.
3. Save.

## Usage

- **Voice** — any HA voice interface (mobile app, Voice PE / `assist_satellite`,
  etc.).
- **Text** — the Assist box in the HA UI.
- **Automations** — call the agent programmatically (see below).

### Example interactions

**Email & communication**
- "Do I have any important emails from [person]?"
- "Send an email to [person] about tomorrow's meeting"
- "Who sent me a Telegram message?"

**Calendar & scheduling**
- "What's on my calendar today?"
- "Add a dentist appointment next Tuesday at 2pm"

**Information & web**
- "Search for restaurants near me"
- "Browse to [website] and summarize the main article"

**Files & notes**
- "Find my notes about [topic]"
- "Save this to my notes: [content]"

**Conversational**
- "Who are you?", "Explain how photosynthesis works", "Tell me a joke"

> Exact capabilities depend on your OpenClaw configuration, skills, and service
> integrations. For simple device control ("turn on the lights"), prefer Home
> Assistant's built-in intents — see [Limitations](#limitations).

### Call the agent from automations

The conversation entity is callable from any script or automation via
`conversation.process` — ask the agent something on a schedule and act on the
reply (e.g. a spoken morning briefing):

```yaml
action: conversation.process
data:
  # Your OpenClaw conversation entity id — find it in Developer Tools → States.
  agent_id: conversation.openclaw
  text: "Give me a one-sentence summary of today's calendar."
response_variable: result

# …then, for example, speak it:
action: assist_satellite.announce
target:
  entity_id: assist_satellite.kitchen
data:
  message: "{{ result.response.speech.plain.speech }}"
```

## Feature guides

### Multi-turn voice

When the agent's reply asks a follow-up question, the integration sets
`continue_conversation` so the satellite **keeps its mic open** — you can answer
without saying the wake word again. It works automatically, requires no
configuration, and falls back cleanly on HA versions that don't support the flag.

### Background work

A voice turn is synchronous — the satellite expects speech back within seconds.
But agent work like browsing the web or triaging email can stay silent for
minutes. Instead of ending in “the response took too long”, the integration
races every request against a short **grace period** (default **10s**):

- **Agent starts talking in time** → the answer is returned inline, exactly as
  normal (streamed, if **Streaming responses** is on).
- **Agent starts talking, then goes quiet for the grace period** (typically a
  slow tool call after “Let me go through your inbox.”) → the turn ends with
  **the agent's own words** as the holding line, up to its last complete
  sentence. The run continues in the background, and the rest of the answer is
  announced when it finishes, without repeating what was already said. If the
  agent stopped mid-sentence, the **holding phrase** is used instead.
- **Still silent when the grace period ends** → the assistant speaks the
  **holding phrase** (“On it — I’ll let you know when it’s done.”), the run
  continues in the background, and the result is **announced when it finishes**
  — on the satellite you spoke to, falling back to the configured proactive
  satellite. Failures are announced too, so a deferred request never goes
  silent.

A deferred turn never reopens the satellite's mic, even if its holding line is
a question, because the agent is still working.

> **Tip:** ask your voice agent to say briefly what it is about to do before
> using a tool (“Let me check your calendar.”). That sentence then becomes the
> holding line, which sounds far more natural than a fixed phrase.

On by default; tune or disable it under **Configure** (**Background work**,
**Grace period**, **Holding phrase**). It works even with proactive voice off —
the report-back speaks directly on the originating satellite.

> **The race measures your agent’s time-to-first-content, not question
> difficulty.** A heavyweight agent (big model, thinking enabled) can take
> longer than the grace period to say *anything* — then even “what time is
> it?” defers and gets announced a moment later. If that happens, make the
> voice agent fast rather than the grace long: set **Thinking mode** to `off`
> and/or a fast **Model override** in this integration’s options, or route to
> a [voice-optimized session](#voice-optimized-session). Raising **Grace
> period** works too, at the cost of slower deferral for genuinely long work.

### Proactive voice

By default the assistant only speaks when spoken to. **Proactive voice** (opt-in)
lets the agent speak *first* on a satellite — announcing a reminder, telling you a
background task finished, or asking a follow-up.

Enable it under **Configure**:

- **Proactive voice** — turn it on (off by default).
- **Satellite to speak on** — the `assist_satellite` entity (e.g. Voice PE).
- **Proactive mode**:
  - `announce` — speak the message.
  - `start_conversation` — speak it **and** reopen the mic for your reply.

Replies you trigger yourself are never re-announced — only agent-*initiated* turns
are.

> **It needs a trigger.** Proactive voice is a *delivery* mechanism: it speaks when
> the gateway produces a proactive turn — an agent **cron job**, a **background
> task**, or the agent choosing to message you. With none of those configured on
> the OpenClaw side, you won't hear anything. Set up agent reminders/cron in
> OpenClaw to give it something to say.

### Sessions & agent routing

The **Session Key** routes HA conversations to a specific OpenClaw session:

- **`main`** (default) — the standard direct-chat session.
- **Custom** — isolate or organize HA conversations (e.g. `voice-assistant`,
  `automation`).

Switch sessions dynamically without reconfiguring via `openclaw.set_session` (see
[Services](#services)). If you leave **Agent** blank, the integration asks the
gateway for its default agent and keys the session as
`agent:<default-id>:<session>`. Set **Agent** to route to a different one
explicitly.

### Model & thinking overrides

Set **Model override** and **Thinking mode** under **Configure** to use a specific
model or reasoning depth for requests from this integration, independent of your
other OpenClaw channels.

### Emoji stripping

**Strip emojis from TTS speech** (default **on**) removes emojis from spoken output
for cleaner TTS:

- "I'm Claude 🦞" → speaks "I'm Claude" (emoji still visible in chat history).
- Disable it if your TTS engine handles emojis well, or if you mostly use the text
  Assist box.

### TTS response trimming

**TTS max characters** caps spoken replies:

- **`0`** (default) — no limit.
- **`> 0`** — trim to that many characters (an ellipsis is added when trimmed).

### Response streaming

**Streaming responses** (off by default) feeds the agent's reply into Home
Assistant's chat log as it is written, using `ChatLog.async_add_delta_content_stream`
(HA 2025.6+). On a voice pipeline, HA starts speaking once the first ~60
characters arrive instead of waiting for the whole reply — noticeably snappier
for longer answers. Short replies behave the same either way.

- Turn it on under **Configure → Streaming responses**, with **TTS max
  characters** at `0` (trimming needs the complete text, so a positive limit
  keeps the complete-reply path).
- With streaming on, emoji stripping applies to the chat-log text too, not just
  the spoken reply.
- With streaming on, text the agent writes before using a tool ("Let me check.")
  is spoken too, followed by the answer — as with Home Assistant's built-in LLM
  agents. With it off, only the final reply is spoken.
- If a reply looks cut short in the Assist dialog, turn streaming off and please
  [open an issue](https://github.com/ddrayne/openclaw-homeassistant/issues) with
  debug logs.

### Voice-optimized session

For the most natural voice experience, point the integration at a dedicated
OpenClaw session whose system prompt is tuned for speech:

```
You are a voice assistant for a smart home. Keep responses:
- Brief and conversational (1–3 sentences when possible)
- Natural for text-to-speech (no bullet points, formatting, or code blocks)
- Free of emojis and special characters
- Direct and to the point
When performing tasks (email, calendar, …), confirm the action briefly.
```

Then set **Session Key** to that session under **Configure**. Your other OpenClaw
channels (Telegram, Discord, …) keep their own settings. See the
[OpenClaw docs](https://docs.openclaw.ai/) for configuring sessions and prompts.

### Multiple gateways and agents

Each integration entry is one **gateway + agent + session**, with its own
conversation entity and device. That gives two common setups:

- **Several gateways** — add the integration once per gateway.
- **Several agents on one gateway** — add the integration again with the same
  host and port, and pick a different **Agent** (or **Session Key**) on the
  second screen. Each becomes its own conversation agent, so you can give each
  one a separate Assist pipeline with its own TTS voice and wake word. The entry
  title names the agent so they're easy to tell apart.

Adding the same gateway, agent and session twice is still rejected as already
configured.

## Remote gateway setup

### Option 1 — direct connection (recommended, with SSL)

- Host: `gateway.example.com` or IP · Port: `18789` · **Use SSL: ✓** · Token: required
- Approve the device once in OpenClaw on first connect (see
  [Setup walkthrough](#setup-walkthrough)).

### Client certificates (mTLS)

If the gateway sits behind a proxy that requires a client certificate, set
**Client certificate path** and **Client private key path** (during setup, or
later under **Configure**). Both are needed, together with **Use SSL**.

- The paths are read by Home Assistant, so the files must be somewhere it can
  reach — for example `/config/ssl/openclaw-client.crt` and
  `/config/ssl/openclaw-client.key`.
- Both files are PEM. The private key must **not** be passphrase-protected.
- The files are checked when you save: a missing file, or a certificate and key
  that don't match, is reported in the form instead of failing later.
- Clear both fields to go back to ordinary TLS.

### Option 2 — SSH tunnel

```bash
# Run on the Home Assistant machine
ssh -N -L 18789:localhost:18789 user@gateway-host
```

Then configure Host `127.0.0.1`, Port `18789`, token required. Over the tunnel the
connection looks local to OpenClaw, so device pairing is typically auto-approved.

## Troubleshooting

**Integration unavailable after a Gateway or proxy restart**
- Restarting the Gateway (upgrade, rollout, container restart) or a reverse proxy
  in front of it can make the WebSocket upgrade fail with HTTP 401/403 or 502/503
  for a few seconds even though the token is fine. The integration retries those
  with a backoff (5 s, doubling to a 60 s ceiling) and only reports an
  authentication failure after several consecutive rejections.
- If the entities still show unavailable, call **`openclaw.reconnect`**
  (Developer tools → Actions). It restarts the connection loop even after it
  stopped on an authentication error, so it is the first thing to try. The
  service waits a few seconds for the connection and can report that a reconnect
  is still in progress: the loop keeps retrying (5 s, doubling to 60 s) and turns
  the entities available when the Gateway answers. Reloading the integration or
  restarting Home Assistant does the same and is not normally needed.
- Enable debug logging (below) to see each connection attempt and its backoff.

**Cannot reach the gateway**
- Confirm it's running: `openclaw status`. Verify host/port and firewall. Enable
  SSL if the remote requires it.

**Authentication failed / invalid token**
- Re-check the token (`echo $OPENCLAW_GATEWAY_TOKEN`) or generate a new one
  (`openclaw doctor --generate-gateway-token`) and update it under **Configure**.

**Device approval required**
- Appears on first connect from a **remote** machine. Approve with
  `openclaw devices approve <device-id>` (or the Control UI), then **Submit**.
  One-time only.

**Device pairing required (repair issue)**
- If a previously approved device loses pairing (e.g. an OpenClaw data reset), a
  repair issue appears. Re-approve in OpenClaw, then reload the integration.

**Response timeout**
- With **Background work** on (the default), slow requests defer to a background
  announce instead of timing out, so “the response took too long” should be
  rare — it means **Background work** is off. A deferred run gets its own
  budget (**1 hour**, independent of Agent Timeout); if it still hasn’t
  finished by then, that is announced too. The **Agent Timeout** only governs
  inline (non-deferred) replies, so it’s safe to keep it short for snappy
  voice failures.

**Protocol mismatch**
- Means the integration and gateway speak different protocol versions. Update both
  the integration (HACS) and OpenClaw to current releases.

**Diagnostics & logs**
- Download diagnostics: **Settings → Devices & Services → OpenClaw → ⋮ →
  Download diagnostics**.
- Enable debug logging:
  ```yaml
  logger:
    logs:
      custom_components.openclaw: debug
  ```
  (The logger name is `custom_components.openclaw`.)

## Limitations

- **Response time** — typical queries take 5–10s; agent tasks (email, web, files)
  can take 15–30s+. That's slower than rule-based assistants (1–2s) but far more
  capable.
- **Device control** — the agent excels at information, tasks, and agentic
  workflows. For simple control ("turn on the lights"), Home Assistant's **native
  intents** are faster and more reliable; run them alongside OpenClaw.
- **Context** — in-HA conversation history is managed by HA's ChatLog; OpenClaw's
  own cross-platform memory is unaffected.
- **Proactive voice** — only speaks when the gateway produces a proactive turn (see
  [Proactive voice](#proactive-voice)), and requires an `assist_satellite` entity.
- **Background work across restarts** — a request deferred to background is
  dropped if Home Assistant restarts before it finishes (the gateway run
  continues; with proactive voice enabled its answer can still arrive). While a
  deferred run is in flight, proactive announcements are held back to avoid
  double-speaking its result.

## Security

- **Layered authentication** — current gateways use a Gateway token and a unique
  Ed25519 device identity; legacy gateways may use token-only authentication.
- **Local credential storage** — the token is held in Home Assistant's config
  entry storage and the device key uses private-permission storage. This
  integration does not add application-level encryption, so protect your Home
  Assistant config directory and backups.
- **Pairing approval** — remote devices require one-time approval; local
  connections auto-approve.
- **Transport** — use SSL/TLS (or an SSH tunnel) for anything off-box; the
  integration warns when connecting to a non-localhost host without SSL.
- The token grants access to your agent — keep it secret and use a dedicated,
  least-privilege agent where possible.
- Report suspected vulnerabilities privately as described in
  [SECURITY.md](SECURITY.md).

## Contributing

Issues and PRs welcome. See [ROADMAP.md](ROADMAP.md) for what's shipped and what's
being considered, [GATEWAY_API.md](GATEWAY_API.md) for the Gateway API reference,
and [AGENTS.md](AGENTS.md) for tuning agents for voice. Keep behavior changes
opt-in or clearly called out — don't change defaults for existing users without a
note.

Maintainer releases are documented in [RELEASING.md](RELEASING.md). HACS tracks
the newest published GitHub Release, not a bare Git tag, and the release tag must
match the version in `custom_components/openclaw/manifest.json`.

## Credits & support

- **OpenClaw** — open-source local AI agent system · [openclaw.ai](https://openclaw.ai/)
  · [docs](https://docs.openclaw.ai/)
- **This integration** — community Home Assistant integration for the OpenClaw
  Gateway, maintained by [@ddrayne](https://github.com/ddrayne). Thanks to
  contributors [@IsakCode222](https://github.com/IsakCode222) (multi-turn voice),
  [@thezapalsky](https://github.com/thezapalsky) (action-run responses),
  [@lanquarden](https://github.com/lanquarden) (connection recovery),
  [@chotaling1](https://github.com/chotaling1) (replies on newer gateways),
  [@biacz](https://github.com/biacz) (streaming),
  [@albaintor](https://github.com/albaintor) (early-event fix, streaming design)
  and [@NsCDE](https://github.com/NsCDE) (mTLS, options fixes).
- **Support** — [GitHub Issues](https://github.com/ddrayne/openclaw-homeassistant/issues)
  · [Home Assistant Community](https://community.home-assistant.io/)

## License

Apache License 2.0 — see [LICENSE](LICENSE).
