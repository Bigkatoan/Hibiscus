"""Small crypto helpers: sha256 token hashing, AES-256-GCM with the app data key."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def sha256(data: str | bytes) -> bytes:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).digest()


def random_token(nbytes: int = 32) -> str:
    """URL-safe random token (43 chars for 32 bytes)."""
    return secrets.token_urlsafe(nbytes)


def constant_time_eq(a: str | bytes, b: str | bytes) -> bool:
    ab = a.encode() if isinstance(a, str) else a
    bb = b.encode() if isinstance(b, str) else b
    return hmac.compare_digest(ab, bb)


class DataCipher:
    """AES-256-GCM; ciphertext layout ``nonce(12) || ciphertext || tag(16)``. ``aad`` binds context."""

    def __init__(self, key_b64: str) -> None:
        key = base64.b64decode(key_b64)
        if len(key) != 32:
            raise ValueError("data key must be 32 bytes")
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: bytes, aad: bytes = b"") -> bytes:
        nonce = secrets.token_bytes(12)
        return nonce + self._aead.encrypt(nonce, plaintext, aad or None)

    def decrypt(self, blob: bytes, aad: bytes = b"") -> bytes:
        return self._aead.decrypt(blob[:12], blob[12:], aad or None)
