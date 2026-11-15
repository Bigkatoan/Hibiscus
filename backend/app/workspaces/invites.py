"""Invite tokens (72 h, single use, role fixed in the invite)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.serializers import iso_req, user_ref
from app.core.crypto import random_token, sha256
from app.core.errors import ErrorCode, ProblemError
from app.db.models import Invite, Membership, User, Workspace, WorkspaceRole


def new_invite_token(ttl_s: int) -> tuple[str, bytes, datetime]:
    token = random_token(32)
    return token, sha256(token), datetime.now(UTC) + timedelta(seconds=ttl_s)


def invite_status(inv: Invite, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    if inv.accepted_at is not None:
        return "accepted"
    if inv.revoked_at is not None:
        return "revoked"
    if inv.expires_at <= now:
        return "expired"
    return "pending"


def invite_out(inv: Invite, inviter: User | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(inv.id),
        "email": inv.email,
        "role": WorkspaceRole(inv.role).value,
        "status": invite_status(inv),
        "expires_at": iso_req(inv.expires_at),
        "created_at": iso_req(inv.created_at),
    }
    ref = user_ref(inviter)
    if ref is not None:
        out["invited_by"] = ref
    return out


async def lookup_invite(
    db: AsyncSession, token: str, *, for_update: bool = False
) -> tuple[Invite, Workspace]:
    """Resolve a plaintext invite token.

    Raises 404 ``invite_invalid`` / 410 ``invite_expired`` / 410 ``gone`` (already used)."""
    stmt = (
        select(Invite, Workspace)
        .join(Workspace, Workspace.id == Invite.workspace_id)
        .where(Invite.token_hash == sha256(token))
    )
    if for_update:
        stmt = stmt.with_for_update(of=Invite)
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        raise ProblemError(404, ErrorCode.INVITE_INVALID)
    inv, ws = row
    if inv.revoked_at is not None or ws.deleted_at is not None:
        raise ProblemError(404, ErrorCode.INVITE_INVALID)
    if inv.accepted_at is not None:
        raise ProblemError(410, ErrorCode.GONE, "Invite already used")
    if inv.expires_at <= datetime.now(UTC):
        raise ProblemError(410, ErrorCode.INVITE_EXPIRED)
    return inv, ws


async def accept_invite(db: AsyncSession, inv: Invite, user: User) -> Membership:
    existing = (
        await db.execute(
            select(Membership).where(
                Membership.workspace_id == inv.workspace_id, Membership.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ProblemError(409, ErrorCode.MEMBER_EXISTS)
    m = Membership(workspace_id=inv.workspace_id, user_id=user.id, role=inv.role, invited_by=inv.invited_by)
    db.add(m)
    inv.accepted_at = datetime.now(UTC)
    inv.accepted_by = user.id
    await db.flush()
    return m
