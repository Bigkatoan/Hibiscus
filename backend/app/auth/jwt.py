"""EdDSA (Ed25519) access tokens: 15 min, claims ``sub sid mfa iat exp iss aud jti`` (ADR-0006).

Optional ``rid``: id of the refresh-token row issued in the same response. A request carrying it
proves the browser stored that response's cookies, which confirms the rotation (QC-e2e-07).
"""

from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ISSUER = "hibiscus"
AUDIENCE = "hibiscus-api"


class AccessTokenExpiredError(Exception):
    pass


class AccessTokenInvalidError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID  # session family id
    mfa: bool
    issued_at: int
    expires_at: int
    refresh_id: uuid.UUID | None = None  # ``rid``: refresh row issued alongside this token


class JwtService:
    def __init__(self, private_key_pem: str, previous_public_pems: list[str] | None = None, ttl_s: int = 900):
        key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("HIBISCUS_JWT_PRIVATE_KEY must be an Ed25519 private key (PEM)")
        self._private = key
        self._public_keys: list[Ed25519PublicKey] = [key.public_key()]
        for pem in previous_public_pems or []:
            pub = serialization.load_pem_public_key(pem.encode())
            if not isinstance(pub, Ed25519PublicKey):
                raise ValueError("previous JWT public keys must be Ed25519")
            self._public_keys.append(pub)
        self.ttl_s = ttl_s

    def issue(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        mfa: bool,
        *,
        now: int | None = None,
        refresh_id: uuid.UUID | None = None,
    ) -> str:
        iat = int(now if now is not None else time.time())
        payload: dict[str, object] = {
            "sub": str(user_id),
            "sid": str(session_id),
            "mfa": bool(mfa),
            "iat": iat,
            "exp": iat + self.ttl_s,
            "iss": ISSUER,
            "aud": AUDIENCE,
            "jti": secrets.token_hex(8),
        }
        if refresh_id is not None:
            payload["rid"] = str(refresh_id)
        return jwt.encode(payload, self._private, algorithm="EdDSA")

    def decode(self, token: str, *, verify_exp: bool = True) -> AccessClaims:
        last_err: Exception | None = None
        for pub in self._public_keys:
            try:
                data = jwt.decode(
                    token,
                    pub,
                    algorithms=["EdDSA"],
                    audience=AUDIENCE,
                    issuer=ISSUER,
                    options={"require": ["sub", "sid", "exp", "iat", "iss", "aud"], "verify_exp": verify_exp},
                    leeway=5,
                )
                return AccessClaims(
                    user_id=uuid.UUID(str(data["sub"])),
                    session_id=uuid.UUID(str(data["sid"])),
                    mfa=bool(data.get("mfa", False)),
                    issued_at=int(data["iat"]),
                    expires_at=int(data["exp"]),
                    refresh_id=uuid.UUID(str(data["rid"])) if data.get("rid") else None,
                )
            except jwt.ExpiredSignatureError as e:
                raise AccessTokenExpiredError from e
            except (jwt.InvalidTokenError, ValueError) as e:
                last_err = e
        raise AccessTokenInvalidError(str(last_err))
