"""ORM -> contract JSON (api/openapi.yaml schemas)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApiToken, Membership, User, Workspace, WorkspaceRole


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def iso_req(dt: datetime) -> str:
    out = iso(dt)
    assert out is not None  # noqa: S101 - dt is not None by type
    return out


def user_out(u: User) -> dict[str, Any]:
    return {
        "id": str(u.id),
        "email": u.email,
        "display_name": u.display_name,
        "locale": u.locale,
        "email_verified": u.email_verified_at is not None,
        "mfa_enabled": u.totp_enabled_at is not None,
        "is_platform_admin": u.is_platform_admin,
        "created_at": iso_req(u.created_at),
    }


def user_ref(u: User | None) -> dict[str, Any] | None:
    if u is None:
        return None
    return {"id": str(u.id), "display_name": u.display_name}


def membership_out(ws: Workspace, role: WorkspaceRole | str) -> dict[str, Any]:
    return {
        "workspace_id": str(ws.id),
        "workspace_slug": ws.slug,
        "workspace_name": ws.name,
        "role": WorkspaceRole(role).value,
    }


async def memberships_for(db: AsyncSession, user_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user_id, Workspace.deleted_at.is_(None))
        .order_by(Workspace.name, Workspace.id)
    )
    return [membership_out(ws, role) for ws, role in rows.all()]


def api_token_out(t: ApiToken) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "name": t.name,
        "prefix": t.prefix,
        "workspace_id": str(t.workspace_id),
        "scopes": list(t.scopes),
        "created_at": iso_req(t.created_at),
        "expires_at": iso(t.expires_at),
        "last_used_at": iso(t.last_used_at),
        "last_used_ip": str(t.last_used_ip) if t.last_used_ip is not None else None,
        "revoked_at": iso(t.revoked_at),
    }
