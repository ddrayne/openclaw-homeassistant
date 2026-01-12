"""Constants for the Clawd integration."""

DOMAIN = "clawd"

# Configuration defaults
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18789
DEFAULT_USE_SSL = False
DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_SESSION_KEY = "main"  # Default direct-chat session

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_TOKEN = "token"
CONF_USE_SSL = "use_ssl"
CONF_TIMEOUT = "timeout"
CONF_SESSION_KEY = "session_key"

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
CLIENT_DISPLAY_NAME = "Home Assistant Clawd"
CLIENT_VERSION = "1.0.0"
CLIENT_PLATFORM = "python"
CLIENT_MODE = "backend"
