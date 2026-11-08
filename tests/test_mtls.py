"""Isolated mTLS context tests; no HA runtime or production certificates."""

import importlib.util
import ssl
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_BASE = Path(__file__).resolve().parent.parent / "custom_components" / "openclaw"
_PKG = "custom_components.openclaw"


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.modules.setdefault("custom_components", ModuleType("custom_components"))
sys.modules.setdefault(_PKG, ModuleType(_PKG))
_load_module(f"{_PKG}.const", _BASE / "const.py")
_exceptions = _load_module(f"{_PKG}.exceptions", _BASE / "exceptions.py")
_load_module(f"{_PKG}.device_auth", _BASE / "device_auth.py")
_gateway = _load_module(f"{_PKG}.gateway", _BASE / "gateway.py")

GatewayTLSConfigurationError = _exceptions.GatewayTLSConfigurationError
create_ssl_context = _gateway.create_ssl_context
GatewayProtocol = _gateway.GatewayProtocol


def _new_cert_and_key(directory: Path, name: str) -> tuple[Path, Path]:
    """Generate a throwaway self-signed certificate and matching private key."""
    cert = directory / f"{name}.crt"
    key = directory / f"{name}.key"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "1",
            "-subj", f"/CN={name}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return cert, key


def test_default_tls_context_without_client_cert() -> None:
    """Plain server-authenticated TLS remains supported."""
    context = create_ssl_context()
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_valid_client_cert_and_key(tmp_path: Path) -> None:
    """A matching client certificate and key can be loaded."""
    cert, key = _new_cert_and_key(tmp_path, "valid-client")
    context = create_ssl_context(str(cert), str(key))
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


@pytest.mark.parametrize("cert,key", [("client.crt", None), (None, "client.key")])
def test_incomplete_pair_is_rejected(cert: str | None, key: str | None) -> None:
    """mTLS must be supplied as a complete certificate/key pair."""
    with pytest.raises(GatewayTLSConfigurationError):
        create_ssl_context(cert, key)


def test_missing_certificate_file_is_rejected(tmp_path: Path) -> None:
    """A typo in the certificate path raises a configuration error."""
    _, key = _new_cert_and_key(tmp_path, "existing")
    missing_cert = tmp_path / "does-not-exist.crt"
    with pytest.raises(GatewayTLSConfigurationError):
        create_ssl_context(str(missing_cert), str(key))


def test_mismatched_certificate_and_key_are_rejected(tmp_path: Path) -> None:
    """A valid certificate with an unrelated private key must fail."""
    cert_a, _ = _new_cert_and_key(tmp_path, "first")
    _, key_b = _new_cert_and_key(tmp_path, "second")
    with pytest.raises(GatewayTLSConfigurationError):
        create_ssl_context(str(cert_a), str(key_b))


@pytest.mark.asyncio
async def test_gateway_reuses_ssl_context(tmp_path: Path) -> None:
    """WebSocket reconnects reuse the TLS context rather than rebuilding it."""
    cert, key = _new_cert_and_key(tmp_path, "cached")
    gateway = GatewayProtocol(
        "localhost", 18789, None, use_ssl=True,
        client_cert=str(cert), client_key=str(key),
    )
    first = await gateway._async_ssl_context()
    second = await gateway._async_ssl_context()
    assert first is second

@pytest.mark.asyncio
async def test_websocket_ssl_context_loads_client_credentials(monkeypatch):
    """WebSocket context must use the configured mTLS credentials."""
    import ssl
    from unittest.mock import MagicMock

    context = ssl.create_default_context()
    helper = MagicMock(return_value=context)

    monkeypatch.setattr(_gateway, "create_ssl_context", helper)

    protocol = _gateway.GatewayProtocol(
        "localhost",
        18789,
        None,
        use_ssl=True,
        client_cert="/tmp/client.crt",
        client_key="/tmp/client.key",
    )

    result = await protocol._async_ssl_context()

    assert result is context
    helper.assert_called_once_with(
        "/tmp/client.crt",
        "/tmp/client.key",
    )
