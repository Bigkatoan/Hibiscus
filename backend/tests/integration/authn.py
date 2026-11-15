"""Real credentials for API tests (no dependency overrides).

* :func:`session_headers` — a ``sessions`` row + ``hb_access`` JWT signed by the app's
  ``JwtService`` + double-submit CSRF pair, returned as request headers (``Cookie`` +
  ``X-CSRF-Token``) so one httpx client can act as several users.
* :func:`pat_headers` — an ``api_tokens`` row (sha256 of the plaintext, like ``POST /users/me/tokens``)
  returned as ``Authorization: Bearer hbp_...``.

Both go through ``app.core.deps.current_principal`` exactly like production requests.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.auth.pat import generate_pat, pat_hash
from app.core.crypto import random_token, sha256
from app.core.deps import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER
from app.db.models import ApiToken, Membership, User, Workspace, WorkspaceRole
from app.db.models import Session as DbSession


def _maker(app: Any) -> Any:
    return app.state.services.db.sessionmaker


async def create_user(
    app: Any, *, email: str | None = None, mfa_enrolled: bool = True, platform_admin: bool = False
) -> uuid.UUID:
    """A verified, active user. ``mfa_enrolled`` avoids ``mfa_enrollment_required`` for owners/admins."""
    now = datetime.now(UTC)
    async with _maker(app)() as db:
        u = User(
            email=(email or f"{uuid.uuid4().hex[:16]}@example.com").lower(),
            display_name="Tester",
            password_hash="!unusable",
            email_verified_at=now,
            is_platform_admin=platform_admin,
            totp_secret_enc=b"\0" if mfa_enrolled else None,
            totp_enabled_at=now if mfa_enrolled else None,
        )
        db.add(u)
        await db.commit()
        return u.id


async def create_workspace(
    app: Any, members: dict[uuid.UUID, WorkspaceRole], *, ws_id: uuid.UUID | None = None
) -> uuid.UUID:
    async with _maker(app)() as db:
        w = Workspace(id=ws_id or uuid.uuid4(), slug=f"w{uuid.uuid4().hex[:12]}", name="WS", settings={})
        db.add(w)
        await db.flush()
        for uid, role in members.items():
            db.add(Membership(workspace_id=w.id, user_id=uid, role=role))
        await db.commit()
        return w.id


async def add_member(app: Any, workspace_id: uuid.UUID, user_id: uuid.UUID, role: WorkspaceRole) -> None:
    async with _maker(app)() as db:
        if await db.get(Workspace, workspace_id) is None:
            db.add(Workspace(id=workspace_id, slug=f"w{uuid.uuid4().hex[:12]}", name="WS", settings={}))
            await db.flush()
        exists = (
            await db.execute(
                select(Membership).where(
                    Membership.workspace_id == workspace_id, Membership.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(Membership(workspace_id=workspace_id, user_id=user_id, role=role))
        await db.commit()


async def session_headers(app: Any, user_id: uuid.UUID, *, mfa_verified: bool = True) -> dict[str, str]:
    svc = app.state.services
    now = datetime.now(UTC)
    family = uuid.uuid4()
    async with _maker(app)() as db:
        db.add(
            DbSession(
                id=family,
                user_id=user_id,
                family_id=family,
                refresh_token_hash=sha256(random_token(32)),
                expires_at=now + timedelta(hours=2),
                idle_expires_at=now + timedelta(hours=2),
                last_used_at=now,
                mfa_verified=mfa_verified,
            )
        )
        await db.commit()
    access = svc.jwt.issue(user_id, family, mfa_verified)
    csrf = random_token(32)
    return {"Cookie": f"{ACCESS_COOKIE}={access}; {CSRF_COOKIE}={csrf}", CSRF_HEADER: csrf}


async def pat_headers(
    app: Any, user_id: uuid.UUID, workspace_id: uuid.UUID, scopes: Iterable[str]
) -> dict[str, str]:
    prefix, token = generate_pat()
    async with _maker(app)() as db:
        db.add(
            ApiToken(
                user_id=user_id,
                workspace_id=workspace_id,
                name=f"test-{prefix}",
                prefix=prefix,
                token_hash=pat_hash(token),
                scopes=list(scopes),
            )
        )
        await db.commit()
    return {"Authorization": f"Bearer {token}"}
