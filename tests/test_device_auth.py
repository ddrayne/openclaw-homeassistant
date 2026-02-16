"""Tests for Ed25519 device authentication (HA-free)."""

import base64
import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_BASE = Path(__file__).parent.parent / "custom_components" / "openclaw"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.modules.setdefault("custom_components", ModuleType("custom_components"))
sys.modules.setdefault(
    "custom_components.openclaw", ModuleType("custom_components.openclaw")
)

_const = _load_module("custom_components.openclaw.const", _BASE / "const.py")
_exceptions = _load_module(
    "custom_components.openclaw.exceptions", _BASE / "exceptions.py"
)
_device_auth = _load_module(
    "custom_components.openclaw.device_auth", _BASE / "device_auth.py"
)


class TestKeypairGeneration:
    def test_generate_keypair_returns_private_key(self):
        key = _device_auth.generate_keypair()
        assert key is not None

    def test_roundtrip_serialization(self):
        key = _device_auth.generate_keypair()
        raw = _device_auth.private_key_to_bytes(key)
        assert len(raw) == 32
        restored = _device_auth.private_key_from_bytes(raw)
        assert _device_auth.public_key_bytes(restored) == _device_auth.public_key_bytes(key)

    def test_public_key_is_32_bytes(self):
        key = _device_auth.generate_keypair()
        pub = _device_auth.public_key_bytes(key)
        assert len(pub) == 32


class TestDeviceId:
    def test_device_id_is_64_char_hex(self):
        key = _device_auth.generate_keypair()
        pub = _device_auth.public_key_bytes(key)
        device_id = _device_auth.device_id_from_public_key(pub)
        assert len(device_id) == 64
        int(device_id, 16)  # must be valid hex

    def test_device_id_matches_sha256(self):
        key = _device_auth.generate_keypair()
        pub = _device_auth.public_key_bytes(key)
        expected = hashlib.sha256(pub).hexdigest()
        assert _device_auth.device_id_from_public_key(pub) == expected


class TestBase64url:
    def test_no_padding(self):
        result = _device_auth._base64url_encode(b"\x00" * 32)
        assert "=" not in result

    def test_url_safe_chars(self):
        result = _device_auth._base64url_encode(b"\xff" * 32)
        assert "+" not in result
        assert "/" not in result


class TestSignaturePayload:
    def test_format(self):
        payload = _device_auth.build_signature_payload(
            device_id="abc123",
            client_id="gateway-client",
            client_mode="backend",
            role="operator",
            scopes=["operator.read", "operator.write"],
            signed_at_ms=1700000000000,
            token="mytoken",
            nonce="uuid-nonce",
        )
        assert payload == (
            "v2|abc123|gateway-client|backend|operator"
            "|operator.read,operator.write|1700000000000|mytoken|uuid-nonce"
        )

    def test_empty_token(self):
        payload = _device_auth.build_signature_payload(
            device_id="abc",
            client_id="gw",
            client_mode="be",
            role="op",
            scopes=["s1"],
            signed_at_ms=0,
            token="",
            nonce="n",
        )
        parts = payload.split("|")
        assert parts[7] == ""  # token field is empty


class TestBuildDeviceAuthDict:
    def test_contains_required_keys(self):
        key = _device_auth.generate_keypair()
        result = _device_auth.build_device_auth_dict(
            key=key,
            client_id="gateway-client",
            client_mode="backend",
            role="operator",
            scopes=["operator.read", "operator.write"],
            token="tok",
            nonce="test-nonce",
        )
        assert set(result.keys()) == {"id", "publicKey", "signature", "signedAt", "nonce"}
        assert result["nonce"] == "test-nonce"
        assert isinstance(result["signedAt"], int)
        assert len(result["id"]) == 64

    def test_signature_is_base64url(self):
        key = _device_auth.generate_keypair()
        result = _device_auth.build_device_auth_dict(
            key=key,
            client_id="gateway-client",
            client_mode="backend",
            role="operator",
            scopes=["operator.read"],
            token="",
            nonce="n",
        )
        sig = result["signature"]
        assert "=" not in sig
        assert "+" not in sig
        assert "/" not in sig

    def test_signature_verifies(self):
        """Verify the signature can be verified with the public key."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        key = _device_auth.generate_keypair()
        pub_bytes = _device_auth.public_key_bytes(key)
        result = _device_auth.build_device_auth_dict(
            key=key,
            client_id="gateway-client",
            client_mode="backend",
            role="operator",
            scopes=["operator.read", "operator.write"],
            token="tok",
            nonce="test-nonce",
        )
        # Reconstruct payload
        device_id = _device_auth.device_id_from_public_key(pub_bytes)
        payload = _device_auth.build_signature_payload(
            device_id=device_id,
            client_id="gateway-client",
            client_mode="backend",
            role="operator",
            scopes=["operator.read", "operator.write"],
            signed_at_ms=result["signedAt"],
            token="tok",
            nonce="test-nonce",
        )
        # Decode signature (re-add padding for base64)
        sig_b64 = result["signature"]
        padding = 4 - len(sig_b64) % 4
        if padding != 4:
            sig_b64 += "=" * padding
        sig_bytes = base64.urlsafe_b64decode(sig_b64)
        # Verify — raises InvalidSignature if invalid
        pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        pub_key.verify(sig_bytes, payload.encode("utf-8"))
