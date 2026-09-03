# Understanding OpenClaw Agents

This guide explains how OpenClaw agents work and how to configure them for optimal Home Assistant integration.

## Table of Contents

- [What is an Agent?](#what-is-an-agent)
- [Agent Architecture](#agent-architecture)
- [Agent Configuration](#agent-configuration)
- [Session Management](#session-management)
- [Multi-Agent Setup](#multi-agent-setup)
- [Voice-Optimized Agents](#voice-optimized-agents)
- [Agent Customization](#agent-customization)
- [Best Practices](#best-practices)

## What is an Agent?

A **OpenClaw agent** is an AI assistant instance with:
- A specific AI model (Claude, GPT, or local models)
- Custom system prompts and behavior
- Access to configured skills and integrations
- Memory and conversation context
- Unique identity and capabilities

Think of agents as different "personalities" or "experts" you can talk to, each configured for specific tasks.

## Agent Architecture

### Components

```
┌─────────────────────────────────────────────┐
│            OpenClaw System                  │
├─────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐    │
│  │ Agent   │  │ Agent   │  │ Agent   │    │
│  │ "main"  │  │ "codex" │  │ "voice" │    │
│  │         │  │         │  │         │    │
│  │ Model:  │  │ Model:  │  │ Model:  │    │
│  │ Sonnet  │  │ Opus    │  │ Sonnet  │    │
│  │         │  │         │  │         │    │
│  │ Skills: │  │ Skills: │  │ Skills: │    │
│  │ All     │  │ Coding  │  │ Basic   │    │
│  └─────────┘  └─────────┘  └─────────┘    │
├─────────────────────────────────────────────┤
│           Gateway (Port 18789)              │
└─────────────────────────────────────────────┘
         │                │               │
         ▼                ▼               ▼
    Telegram         Discord      Home Assistant
```

### Key Concepts

**Agent ID:** Unique identifier (e.g., `main`, `codex`, `voice-assistant`)

**Session:** A conversation thread with an agent. Multiple sessions can exist for the same agent.

**Session Key:** Unique identifier for a conversation session (e.g., `main`, `home-assistant-abc123`)

**Model:** The AI model powering the agent (e.g., `anthropic/claude-sonnet-4-5`)

**System Prompt:** Instructions that define the agent's behavior and personality

## Agent Configuration

### Default Agent Configuration

The default `main` agent is configured in `~/.openclaw/openclaw.json`:

```json
{
  "agents": {
    "defaults": {
      "model": {
        "primary": "anthropic/claude-sonnet-4-5"
      },
      "workspace": "/Users/dan/.openclaw/workspace",
      "heartbeat": {
        "every": "2h",
        "model": "sonnet"
      }
    },
    "list": [
      {
        "id": "main",
        "subagents": {
          "allowAgents": ["main", "codex"]
        }
      }
    ]
  }
}
```

### Creating Additional Agents

Add new agents to the `agents.list` array:

```json
{
  "agents": {
    "list": [
      {
        "id": "main",
        "model": "anthropic/claude-sonnet-4-5"
      },
      {
        "id": "voice-assistant",
        "name": "Voice Assistant",
        "model": "anthropic/claude-sonnet-4-5",
        "systemPrompt": "You are a voice assistant for a smart home..."
      },
      {
        "id": "codex",
        "name": "Codex",
        "model": "anthropic/claude-opus-4-5"
      }
    ]
  }
}
```

### Agent Properties

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Unique agent identifier (required) |
| `name` | string | Human-readable name |
| `model` | string | AI model to use |
| `systemPrompt` | string | Custom system prompt |
| `workspace` | string | Agent's working directory |
| `maxConcurrent` | number | Max concurrent requests |
| `subagents.allowAgents` | array | Which agents can spawn sub-agents |

## Session Management

### What is a Session?

A **session** represents a conversation thread with an agent. Each session maintains:
- Conversation history
- Context and memory
- Token usage statistics
- Last active timestamp

### Session Types

**Direct Sessions:**
- Created when you message an agent directly
- One session per communication channel (Telegram, Discord, etc.)
- Session key matches agent ID (e.g., `main`)

**Custom Sessions:**
- Created for specific purposes
- Can be isolated from other conversations
- Custom session keys (e.g., `home-assistant`, `automation-xyz`)

**Spawned Sessions:**
- Background task sessions
- Created by `sessions_spawn`
- Temporary (can be deleted after task completion)

### Configuring Home Assistant Session

In the integration configuration, you specify which session to use:

**Default (main session):**
```yaml
session_key: "main"
```
- With the **Agent** option blank, the integration resolves the gateway's
  default agent and scopes this session automatically
- HA conversations appear in that agent's main OpenClaw session
- Shares context with other platforms (Telegram, Discord)
- Full conversation history available

**Dedicated session:**
```yaml
session_key: "home-assistant"
```
- Isolated conversation thread
- Separate from other OpenClaw interactions
- Clean separation of concerns

**Per-family-member:**
```yaml
session_key: "ha-dan"
session_key: "ha-partner"
```
- Individual conversation threads
- Personalized responses
- Separate memory and context

## Multi-Agent Setup

### Use Cases

Different agents for different purposes:

**1. Default Agent (main)**
- General-purpose assistant
- Full access to all skills
- Used for complex queries
```json
{
  "id": "main",
  "model": "anthropic/claude-sonnet-4-5"
}
```

**2. Voice Assistant Agent**
- Optimized for spoken responses
- Brief, conversational answers
- No formatting, code blocks, or emojis
```json
{
  "id": "voice-assistant",
  "name": "Voice Assistant",
  "model": "anthropic/claude-sonnet-4-5",
  "systemPrompt": "You are a voice assistant. Keep responses brief (1-3 sentences), conversational, and free of emojis or formatting."
}
```

**3. Coding Expert Agent**
- Deep technical knowledge
- Code generation and debugging
- Extended reasoning mode
```json
{
  "id": "codex",
  "name": "Codex",
  "model": "anthropic/claude-opus-4-5",
  "systemPrompt": "You are an expert software engineer..."
}
```

**4. Research Agent**
- Web browsing and research
- Information gathering
- Report generation
```json
{
  "id": "research",
  "name": "Research Assistant",
  "model": "anthropic/claude-opus-4-5",
  "systemPrompt": "You are a research assistant. Search the web, analyze sources, and provide comprehensive reports."
}
```

### Routing Queries to Different Agents

From Home Assistant, you can route to different agents using sessions:

**Option 1: Multiple Integration Entries**
- Add integration multiple times
- Each entry points to different session/agent
- Select appropriate conversation agent in HA

**Option 2: Dynamic Routing (Future)**
- Single integration
- Auto-detect query type
- Route to appropriate agent

## Voice-Optimized Agents

### Why Voice Optimization?

Standard AI responses often include:
- Emojis (🏠 🐙 🔥)
- Markdown formatting (**bold**, *italic*)
- Code blocks and technical output
- Long, detailed explanations
- Lists and bullet points

These don't work well with text-to-speech!

### Creating a Voice Agent

**Step 1: Configure the Agent**

Create a new agent in `openclaw.json`:

```json
{
  "agents": {
    "list": [
      {
        "id": "voice-assistant",
        "name": "Voice Assistant",
        "model": "anthropic/claude-sonnet-4-5",
        "systemPrompt": "You are a voice assistant for a smart home. Keep your responses:\n- Brief and conversational (1-3 sentences when possible)\n- Natural for text-to-speech (avoid bullet points, formatting, code blocks)\n- Free of emojis and special characters\n- Direct and to the point\n\nWhen performing tasks (emails, calendar, etc.), confirm the action briefly rather than explaining in detail.\n\nExamples:\n- Good: \"I've added the meeting to your calendar for Tuesday at 2pm.\"\n- Bad: \"✅ Done! I've added the following to your calendar:\\n- Event: Team Meeting\\n- Date: Tuesday, Jan 28th\\n- Time: 2:00 PM\""
      }
    ]
  }
}
```

**Step 2: Configure Integration**

Set the integration to use the voice-optimized session:

```yaml
session_key: "voice-assistant"
```

**Step 3: Enable Emoji Stripping**

In integration options:
```yaml
strip_emojis: true  # Remove emojis from TTS
tts_max_characters: 500  # Limit spoken response length
```

### Voice Agent Best Practices

**System Prompt Guidelines:**

```
DO:
✓ "The weather is sunny with a high of 75 degrees."
✓ "I've sent the email to John about tomorrow's meeting."
✓ "You have three appointments today."

DON'T:
✗ "The weather today is: ☀️ Sunny..."
✗ "Email sent! 📧\n\nRecipient: John..."
✗ "Here's your schedule:\n• 9am - Meeting\n• 2pm - Lunch..."
```

**Response Length:**
- Quick queries: 1-2 sentences
- Complex queries: 3-5 sentences max
- Long information: "I've found several options. I can email you the details."

**Formatting:**
- No markdown
- No bullet points
- No code blocks
- Natural sentence flow

## Agent Customization

### System Prompts

System prompts define agent behavior. Key sections to include:

**1. Identity & Role**
```
You are a [role] for [context].
```

**2. Response Style**
```
Keep responses:
- [characteristic 1]
- [characteristic 2]
- [characteristic 3]
```

**3. Capabilities**
```
You can:
- [capability 1]
- [capability 2]

You cannot:
- [limitation 1]
- [limitation 2]
```

**4. Context & Memory**
```
Remember that:
- [important context 1]
- [important context 2]
```

### Example: Complete Voice Assistant System Prompt

```
You are a voice assistant for a smart home. Your responses are spoken aloud using text-to-speech.

Response Guidelines:
- Keep responses brief (1-3 sentences when possible)
- Use natural, conversational language
- No emojis, markdown, or special formatting
- No bullet points or numbered lists
- Avoid technical jargon unless specifically asked

Task Confirmation:
When performing actions, confirm briefly:
- Good: "I've added the appointment to your calendar."
- Bad: "Done! Here's what I added: [details]..."

Error Handling:
- Be clear but brief about errors
- Offer simple next steps
- Don't overwhelm with technical details

Examples:
User: "What's the weather?"
You: "It's currently 68 degrees and partly cloudy. The high today is 75."

User: "Add milk to my shopping list"
You: "I've added milk to your shopping list."

User: "What's on my calendar today?"
You: "You have three events today: a team meeting at 9am, lunch with Sarah at noon, and a dentist appointment at 3pm."
```

### Model Selection

Choose models based on use case:

**Fast Models (Sonnet):**
- Quick queries
- Simple tasks
- Home automation
- Typical response: 2-5 seconds

**Powerful Models (Opus):**
- Complex reasoning
- Research and analysis
- Code generation
- Extended thinking mode
- Typical response: 5-15 seconds

**Local Models:**
- Privacy-critical use cases
- Offline operation
- Lower cost
- Variable performance

### Workspace Configuration

Each agent can have its own workspace:

```json
{
  "id": "research",
  "workspace": "/Users/dan/.openclaw/workspaces/research"
}
```

Benefits:
- Isolated file access
- Separate notes/memory
- Organized by purpose
- Security boundaries

## Best Practices

### 1. Agent Separation

**Recommended Setup:**
```json
{
  "agents": {
    "list": [
      {
        "id": "main",
        "model": "anthropic/claude-sonnet-4-5"
      },
      {
        "id": "voice-assistant",
        "model": "anthropic/claude-sonnet-4-5",
        "systemPrompt": "..."
      }
    ]
  }
}
```

Use `main` for Telegram/Discord, `voice-assistant` for Home Assistant.

### 2. Session Organization

**Pattern: Purpose-Based Sessions**
- `main` - General chat
- `home-assistant` - Voice control
- `automation-xyz` - Specific automation
- `family-member-name` - Personal assistant

### 3. Model Strategy

**Cost-Conscious:**
- Use Sonnet for most queries
- Reserve Opus for complex tasks
- Monitor token usage

**Performance-Focused:**
- Use Opus for better quality
- Accept higher cost
- Enable thinking mode

**Privacy-First:**
- Use local models
- Keep data on-device
- Trade performance for privacy

### 4. System Prompt Evolution

Start simple, iterate:

**v1 (Basic):**
```
You are a voice assistant. Keep responses brief.
```

**v2 (Improved):**
```
You are a voice assistant for a smart home.
- Keep responses under 3 sentences
- No emojis or formatting
- Confirm actions briefly
```

**v3 (Refined):**
```
[Comprehensive prompt with examples, edge cases, personality]
```

### 5. Testing & Iteration

**Test Different Scenarios:**
- Simple queries ("What's the weather?")
- Complex requests ("Schedule a meeting and email the team")
- Error cases ("Check my calendar" when calendar unavailable)
- Multi-turn conversations

**Measure Performance:**
- Response time
- Token usage
- User satisfaction
- Error rate

**Iterate Based on Feedback:**
- Adjust prompt based on actual usage
- Add examples for common edge cases
- Refine tone and style

## Advanced Agent Configuration

### Context Pruning

Control conversation memory:

```json
{
  "agents": {
    "defaults": {
      "contextPruning": {
        "mode": "cache-ttl",
        "ttl": "1h"
      }
    }
  }
}
```

**Modes:**
- `cache-ttl`: Prune based on time
- `safeguard`: Keep most recent context
- Custom strategies

### Compaction

Summarize old messages to save tokens:

```json
{
  "agents": {
    "defaults": {
      "compaction": {
        "mode": "safeguard"
      }
    }
  }
}
```

### Concurrency

Limit parallel requests per agent:

```json
{
  "id": "main",
  "maxConcurrent": 4
}
```

### Subagent Delegation

Allow agents to spawn helper agents:

```json
{
  "id": "main",
  "subagents": {
    "allowAgents": ["main", "codex", "research"],
    "maxConcurrent": 8
  }
}
```

## Troubleshooting

### Agent Not Responding

**Check agent status:**
```bash
openclaw status
```

**Verify agent ID:**
```bash
openclaw config get | jq '.agents.list'
```

**Check logs:**
```bash
tail -f ~/.openclaw/logs/gateway.log
```

### Wrong Agent Responding

**Verify session key:**
- Check Home Assistant integration config
- Ensure session key matches agent ID
- Check for typos

### Performance Issues

**Slow responses:**
- Check model configuration (Opus is slower than Sonnet)
- Disable thinking mode for simple queries
- Increase timeout if needed

**High token usage:**
- Enable context pruning
- Use compaction mode
- Shorten system prompts

### Context Issues

**Agent forgetting context:**
- Check context pruning settings
- Verify session key is consistent
- Don't mix sessions for same conversation

**Too much context:**
- Enable aggressive pruning
- Use dedicated sessions for different purposes
- Clear old sessions periodically

## Examples

### Complete Home Assistant Agent Setup

**1. Configure Agent**

Edit `~/.openclaw/openclaw.json`:

```json
{
  "agents": {
    "list": [
      {
        "id": "home-assistant",
        "name": "Home Assistant Voice",
        "model": "anthropic/claude-sonnet-4-5",
        "systemPrompt": "You are a voice assistant for a smart home. Keep responses brief, conversational, and free of formatting or emojis. Confirm actions simply without detailed explanations.",
        "maxConcurrent": 2
      }
    ]
  }
}
```

**2. Restart Gateway**

```bash
openclaw gateway restart
```

**3. Configure Integration**

In Home Assistant:
- Settings → Devices & Services → OpenClaw
- Click "Configure"
- Set `session_key` to `home-assistant`
- Enable `strip_emojis`
- Set `tts_max_characters` to `300`

**4. Test**

Try voice commands:
- "What's the weather?"
- "Check my calendar"
- "Turn on the living room lights"

## Resources

- **OpenClaw Documentation:** https://docs.openclaw.ai/
- **System Prompt Guide:** https://docs.openclaw.ai/guides/system-prompts
- **Agent Configuration:** https://docs.openclaw.ai/config/agents
- **Session Management:** https://docs.openclaw.ai/features/sessions

## Support

- **Integration Issues:** https://github.com/ddrayne/openclaw-homeassistant/issues
- **OpenClaw Discord:** https://discord.com/invite/openclaw
- **Home Assistant Community:** https://community.home-assistant.io/

---

*Last Updated: 2026-01-25*
