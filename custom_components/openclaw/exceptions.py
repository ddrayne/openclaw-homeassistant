"""Exceptions for the OpenClaw integration."""


class OpenClawError(Exception):
    """Base exception for OpenClaw integration."""


class GatewayConnectionError(OpenClawError):
    """Cannot connect to Gateway."""

class GatewayTLSConfigurationError(GatewayConnectionError):
    """Invalid local TLS certificate or private key configuration."""

class GatewayUpgradeRejectedError(GatewayConnectionError):
    """The WebSocket upgrade was rejected with HTTP 401/403.

    Possibly transient - a restarting reverse proxy can reject a valid token
    for a few seconds - so it is retried; repeated rejections mean the token
    really is wrong.
    """

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class GatewayAuthenticationError(OpenClawError):
    """Authentication failed - invalid token."""


class DevicePairingRequiredError(GatewayAuthenticationError):
    """Device is registered but not yet approved in OpenClaw."""


class GatewayTimeoutError(OpenClawError):
    """Request timeout - Gateway or agent took too long."""


class AgentExecutionError(OpenClawError):
    """Agent execution failed."""


class ProtocolError(OpenClawError):
    """Protocol version mismatch or invalid message."""
