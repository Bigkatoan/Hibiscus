"""TOTP (RFC 6238 via pyotp, SHA1/6 digits/30 s, ±1 step, replay-protected) and recovery codes."""

from __future__ import annotations

import hmac
import secrets
import string
import time
import uuid
from datetime import UTC, datetime

import pyotp
from pyotp.totp import TOTP
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import PasswordHasher
from app.core.crypto import DataCipher
from app.db.models import RecoveryCode, User

ISSUER = "Hibiscus"
PERIOD = 30
RECOVERY_COUNT = 10
_RC_ALPHABET = string.ascii_lowercase + string.digits


def _aad(user_id: uuid.UUID) -> bytes:
    return b"totp:" + user_id.bytes


def new_secret() -> str:
    return pyotp.random_base32(32)


def encrypt_secret(cipher: DataCipher, user_id: uuid.UUID, secret: str) -> bytes:
    return cipher.encrypt(secret.encode(), _aad(user_id))


def decrypt_secret(cipher: DataCipher, user: User) -> str | None:
    if user.totp_secret_enc is None:
        return None
    return cipher.decrypt(user.totp_secret_enc, _aad(user.id)).decode()


def otpauth_uri(secret: str, email: str) -> str:
    return TOTP(secret, interval=PERIOD).provisioning_uri(name=email, issuer_name=ISSUER)


def match_step(secret: str, code: str, *, now: float | None = None, window: int = 1) -> int | None:
    """Return the matching time step (for replay protection) or None."""
    totp = TOTP(secret, interval=PERIOD)
    t = time.time() if now is None else now
    current = int(t // PERIOD)
    for step in range(current - window, current + window + 1):
        if hmac.compare_digest(totp.at(step * PERIOD), code):
            return step
    return None


def verify_user_code(cipher: DataCipher, user: User, code: str, *, now: float | None = None) -> bool:
    """Verify ``code`` against the user's (pending or active) secret; updates ``totp_last_used_step``."""
    secret = decrypt_secret(cipher, user)
    if secret is None:
        return False
    step = match_step(secret, code, now=now)
    if step is None:
        return False
    if user.totp_last_used_step is not None and step <= user.totp_last_used_step:
        return False  # replayed code
    user.totp_last_used_step = step
    return True


def _new_code() -> str:
    raw = "".join(secrets.choice(_RC_ALPHABET) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"


async def replace_recovery_codes(db: AsyncSession, hasher: PasswordHasher, user_id: uuid.UUID) -> list[str]:
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id))
    codes = [_new_code() for _ in range(RECOVERY_COUNT)]
    for c in codes:
        db.add(RecoveryCode(user_id=user_id, code_hash=hasher.hash(c)))
    await db.flush()
    return codes


async def use_recovery_code(db: AsyncSession, hasher: PasswordHasher, user_id: uuid.UUID, code: str) -> bool:
    rows = (
        (
            await db.execute(
                select(RecoveryCode)
                .where(RecoveryCode.user_id == user_id, RecoveryCode.used_at.is_(None))
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    normalized = code.strip().lower()
    for rc in rows:
        if hasher.verify(rc.code_hash, normalized):
            rc.used_at = datetime.now(UTC)
            await db.flush()
            return True
    return False


async def remaining_recovery_codes(db: AsyncSession, user_id: uuid.UUID) -> int:
    n = (
        await db.execute(
            select(func.count())
            .select_from(RecoveryCode)
            .where(RecoveryCode.user_id == user_id, RecoveryCode.used_at.is_(None))
        )
    ).scalar_one()
    return int(n)


async def clear_mfa(db: AsyncSession, user: User) -> None:
    user.totp_secret_enc = None
    user.totp_enabled_at = None
    user.totp_last_used_step = None
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    await db.flush()
