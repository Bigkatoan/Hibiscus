"""Single-use hashed tokens (email verify 24 h, password reset 30 min, MFA challenge 5 min)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import random_token, sha256
from app.db.models import OneTimeToken, OneTimeTokenPurpose


async def issue(
    db: AsyncSession,
    user_id: uuid.UUID,
    purpose: OneTimeTokenPurpose,
    ttl_s: int,
    *,
    payload: dict[str, Any] | None = None,
    invalidate_previous: bool = True,
) -> tuple[str, datetime]:
    """Create a token; returns ``(plaintext, expires_at)``. Previous unused tokens of the same
    purpose are invalidated (only the latest link works)."""
    now = datetime.now(UTC)
    if invalidate_previous:
        await db.execute(
            update(OneTimeToken)
            .where(
                OneTimeToken.user_id == user_id,
                OneTimeToken.purpose == purpose,
                OneTimeToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
    token = random_token(32)
    expires = now + timedelta(seconds=ttl_s)
    db.add(
        OneTimeToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=sha256(token),
            expires_at=expires,
            payload=payload or {},
        )
    )
    await db.flush()
    return token, expires


async def find_valid(db: AsyncSession, token: str, purpose: OneTimeTokenPurpose) -> OneTimeToken | None:
    row = (
        await db.execute(
            select(OneTimeToken)
            .where(OneTimeToken.token_hash == sha256(token), OneTimeToken.purpose == purpose)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at <= datetime.now(UTC):
        return None
    return row


async def consume(db: AsyncSession, token: str, purpose: OneTimeTokenPurpose) -> OneTimeToken | None:
    row = await find_valid(db, token, purpose)
    if row is not None:
        row.used_at = datetime.now(UTC)
        await db.flush()
    return row
