# OpenClaw Voice Assistant for Home Assistant

[![Tests](https://github.com/ddrayne/openclaw-homeassistant/actions/workflows/tests.yml/badge.svg)](https://github.com/ddrayne/openclaw-homeassistant/actions/workflows/tests.yml)

<p align="center">
  <img src="custom_components/openclaw/icon.png" alt="OpenClaw Icon" width="128" height="128">
</p>

Integrate [OpenClaw](https://openclaw.ai/) with Home Assistant's voice control system, bringing your personal AI agent to your smart home.

**OpenClaw** is an open-source AI agent system that runs locally on your machine. It can browse the web, manage emails and calendar, access files, execute commands, and integrate with 50+ services like Gmail, GitHub, Spotify, and Obsidian. Works with Claude, GPT, or local AI models.

This integration lets you access your **entire OpenClaw agent** - with all its skills, integrations, memory, and capabilities - through Home Assistant's voice interface and Assist. Whatever your OpenClaw can do in WhatsApp, Telegram, or Discord, it can now do through your smart home voice assistant.

## Features

### OpenClaw Agent Capabilities
- **Full Agent Access**: Complete access to your OpenClaw agent with all configured skills and integrations
- **System Integration**: Browse web, manage files, execute commands - everything your OpenClaw can do
- **Service Integrations**: Access Gmail, Calendar, GitHub, Spotify, Obsidian, and 50+ other services
- **Persistent Memory**: Your OpenClaw's memory and context carry over to voice interactions
- **Custom Skills**: Use any custom skills or plugins you've installed in OpenClaw
- **Multi-Model Support**: Works with whatever AI model you've configured (Claude, GPT, local models)

### Integration Features
- **Direct WebSocket Connection**: Real-time, persistent connection to OpenClaw Gateway
- **Smart TTS Processing**: Configurable emoji stripping for clean text-to-speech output
- **Voice-Friendly Limits**: Optional TTS response trimming to keep speech concise
- **Flexible Authentication**: Secure token-based auth with SSL/TLS support
- **Reliable Connection**: Keepalive pings, automatic reconnects, and graceful error handling
- **Customizable Sessions**: Session selector in setup plus `openclaw.set_session` for fast switching
- **Model & Thinking Overrides**: Per-request model and reasoning mode controls
- **Streaming Responses**: Stream output when Home Assistant supports streaming conversation results
- **Diagnostic Sensors**: Gateway uptime, connected clients, and health status sensors
- **Fast Responses**: Typical response time of 5-10 seconds for most queries
- **Easy Configuration**: Simple UI-based setup through Home Assistant
- **Diagnostics Support**: Built-in diagnostics for troubleshooting

## Documentation

📚 **Additional Guides:**

- **[Roadmap & Enhancement Plan](ROADMAP.md)** - Planned features, optimizations, and development priorities
- **[Gateway API Documentation](GATEWAY_API.md)** - Comprehensive OpenClaw Gateway API reference for developers
- **[Agent Configuration Guide](AGENTS.md)** - Understanding and configuring OpenClaw agents for optimal voice assistant performance

## Requirements

- Home Assistant 2024.1.0 or later
- A configured [OpenClaw](https://openclaw.ai/) installation with Gateway running (local or remote)
- Gateway token (for non-localhost connections)

**Note**: OpenClaw runs on macOS, Windows, and Linux. You'll need to have OpenClaw installed and configured with your desired AI model (Claude, GPT, or local) and any service integrations you want to use before connecting to Home Assistant.

## Upgrading from Clawd v1.2.x to OpenClaw v1.3.0

Clawd has been renamed to **OpenClaw** (via MoltBot). This integration now uses the `openclaw` domain. This is a breaking change that requires a clean reinstall — there is no automatic migration path.

### Step-by-step upgrade

1. **Remove the old integration**
   - Go to **Settings > Devices & Services**
   - Find "Clawd" and click the three dots > **Delete**
   - Note down your host, port, and token before deleting

2. **Remove old files from HACS**
   - Open **HACS > Integrations**
   - Find "Clawd Voice Assistant" and **remove** it (uninstall + remove from custom repositories)

3. **Delete the old `clawd` directory** (important!)
   - Using SSH, the File Editor add-on, or Samba, **manually delete** the `custom_components/clawd/` directory
   - HACS does **not** remove this automatically because the repository name changed
   - If you skip this step, Home Assistant will load both the old `clawd` and new `openclaw` integrations, causing errors in the log

4. **Restart Home Assistant**

5. **Install OpenClaw**
   - Open **HACS > Integrations > three dots > Custom repositories**
   - Add `ddrayne/openclaw-homeassistant` as an "Integration"
   - Download "OpenClaw Voice Assistant"
   - Restart Home Assistant

6. **Re-add the integration**
   - Go to **Settings > Devices & Services > Add Integration**
   - Search for "OpenClaw Voice Assistant"
   - Enter your Gateway connection details (same host, port, and token as before)

7. **Update automations and dashboards**
   - Any automations, scripts, or dashboard cards referencing old entity IDs (e.g. `sensor.clawd_*`, `binary_sensor.clawd_*`, `conversation.clawd`) need to be updated to use the new `openclaw` entity IDs

Your Gateway token and connection settings are unchanged — only the Home Assistant side needs to be reinstalled.

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL and select "Integration" as the category
6. Click "Add"
7. Search for "OpenClaw Voice Assistant"
8. Click "Download"
9. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/openclaw` directory to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Getting a Gateway Token

A Gateway token is required when connecting to OpenClaw from a different machine (non-localhost). The token authenticates your Home Assistant instance with the Gateway.

**Generate a new token:**

```bash
openclaw doctor --generate-gateway-token
```

This will output a token like `666c291bc8427a2dfb9e16e8871f2eec59f3e2ffee202a5f`. Copy this value for use in the integration configuration.

**Using an existing token:**

If you've already set a token via environment variable, you can retrieve it:

```bash
echo $OPENCLAW_GATEWAY_TOKEN
```

**Starting the Gateway for remote access:**

By default, the Gateway only listens on localhost. To allow connections from Home Assistant on a different machine:

```bash
openclaw gateway --bind lan
```

This binds the Gateway to your local network interface, allowing connections from other devices on your network.

**Security note**: Always use SSL/TLS for remote connections, or use an SSH tunnel. The token should be kept secret as it provides full access to your OpenClaw agent.

## Configuration

### Setting Up the Integration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "OpenClaw Voice Assistant"
4. Enter your Gateway connection details:
   - **Host**: Gateway hostname or IP address (e.g., `gateway.example.com` or `192.168.1.100`)
   - **Port**: Gateway port (default: `18789`)
   - **Gateway Token**: Your authentication token (leave empty for localhost without authentication)
   - **Use SSL**: Check this for `wss://` connections (recommended for remote connections)
   - **Agent Timeout**: Maximum time to wait for agent response in seconds (default: 30)
   - **Session Key**: OpenClaw session to use (default: `main` - the standard direct-chat session)
   - **Strip emojis from TTS speech**: Remove emojis from spoken responses (default: enabled)

5. Click **Submit**

### Configuring Voice Assistant

1. Go to **Settings** → **Voice Assistants** → **Assist**
2. Select your preferred voice assistant
3. Under **Conversation agent**, select **OpenClaw**
4. Save changes

## Usage

Once configured, your Home Assistant voice assistant connects directly to your OpenClaw agent:

- **Voice Commands**: Use any Home Assistant voice interface (mobile app, voice satellites, etc.)
- **Assist Interface**: Type or speak to your OpenClaw through the Home Assistant UI
- **Full Agent Access**: Your OpenClaw can check emails, manage calendar, access files, browse web, and use all configured integrations
- **Natural Conversations**: Multi-turn conversations with persistent memory and context
- **Secure Communication**: All requests sent securely to your OpenClaw Gateway's agent endpoint

### Example Interactions

Your OpenClaw can handle a wide variety of requests through Home Assistant voice interface:

**Email & Communication:**
- "Do I have any important emails from [person]?"
- "Send an email to [person] about tomorrow's meeting"
- "What messages are in my inbox?"
- "Who sent me a telegram message?"

**Calendar & Scheduling:**
- "What's on my calendar today?"
- "When is my next meeting?"
- "Add a dentist appointment for next Tuesday at 2pm"
- "Check me in for my flight tomorrow"

**Information & Web:**
- "Search for restaurants near me"
- "What's the weather forecast for this week?"
- "Look up the latest news about [topic]"
- "Browse to [website] and summarize the main article"

**Files & Documents:**
- "Find my notes about [topic]"
- "What's in my [filename] file?"
- "Save this to my notes: [content]"

**Conversational & Knowledge:**
- "Who are you?"
- "Explain how photosynthesis works"
- "What's 2 plus 2?"
- "Tell me a joke"

**Custom Skills:**
- Any custom skills or integrations you've configured in OpenClaw

**Note**: The exact capabilities depend on your OpenClaw configuration, installed skills, and service integrations. For basic home automation commands like "turn on the lights", you may want to use Home Assistant's built-in intents alongside OpenClaw for the best experience.

## Remote Gateway Setup

If your OpenClaw Gateway is running on a different machine, you have two options:

### Option 1: Direct Connection (Recommended with SSL)

Configure the integration with your Gateway's hostname/IP and enable SSL:
- Host: `gateway.example.com` or IP address
- Port: `18789`
- Use SSL: ✓ (enabled)
- Gateway Token: Required

### Option 2: SSH Tunnel

Set up an SSH tunnel separately and connect via localhost:

```bash
# Set up SSH tunnel (run this command on your Home Assistant machine)
ssh -N -L 18789:localhost:18789 user@gateway-host
```

Then configure the integration:
- Host: `127.0.0.1`
- Port: `18789`
- Gateway Token: (Optional)

## Troubleshooting

### Connection Errors

**Cannot reach OpenClaw Gateway:**
- Check that the Gateway is running: `openclaw status`
- Verify the host and port are correct
- Check firewall rules
- For remote connections, ensure SSL is enabled if required

**Authentication failed:**
- Verify your token is correct
- Check Gateway token configuration: `echo $OPENCLAW_GATEWAY_TOKEN`
- For localhost connections without a token, leave the token field empty

**Response timeout:**
- Agent execution is taking longer than the configured timeout (default: 30 seconds)
- Typical response time is 5-10 seconds for most queries
- Complex questions may take longer (up to 30+ seconds)
- Increase the timeout setting in integration options if needed
- Check Gateway logs for issues

### Diagnostics

Home Assistant provides a diagnostics panel for the integration:

- Go to **Settings** → **Devices & Services** → **OpenClaw** → **Diagnostics**
- Includes connection status, health info, and redacted configuration

### Performance Issues

**Slow responses:**
- Most queries respond in 5-10 seconds
- Complex reasoning or long responses may take 15-30+ seconds
- This is normal for AI agent processing
- Consider increasing the timeout for complex queries

**Connection drops:**
- Check network stability
- The integration will automatically reconnect
- Check Gateway logs for any issues

## Limitations

- **Response time**: Typical queries take 5-10 seconds. Agent tasks (emails, web browsing, file access) may take longer depending on complexity. This is slower than traditional rule-based voice assistants (1-2 seconds) but provides significantly more capability
- **Streaming**: Streams partial responses when Home Assistant supports streaming; older versions fall back to buffered responses
- **Home Automation**: Best used alongside Home Assistant's native intents for device control. Your OpenClaw excels at information, complex tasks, email/calendar management, and agentic workflows rather than simple "turn on the lights" commands
- **Context**: Conversation history within Home Assistant is managed by ChatLog. Your OpenClaw's persistent memory across all platforms remains intact
- **Capabilities**: What your voice assistant can do depends entirely on your OpenClaw configuration, installed skills, and service integrations

## Security

- **Token storage**: Tokens are encrypted at rest by Home Assistant
- **SSL/TLS**: Recommended for all remote connections
- **SSH tunnels**: Can be used as an alternative to direct connections
- **Non-SSL warning**: The integration warns when connecting to non-localhost without SSL

## Advanced Configuration

### Updating Settings

You can update the Gateway connection settings without removing the integration:

1. Go to **Settings** → **Devices & Services**
2. Find the **OpenClaw Voice Assistant** integration
3. Click **Configure**
4. Update settings as needed
5. Click **Submit**

### Reconnect Service

If the Gateway connection gets stuck, you can force a reconnect:

- Service: `openclaw.reconnect`
- Optional field: `entry_id` (reconnect a specific entry; omit to reconnect all)

### Session Keys

The **Session Key** setting allows you to route Home Assistant conversations to specific OpenClaw sessions:

- **Default (`main`)**: The standard direct-chat session - conversations appear in your main OpenClaw session
- **Custom sessions**: Use a different session key to organize Home Assistant conversations separately
- **Use cases**:
  - Keep Home Assistant conversations isolated from other OpenClaw interactions
  - Route to different agents if you have multiple configured
  - Organize conversations by purpose (e.g., `home-assistant`, `automation`, etc.)

To use a custom session, simply enter the desired session key in the integration configuration.

You can also switch sessions dynamically with the `openclaw.set_session` service:

```yaml
service: openclaw.set_session
data:
  session_key: "voice-assistant"
```

This updates the active session for new requests until the integration reloads or is reconfigured.

### Voice-Optimized Session Configuration

For the best voice assistant experience, you can configure a dedicated OpenClaw session with a system prompt optimized for spoken responses. This keeps responses brief and TTS-friendly.

**Step 1: Create a voice-optimized session in OpenClaw**

In your OpenClaw configuration, create a new session with a system prompt like:

```
You are a voice assistant for a smart home. Keep your responses:
- Brief and conversational (1-3 sentences when possible)
- Natural for text-to-speech (avoid bullet points, formatting, code blocks)
- Free of emojis and special characters
- Direct and to the point

When performing tasks (emails, calendar, etc.), confirm the action briefly rather than explaining in detail.
```

Refer to the [OpenClaw documentation](https://docs.openclaw.ai/) for details on configuring custom sessions and system prompts.

**Step 2: Use the session in Home Assistant**

1. Go to **Settings** → **Devices & Services** → **OpenClaw** → **Configure**
2. Set the **Session Key** to your voice-optimized session name (e.g., `voice-assistant`)
3. Click **Submit**

Now all voice commands through Home Assistant will use your voice-optimized configuration, while other OpenClaw interfaces (Telegram, Discord, etc.) continue using their own settings.

### Emoji Stripping

The **Strip emojis from TTS speech** option controls whether emojis are removed from spoken responses:

- **Enabled (default)**: Emojis are removed from text-to-speech output for cleaner speech
  - Example: "I'm Claude 🦞" → Speaks "I'm Claude"
  - Emojis remain visible in the conversation history
- **Disabled**: TTS attempts to read emojis (may sound awkward depending on your TTS engine)
  - Example: "I'm Claude 🦞" → Speaks "I'm Claude lobster emoji"

**When to disable:**
- You have a high-quality TTS engine that handles emojis well
- You prefer emoji descriptions to be spoken
- You're using the integration primarily through text (Assist interface) rather than voice

You can change this setting anytime in **Settings** → **Devices & Services** → **OpenClaw** → **Configure**.

### TTS Response Trimming

The **TTS max characters** option caps spoken responses for long replies:

- **0 (default)**: No limit
- **> 0**: Trim TTS to the specified character count (adds "..." when trimmed)

### Multiple Gateways

You can add multiple Gateway connections if needed:
- Each Gateway requires a unique host:port combination
- Configure multiple conversation entities
- Select different agents in different voice assistant configurations

## License

Apache License 2.0 - See LICENSE file for details

## Credits

- **OpenClaw**: Open-source AI agent system by Anthropic - [openclaw.ai](https://openclaw.ai/)
- **Integration**: Home Assistant conversation entity integration for OpenClaw Gateway

## Support

- **Integration Issues**: [GitHub Issues](https://github.com/ddrayne/openclaw-homeassistant/issues)
- **OpenClaw Website**: [https://openclaw.ai/](https://openclaw.ai/)
- **OpenClaw Documentation**: [https://docs.openclaw.ai/](https://docs.openclaw.ai/)
- **Home Assistant Community**: [https://community.home-assistant.io/](https://community.home-assistant.io/)
