"""Opaque, HMAC-signed cursors: ``base64url(json) "." base64url(hmac_sha256[:16])``.

``encode_cursor(dict) -> str`` / ``decode_cursor(str) -> dict``. A tampered or malformed cursor
raises ``ProblemError(400, bad_request)``. The key comes from ``HIBISCUS_CURSOR_SECRET``.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from typing import Any

from app.core.errors import ErrorCode, ProblemError
from app.core.settings import get_settings

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
_key_override: bytes | None = None


def set_cursor_key(key: str | bytes) -> None:
    """Called by the app factory so cursors use that app's settings."""
    global _key_override
    _key_override = key.encode() if isinstance(key, str) else key


def _key() -> bytes:
    return _key_override or get_settings().cursor_secret.encode()


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def encode_cursor(data: dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":"), sort_keys=True, default=str).encode()
    sig = hmac.new(_key(), payload, hashlib.sha256).digest()[:16]
    return f"{_b64e(payload)}.{_b64e(sig)}"


def decode_cursor(cursor: str) -> dict[str, Any]:
    try:
        p, s = cursor.split(".", 1)
        payload, sig = _b64d(p), _b64d(s)
    except (ValueError, binascii.Error) as e:
        raise ProblemError(400, ErrorCode.BAD_REQUEST, "Invalid cursor") from e
    expected = hmac.new(_key(), payload, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(sig, expected):
        raise ProblemError(400, ErrorCode.BAD_REQUEST, "Invalid cursor")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ProblemError(400, ErrorCode.BAD_REQUEST, "Invalid cursor")
    return data
