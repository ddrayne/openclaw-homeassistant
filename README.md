# Clawd Voice Assistant for Home Assistant

<p align="center">
  <img src="custom_components/clawd/icon.png" alt="Clawd Icon" width="128" height="128">
</p>

Integrate [Clawdbot](https://clawd.bot/) with Home Assistant's voice control system, bringing your personal AI agent to your smart home.

**Clawdbot** is an open-source AI agent system that runs locally on your machine. It can browse the web, manage emails and calendar, access files, execute commands, and integrate with 50+ services like Gmail, GitHub, Spotify, and Obsidian. Works with Claude, GPT, or local AI models.

This integration lets you access your **entire Clawdbot agent** - with all its skills, integrations, memory, and capabilities - through Home Assistant's voice interface and Assist. Whatever your Clawdbot can do in WhatsApp, Telegram, or Discord, it can now do through your smart home voice assistant.

## Features

### Clawdbot Agent Capabilities
- **Full Agent Access**: Complete access to your Clawdbot agent with all configured skills and integrations
- **System Integration**: Browse web, manage files, execute commands - everything your Clawdbot can do
- **Service Integrations**: Access Gmail, Calendar, GitHub, Spotify, Obsidian, and 50+ other services
- **Persistent Memory**: Your Clawdbot's memory and context carry over to voice interactions
- **Custom Skills**: Use any custom skills or plugins you've installed in Clawdbot
- **Multi-Model Support**: Works with whatever AI model you've configured (Claude, GPT, local models)

### Integration Features
- **Direct WebSocket Connection**: Real-time connection to Clawdbot Gateway
- **Smart TTS Processing**: Configurable emoji stripping for clean text-to-speech output
- **Flexible Authentication**: Secure token-based auth with SSL/TLS support
- **Reliable Connection**: Automatic reconnection with graceful error handling
- **Customizable Sessions**: Route conversations to different Clawdbot sessions
- **Fast Responses**: Typical response time of 5-10 seconds for most queries
- **Easy Configuration**: Simple UI-based setup through Home Assistant

## Requirements

- Home Assistant 2024.1.0 or later
- A configured [Clawdbot](https://clawd.bot/) installation with Gateway running (local or remote)
- Gateway token (for non-localhost connections)

**Note**: Clawdbot runs on macOS, Windows, and Linux. You'll need to have Clawdbot installed and configured with your desired AI model (Claude, GPT, or local) and any service integrations you want to use before connecting to Home Assistant.

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL and select "Integration" as the category
6. Click "Add"
7. Search for "Clawd Voice Assistant"
8. Click "Download"
9. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/clawd` directory to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Getting a Gateway Token

A Gateway token is required when connecting to Clawdbot from a different machine (non-localhost). The token authenticates your Home Assistant instance with the Gateway.

**Generate a new token:**

```bash
clawdbot doctor --generate-gateway-token
```

This will output a token like `666c291bc8427a2dfb9e16e8871f2eec59f3e2ffee202a5f`. Copy this value for use in the integration configuration.

**Using an existing token:**

If you've already set a token via environment variable, you can retrieve it:

```bash
echo $CLAWDBOT_GATEWAY_TOKEN
```

**Starting the Gateway for remote access:**

By default, the Gateway only listens on localhost. To allow connections from Home Assistant on a different machine:

```bash
clawdbot gateway --bind lan
```

This binds the Gateway to your local network interface, allowing connections from other devices on your network.

**Security note**: Always use SSL/TLS for remote connections, or use an SSH tunnel. The token should be kept secret as it provides full access to your Clawdbot agent.

## Configuration

### Setting Up the Integration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Clawd Voice Assistant"
4. Enter your Gateway connection details:
   - **Host**: Gateway hostname or IP address (e.g., `gateway.example.com` or `192.168.1.100`)
   - **Port**: Gateway port (default: `18789`)
   - **Gateway Token**: Your authentication token (leave empty for localhost without authentication)
   - **Use SSL**: Check this for `wss://` connections (recommended for remote connections)
   - **Agent Timeout**: Maximum time to wait for agent response in seconds (default: 30)
   - **Session Key**: Clawdbot session to use (default: `main` - the standard direct-chat session)
   - **Strip emojis from TTS speech**: Remove emojis from spoken responses (default: enabled)

5. Click **Submit**

### Configuring Voice Assistant

1. Go to **Settings** → **Voice Assistants** → **Assist**
2. Select your preferred voice assistant
3. Under **Conversation agent**, select **Clawd**
4. Save changes

## Usage

Once configured, your Home Assistant voice assistant connects directly to your Clawdbot agent:

- **Voice Commands**: Use any Home Assistant voice interface (mobile app, voice satellites, etc.)
- **Assist Interface**: Type or speak to your Clawdbot through the Home Assistant UI
- **Full Agent Access**: Your Clawdbot can check emails, manage calendar, access files, browse web, and use all configured integrations
- **Natural Conversations**: Multi-turn conversations with persistent memory and context
- **Secure Communication**: All requests sent securely to your Clawdbot Gateway's agent endpoint

### Example Interactions

Your Clawdbot can handle a wide variety of requests through Home Assistant voice interface:

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
- Any custom skills or integrations you've configured in Clawdbot

**Note**: The exact capabilities depend on your Clawdbot configuration, installed skills, and service integrations. For basic home automation commands like "turn on the lights", you may want to use Home Assistant's built-in intents alongside Clawdbot for the best experience.

## Remote Gateway Setup

If your Clawdbot Gateway is running on a different machine, you have two options:

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

**Cannot reach Clawd Gateway:**
- Check that the Gateway is running: `clawdbot status`
- Verify the host and port are correct
- Check firewall rules
- For remote connections, ensure SSL is enabled if required

**Authentication failed:**
- Verify your token is correct
- Check Gateway token configuration: `echo $CLAWDBOT_GATEWAY_TOKEN`
- For localhost connections without a token, leave the token field empty

**Response timeout:**
- Agent execution is taking longer than the configured timeout (default: 30 seconds)
- Typical response time is 5-10 seconds for most queries
- Complex questions may take longer (up to 30+ seconds)
- Increase the timeout setting in integration options if needed
- Check Gateway logs for issues

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
- **Streaming**: Responses are buffered and returned complete (no streaming TTS support during generation)
- **Home Automation**: Best used alongside Home Assistant's native intents for device control. Your Clawdbot excels at information, complex tasks, email/calendar management, and agentic workflows rather than simple "turn on the lights" commands
- **Context**: Conversation history within Home Assistant is managed by ChatLog. Your Clawdbot's persistent memory across all platforms remains intact
- **Capabilities**: What your voice assistant can do depends entirely on your Clawdbot configuration, installed skills, and service integrations

## Security

- **Token storage**: Tokens are encrypted at rest by Home Assistant
- **SSL/TLS**: Recommended for all remote connections
- **SSH tunnels**: Can be used as an alternative to direct connections
- **Non-SSL warning**: The integration warns when connecting to non-localhost without SSL

## Advanced Configuration

### Updating Settings

You can update the Gateway connection settings without removing the integration:

1. Go to **Settings** → **Devices & Services**
2. Find the **Clawd Voice Assistant** integration
3. Click **Configure**
4. Update settings as needed
5. Click **Submit**

### Session Keys

The **Session Key** setting allows you to route Home Assistant conversations to specific Clawdbot sessions:

- **Default (`main`)**: The standard direct-chat session - conversations appear in your main Clawdbot session
- **Custom sessions**: Use a different session key to organize Home Assistant conversations separately
- **Use cases**:
  - Keep Home Assistant conversations isolated from other Clawdbot interactions
  - Route to different agents if you have multiple configured
  - Organize conversations by purpose (e.g., `home-assistant`, `automation`, etc.)

To use a custom session, simply enter the desired session key in the integration configuration.

### Voice-Optimized Session Configuration

For the best voice assistant experience, you can configure a dedicated Clawdbot session with a system prompt optimized for spoken responses. This keeps responses brief and TTS-friendly.

**Step 1: Create a voice-optimized session in Clawdbot**

In your Clawdbot configuration, create a new session with a system prompt like:

```
You are a voice assistant for a smart home. Keep your responses:
- Brief and conversational (1-3 sentences when possible)
- Natural for text-to-speech (avoid bullet points, formatting, code blocks)
- Free of emojis and special characters
- Direct and to the point

When performing tasks (emails, calendar, etc.), confirm the action briefly rather than explaining in detail.
```

Refer to the [Clawdbot documentation](https://docs.clawd.bot/) for details on configuring custom sessions and system prompts.

**Step 2: Use the session in Home Assistant**

1. Go to **Settings** → **Devices & Services** → **Clawd** → **Configure**
2. Set the **Session Key** to your voice-optimized session name (e.g., `voice-assistant`)
3. Click **Submit**

Now all voice commands through Home Assistant will use your voice-optimized configuration, while other Clawdbot interfaces (Telegram, Discord, etc.) continue using their own settings.

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

You can change this setting anytime in **Settings** → **Devices & Services** → **Clawd** → **Configure**.

### Multiple Gateways

You can add multiple Gateway connections if needed:
- Each Gateway requires a unique host:port combination
- Configure multiple conversation entities
- Select different agents in different voice assistant configurations

## License

Apache License 2.0 - See LICENSE file for details

## Credits

- **Clawdbot**: Open-source AI agent system by Anthropic - [clawd.bot](https://clawd.bot/)
- **Integration**: Home Assistant conversation entity integration for Clawdbot Gateway

## Support

- **Integration Issues**: [GitHub Issues](https://github.com/ddrayne/clawd-homeassistant/issues)
- **Clawdbot Website**: [https://clawd.bot/](https://clawd.bot/)
- **Clawdbot Documentation**: [https://docs.clawd.bot/](https://docs.clawd.bot/)
- **Home Assistant Community**: [https://community.home-assistant.io/](https://community.home-assistant.io/)
