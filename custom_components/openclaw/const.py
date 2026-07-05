"""Constants for the OpenClaw integration."""

DOMAIN = "openclaw"

# Configuration defaults
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18789
DEFAULT_USE_SSL = False
DEFAULT_TIMEOUT = 300  # seconds
DEFAULT_SESSION_KEY = "main"  # Default direct-chat session
DEFAULT_MODEL = None
DEFAULT_THINKING = None
DEFAULT_STRIP_EMOJIS = True  # Strip emojis from TTS by default
DEFAULT_TTS_MAX_CHARS = 0  # 0 disables TTS trimming
DEFAULT_AGENT_ID = None  # Use gateway default agent

# Proactive voice: speak agent-initiated turns (cron/background/follow-ups) on a
# satellite. Opt-in so existing installs are unaffected.
DEFAULT_PROACTIVE_ENABLED = False
DEFAULT_PROACTIVE_MODE = "announce"
PROACTIVE_MODE_ANNOUNCE = "announce"
PROACTIVE_MODE_START_CONVERSATION = "start_conversation"
# Ignore session-message echoes of the user's own Q&A that land within this many
# seconds of local agent activity (the satellite already spoke those).
PROACTIVE_SUPPRESS_SECONDS = 15.0

# Background work: when a request produces no content within the grace period,
# speak a holding phrase, let the run finish detached, and announce the result
# on the originating satellite (fallback: the proactive satellite).
DEFAULT_BACKGROUND_ENABLED = True
DEFAULT_BACKGROUND_GRACE = 10  # seconds to wait for first content
DEFAULT_HOLDING_PHRASE = "On it — I'll let you know when it's done."
BACKGROUND_ERROR_PHRASE = "Sorry — that request ran into a problem."
BACKGROUND_TIMEOUT_PHRASE = (
    "That's taking longer than expected, so I've stopped waiting for it."
)
# Overall completion budget for a detached run. Deliberately decoupled from
# the (voice-tuned, often short) agent timeout: once deferred, a run only
# needs to finish eventually, not chunk regularly.
BACKGROUND_MAX_SECONDS = 3600.0

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_TOKEN = "token"
CONF_USE_SSL = "use_ssl"
CONF_TIMEOUT = "timeout"
CONF_SESSION_KEY = "session_key"
CONF_AGENT_ID = "agent_id"
CONF_MODEL = "model"
CONF_THINKING = "thinking"
CONF_STRIP_EMOJIS = "strip_emojis"
CONF_TTS_MAX_CHARS = "tts_max_chars"
CONF_PROACTIVE_ENABLED = "proactive_enabled"
CONF_PROACTIVE_SATELLITE = "proactive_satellite"
CONF_PROACTIVE_MODE = "proactive_mode"
CONF_BACKGROUND_ENABLED = "background_enabled"
CONF_BACKGROUND_GRACE = "background_grace"
CONF_HOLDING_PHRASE = "holding_phrase"
# Connection states
STATE_CONNECTED = "connected"
STATE_DISCONNECTED = "disconnected"
STATE_CONNECTING = "connecting"
STATE_ERROR = "error"

# Gateway protocol
# Advertise a range: keep min at 3 for backward compatibility with older
# gateways while supporting v4, which OpenClaw 2026.6+ requires (the gateway
# rejects clients whose maxProtocol < 4 with PROTOCOL_MISMATCH). The connect
# handshake and the "agent" RPC params this integration uses are unchanged
# between v3 and v4.
PROTOCOL_MIN_VERSION = 3
PROTOCOL_MAX_VERSION = 4

# Client identification
CLIENT_ID = "gateway-client"
CLIENT_DISPLAY_NAME = "Home Assistant OpenClaw"
CLIENT_VERSION = "1.0.0"
CLIENT_PLATFORM = "python"
CLIENT_MODE = "backend"

# Device authentication (OpenClaw 2026.2.13+)
DEVICE_ROLE = "operator"
DEVICE_SCOPES = ["operator.read", "operator.write"]
CHALLENGE_TIMEOUT = 2.0  # seconds to wait for connect.challenge before fallback
