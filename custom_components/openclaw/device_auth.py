"""Ed25519 device authentication for OpenClaw Gateway (2026.2.13+)."""

import base64
import hashlib
import logging
import time
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "openclaw.device_auth"
STORAGE_VERSION = 1


def generate_keypair() -> Ed25519PrivateKey:
    """Generate a new Ed25519 keypair."""
    return Ed25519PrivateKey.generate()


def private_key_to_bytes(key: Ed25519PrivateKey) -> bytes:
    """Serialize private key to raw 32-byte form."""
    return key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def private_key_from_bytes(data: bytes) -> Ed25519PrivateKey:
    """Deserialize private key from raw 32-byte form."""
    return Ed25519PrivateKey.from_private_bytes(data)


def public_key_bytes(key: Ed25519PrivateKey) -> bytes:
    """Get raw 32-byte public key from private key."""
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _base64url_encode(data: bytes) -> str:
    """Base64url encode without padding (matching OpenClaw format)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def device_id_from_public_key(pub_bytes: bytes) -> str:
    """Derive device ID: hex-encoded SHA-256 of the public key."""
    return hashlib.sha256(pub_bytes).hexdigest()


def build_signature_payload(
    device_id: str,
    client_id: str,
    client_mode: str,
    role: str,
    scopes: list[str],
    signed_at_ms: int,
    token: str,
    nonce: str,
) -> str:
    """Build the v2 pipe-delimited signature payload string."""
    scopes_csv = ",".join(scopes)
    return (
        f"v2|{device_id}|{client_id}|{client_mode}|{role}"
        f"|{scopes_csv}|{signed_at_ms}|{token}|{nonce}"
    )


def sign_payload(key: Ed25519PrivateKey, payload: str) -> str:
    """Sign a payload string and return base64url-encoded signature."""
    signature_bytes = key.sign(payload.encode("utf-8"))
    return _base64url_encode(signature_bytes)


def build_device_auth_dict(
    key: Ed25519PrivateKey,
    client_id: str,
    client_mode: str,
    role: str,
    scopes: list[str],
    token: str,
    nonce: str,
) -> dict[str, Any]:
    """Build the complete device auth dict for the connect request.

    Returns dict with keys: id, publicKey, signature, signedAt, nonce.
    """
    pub_bytes = public_key_bytes(key)
    device_id = device_id_from_public_key(pub_bytes)
    signed_at_ms = int(time.time() * 1000)

    payload = build_signature_payload(
        device_id=device_id,
        client_id=client_id,
        client_mode=client_mode,
        role=role,
        scopes=scopes,
        signed_at_ms=signed_at_ms,
        token=token,
        nonce=nonce,
    )

    signature = sign_payload(key, payload)
    public_key_b64 = _base64url_encode(pub_bytes)

    return {
        "id": device_id,
        "publicKey": public_key_b64,
        "signature": signature,
        "signedAt": signed_at_ms,
        "nonce": nonce,
    }


async def async_load_or_create_keypair(hass) -> Ed25519PrivateKey:
    """Load persisted Ed25519 keypair or generate and save a new one."""
    from homeassistant.helpers.storage import Store

    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    data = await store.async_load()

    if data and "private_key_hex" in data:
        try:
            raw = bytes.fromhex(data["private_key_hex"])
            key = private_key_from_bytes(raw)
            _LOGGER.debug("Loaded existing device keypair")
            return key
        except Exception:  # pylint: disable=broad-except
            _LOGGER.warning(
                "Failed to load stored keypair, generating new one"
            )

    key = generate_keypair()
    raw = private_key_to_bytes(key)
    await store.async_save({"private_key_hex": raw.hex()})
    _LOGGER.info("Generated and saved new device keypair")
    return key
