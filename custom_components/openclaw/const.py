"""Constants for the OpenClaw integration."""

DOMAIN = "openclaw"

# Configuration defaults
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18789
DEFAULT_USE_SSL = False
DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_SESSION_KEY = "main"  # Default direct-chat session
DEFAULT_MODEL = None
DEFAULT_THINKING = None
DEFAULT_STRIP_EMOJIS = True  # Strip emojis from TTS by default
DEFAULT_TTS_MAX_CHARS = 0  # 0 disables TTS trimming

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_TOKEN = "token"
CONF_USE_SSL = "use_ssl"
CONF_TIMEOUT = "timeout"
CONF_SESSION_KEY = "session_key"
CONF_MODEL = "model"
CONF_THINKING = "thinking"
CONF_STRIP_EMOJIS = "strip_emojis"
CONF_TTS_MAX_CHARS = "tts_max_chars"
# Connection states
STATE_CONNECTED = "connected"
STATE_DISCONNECTED = "disconnected"
STATE_CONNECTING = "connecting"
STATE_ERROR = "error"

# Gateway protocol
PROTOCOL_MIN_VERSION = 3
PROTOCOL_MAX_VERSION = 3

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
