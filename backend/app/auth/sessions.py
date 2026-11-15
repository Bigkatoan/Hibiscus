"""Refresh-token sessions (one row per token, rotating, family-based reuse detection) and cookies."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import random_token, sha256
from app.core.deps import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE, services
from app.core.services import Services
from app.db.models import Session as DbSession
from app.db.models import SessionRevokeReason

REFRESH_PATH = "/api/v1/auth"
ACCESS_PATH = "/api"


@dataclass(frozen=True, slots=True)
class IssuedSession:
    family_id: uuid.UUID
    access_token: str
    refresh_token: str
    csrf_token: str
    expires_at: datetime


async def create_session(
    db: AsyncSession, svc: Services, request: Request, user_id: uuid.UUID, *, mfa_verified: bool
) -> IssuedSession:
    now = datetime.now(UTC)
    s = svc.settings
    family = uuid.uuid4()
    refresh = random_token(32)
    row = DbSession(
        id=family,
        user_id=user_id,
        family_id=family,
        refresh_token_hash=sha256(refresh),
        expires_at=now + timedelta(seconds=s.session_absolute_ttl_s),
        idle_expires_at=now + timedelta(seconds=s.session_idle_ttl_s),
        last_used_at=now,
        mfa_verified=mfa_verified,
        ip=getattr(request.state, "client_ip", None),
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
    )
    db.add(row)
    await db.flush()
    return IssuedSession(
        family_id=family,
        access_token=svc.jwt.issue(user_id, family, mfa_verified, refresh_id=row.id),
        refresh_token=refresh,
        csrf_token=random_token(32),
        expires_at=row.expires_at,
    )


async def revoke_family(
    db: AsyncSession, family_id: uuid.UUID, reason: SessionRevokeReason, *, user_id: uuid.UUID | None = None
) -> int:
    stmt = (
        update(DbSession)
        .where(DbSession.family_id == family_id, DbSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
    )
    if user_id is not None:
        stmt = stmt.where(DbSession.user_id == user_id)
    res = await db.execute(stmt)
    return int(getattr(res, "rowcount", 0) or 0)


async def revoke_user_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    reason: SessionRevokeReason,
    *,
    except_family: uuid.UUID | None = None,
) -> int:
    stmt = (
        update(DbSession)
        .where(DbSession.user_id == user_id, DbSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
    )
    if except_family is not None:
        stmt = stmt.where(DbSession.family_id != except_family)
    res = await db.execute(stmt)
    return int(getattr(res, "rowcount", 0) or 0)


async def current_row(db: AsyncSession, family_id: uuid.UUID) -> DbSession | None:
    return (
        await db.execute(
            select(DbSession).where(DbSession.family_id == family_id, DbSession.rotated_at.is_(None))
        )
    ).scalar_one_or_none()


def _set(
    response: Response, request: Request, name: str, value: str, path: str, httponly: bool, max_age: int
) -> None:
    s = services(request).settings
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path=path,
        httponly=httponly,
        secure=s.cookie_secure,
        samesite="strict",
        domain=s.cookie_domain,
    )


def set_session_cookies(response: Response, request: Request, issued: IssuedSession) -> None:
    max_age = max(1, int((issued.expires_at - datetime.now(UTC)).total_seconds()))
    _set(response, request, ACCESS_COOKIE, issued.access_token, ACCESS_PATH, True, max_age)
    _set(response, request, REFRESH_COOKIE, issued.refresh_token, REFRESH_PATH, True, max_age)
    _set(response, request, CSRF_COOKIE, issued.csrf_token, "/", False, max_age)


def set_access_cookie(response: Response, request: Request, access: str, expires_at: datetime) -> None:
    max_age = max(1, int((expires_at - datetime.now(UTC)).total_seconds()))
    _set(response, request, ACCESS_COOKIE, access, ACCESS_PATH, True, max_age)


def ensure_csrf_cookie(response: Response, request: Request) -> None:
    if request.cookies.get(CSRF_COOKIE):
        return
    max_age = services(request).settings.session_absolute_ttl_s
    _set(response, request, CSRF_COOKIE, random_token(32), "/", False, max_age)


def clear_session_cookies(response: Response, request: Request) -> None:
    s = services(request).settings
    for name, path, httponly in (
        (ACCESS_COOKIE, ACCESS_PATH, True),
        (REFRESH_COOKIE, REFRESH_PATH, True),
    ):
        response.delete_cookie(
            name,
            path=path,
            secure=s.cookie_secure,
            httponly=httponly,
            samesite="strict",
            domain=s.cookie_domain,
        )
