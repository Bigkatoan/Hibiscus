"""/api/v1/workspaces/* (OpenAPI tag ``workspaces``): workspaces, members, invites, usage, events."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from redis.asyncio.client import PubSub
from redis.exceptions import RedisError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.auth.emails import invite_email
from app.auth.serializers import iso_req, user_ref
from app.core.audit import AuditAction, record
from app.core.deps import (
    MFA_ROLES,
    ROLE_RANK,
    Principal,
    StreamAuthGuard,
    current_principal,
    ensure_role,
    get_db,
    services,
    session_principal,
)
from app.core.email import send_safely
from app.core.errors import VALIDATION_400, ErrorCode, ProblemError
from app.core.events import workspace_channel
from app.db.models import ApiToken, Invite, Membership, Quota, Run, RunStatus, User, Workspace, WorkspaceRole
from app.workspaces.invites import invite_out, new_invite_token
from app.workspaces.quotas import (
    ACTIVE_STATUSES,
    effective_limits,
    fair_share_hours_7d,
    run_counts,
    storage_used,
)
from app.workspaces.schemas import (
    InviteCreate,
    MemberRoleUpdate,
    WorkspaceCreate,
    WorkspaceSettings,
    WorkspaceUpdate,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])
HEARTBEAT_S = 15.0


def _settings_out(raw: dict[str, Any] | None) -> dict[str, Any]:
    return WorkspaceSettings.model_validate(raw or {}).model_dump()


async def _member_count(db: AsyncSession, ws_id: uuid.UUID) -> int:
    return int(
        (
            await db.execute(
                select(func.count()).select_from(Membership).where(Membership.workspace_id == ws_id)
            )
        ).scalar_one()
    )


async def _workspace_out(db: AsyncSession, ws: Workspace, role: WorkspaceRole) -> dict[str, Any]:
    return {
        "id": str(ws.id),
        "slug": ws.slug,
        "name": ws.name,
        "my_role": WorkspaceRole(role).value,
        "member_count": await _member_count(db, ws.id),
        "settings": _settings_out(ws.settings),
        "created_at": iso_req(ws.created_at),
    }


async def _live_workspace(db: AsyncSession, ws_id: uuid.UUID) -> Workspace:
    ws = await db.get(Workspace, ws_id)
    if ws is None or ws.deleted_at is not None:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    return ws


# --------------------------------------------------------------------------------------------
# Workspaces
# --------------------------------------------------------------------------------------------
@router.get("", operation_id="listWorkspaces", openapi_extra=VALIDATION_400)
async def list_workspaces(
    principal: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    ids = list(principal.workspace_ids_roles)
    if not ids:
        return {"items": []}
    rows = (
        (
            await db.execute(
                select(Workspace)
                .where(Workspace.id.in_(ids), Workspace.deleted_at.is_(None))
                .order_by(Workspace.name, Workspace.id)
            )
        )
        .scalars()
        .all()
    )
    return {"items": [await _workspace_out(db, ws, principal.workspace_ids_roles[ws.id]) for ws in rows]}


@router.post("", operation_id="createWorkspace", status_code=201)
async def create_workspace(
    body: WorkspaceCreate,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not principal.is_platform_admin:
        raise ProblemError(403, ErrorCode.FORBIDDEN, "Only platform admins can create workspaces")
    taken = (
        await db.execute(
            select(Workspace.id).where(Workspace.slug == body.slug, Workspace.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if taken is not None:
        raise ProblemError(409, ErrorCode.WORKSPACE_SLUG_TAKEN)
    ws = Workspace(slug=body.slug, name=body.name.strip(), created_by=principal.user_id, settings={})
    db.add(ws)
    try:
        await db.flush()
    except IntegrityError as e:  # concurrent create with the same slug
        await db.rollback()
        raise ProblemError(409, ErrorCode.WORKSPACE_SLUG_TAKEN) from e
    db.add(Membership(workspace_id=ws.id, user_id=principal.user_id, role=WorkspaceRole.OWNER))
    db.add(Quota(workspace_id=ws.id, user_id=None))
    await record(
        AuditAction.WORKSPACE_CREATED,
        db=db,
        actor=principal,
        workspace_id=ws.id,
        target_type="workspace",
        target_id=ws.id,
        details={"slug": ws.slug},
    )
    await db.commit()
    await db.refresh(ws)
    return await _workspace_out(db, ws, WorkspaceRole.OWNER)


@router.get("/{workspace_id}", operation_id="getWorkspace", openapi_extra=VALIDATION_400)
async def get_workspace(
    workspace_id: uuid.UUID,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    role = ensure_role(principal, workspace_id, WorkspaceRole.VIEWER)
    return await _workspace_out(db, await _live_workspace(db, workspace_id), role)


@router.patch("/{workspace_id}", operation_id="updateWorkspace")
async def update_workspace(
    workspace_id: uuid.UUID,
    body: WorkspaceUpdate,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    role = ensure_role(principal, workspace_id, WorkspaceRole.ADMIN)
    ws = await _live_workspace(db, workspace_id)
    changed: list[str] = []
    if body.name is not None:
        ws.name = body.name.strip()
        changed.append("name")
    if body.settings is not None:
        ws.settings = body.settings.model_dump()
        changed.append("settings")
    await record(
        AuditAction.WORKSPACE_UPDATED,
        db=db,
        actor=principal,
        workspace_id=ws.id,
        target_type="workspace",
        target_id=ws.id,
        details={"fields": changed},
    )
    await db.commit()
    await db.refresh(ws)
    return await _workspace_out(db, ws, role)


@router.delete(
    "/{workspace_id}",
    operation_id="deleteWorkspace",
    openapi_extra=VALIDATION_400,
    status_code=204,
    response_class=Response,
)
async def delete_workspace(
    workspace_id: uuid.UUID,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    ensure_role(principal, workspace_id, WorkspaceRole.OWNER)
    ws = (
        await db.execute(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    ).scalar_one()
    active = (
        await db.execute(
            select(func.count())
            .select_from(Run)
            .where(Run.workspace_id == workspace_id, Run.status.in_((*ACTIVE_STATUSES, RunStatus.QUEUED)))
        )
    ).scalar_one()
    if active:
        raise ProblemError(409, ErrorCode.WORKSPACE_NOT_EMPTY, params={"active_runs": int(active)})
    now = datetime.now(UTC)
    ws.deleted_at = now
    ws.slug = ws.slug  # slug stays (unique only among live rows)
    await db.execute(
        update(ApiToken)
        .where(ApiToken.workspace_id == workspace_id, ApiToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.execute(
        update(Invite)
        .where(Invite.workspace_id == workspace_id, Invite.accepted_at.is_(None), Invite.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await record(
        AuditAction.WORKSPACE_DELETED,
        db=db,
        actor=principal,
        workspace_id=ws.id,
        target_type="workspace",
        target_id=ws.id,
    )
    await db.commit()
    return None


# --------------------------------------------------------------------------------------------
# Members
# --------------------------------------------------------------------------------------------
def _member_out(m: Membership, u: User) -> dict[str, Any]:
    return {
        "user": user_ref(u),
        "email": u.email,
        "role": WorkspaceRole(m.role).value,
        "mfa_enabled": u.totp_enabled_at is not None,
        "joined_at": iso_req(m.created_at),
    }


@router.get("/{workspace_id}/members", operation_id="listMembers", openapi_extra=VALIDATION_400)
async def list_members(
    workspace_id: uuid.UUID,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    ensure_role(principal, workspace_id, WorkspaceRole.VIEWER)
    rows = await db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == workspace_id)
        .order_by(func.lower(User.display_name), User.id)
    )
    return {"items": [_member_out(m, u) for m, u in rows.all()]}


async def _membership(
    db: AsyncSession, ws_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False
) -> tuple[Membership, User]:
    stmt = (
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == ws_id, Membership.user_id == user_id)
    )
    if lock:
        stmt = stmt.with_for_update(of=Membership)
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    return row[0], row[1]


async def _owner_count(db: AsyncSession, ws_id: uuid.UUID) -> int:
    # lock all owner rows so concurrent demotions cannot both pass the "last owner" check
    rows = (
        await db.execute(
            select(Membership.id)
            .where(Membership.workspace_id == ws_id, Membership.role == WorkspaceRole.OWNER)
            .with_for_update()
        )
    ).all()
    return len(rows)


@router.patch(
    "/{workspace_id}/members/{user_id}", operation_id="updateMemberRole", openapi_extra=VALIDATION_400
)
async def update_member_role(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    body: MemberRoleUpdate,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    actor_role = ensure_role(principal, workspace_id, WorkspaceRole.ADMIN)
    m, u = await _membership(db, workspace_id, user_id, lock=True)
    new = body.role
    old = WorkspaceRole(m.role)
    if actor_role != WorkspaceRole.OWNER:
        # admin: member/viewer for non-owners only
        if old == WorkspaceRole.OWNER or new not in (WorkspaceRole.MEMBER, WorkspaceRole.VIEWER):
            raise ProblemError(403, ErrorCode.FORBIDDEN)
    if old == new:
        return _member_out(m, u)
    if (
        old == WorkspaceRole.OWNER
        and new != WorkspaceRole.OWNER
        and await _owner_count(db, workspace_id) <= 1
    ):
        raise ProblemError(409, ErrorCode.LAST_OWNER)
    if new in MFA_ROLES and u.totp_enabled_at is None:
        raise ProblemError(409, ErrorCode.MFA_REQUIRED_BY_ROLE)
    m.role = new
    if ROLE_RANK[new] <= ROLE_RANK[WorkspaceRole.VIEWER]:
        # a viewer keeps only read scopes: revoke write-capable PATs for this workspace
        await db.execute(
            update(ApiToken)
            .where(
                ApiToken.workspace_id == workspace_id,
                ApiToken.user_id == user_id,
                ApiToken.revoked_at.is_(None),
                ApiToken.scopes.overlap(["datasets:write", "runs:write"]),
            )
            .values(revoked_at=datetime.now(UTC))
        )
    await record(
        AuditAction.MEMBER_ROLE_CHANGED,
        db=db,
        actor=principal,
        workspace_id=workspace_id,
        target_type="user",
        target_id=user_id,
        details={"from": old.value, "to": new.value},
    )
    await db.commit()
    return _member_out(m, u)


@router.delete(
    "/{workspace_id}/members/{user_id}",
    operation_id="removeMember",
    openapi_extra=VALIDATION_400,
    status_code=204,
    response_class=Response,
)
async def remove_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    self_leave = user_id == principal.user_id
    actor_role = ensure_role(
        principal, workspace_id, WorkspaceRole.VIEWER if self_leave else WorkspaceRole.ADMIN
    )
    m, _u = await _membership(db, workspace_id, user_id, lock=True)
    target = WorkspaceRole(m.role)
    if not self_leave and actor_role != WorkspaceRole.OWNER and target == WorkspaceRole.OWNER:
        raise ProblemError(403, ErrorCode.FORBIDDEN)
    if target == WorkspaceRole.OWNER and await _owner_count(db, workspace_id) <= 1:
        raise ProblemError(409, ErrorCode.LAST_OWNER)
    await db.delete(m)
    await db.execute(
        update(ApiToken)
        .where(
            ApiToken.workspace_id == workspace_id, ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None)
        )
        .values(revoked_at=datetime.now(UTC))
    )
    await db.execute(delete(Quota).where(Quota.workspace_id == workspace_id, Quota.user_id == user_id))
    await record(
        AuditAction.MEMBER_REMOVED,
        db=db,
        actor=principal,
        workspace_id=workspace_id,
        target_type="user",
        target_id=user_id,
        details={"role": target.value, "self": self_leave},
    )
    await db.commit()
    return None


# --------------------------------------------------------------------------------------------
# Invites
# --------------------------------------------------------------------------------------------
async def _send_invite(
    request: Request, db: AsyncSession, ws: Workspace, inv: Invite, token: str
) -> str | None:
    svc = services(request)
    url = svc.settings.link(svc.settings.invite_path, token)
    if not svc.email.enabled:
        return url
    existing = (
        await db.execute(select(User.locale).where(func.lower(User.email) == inv.email))
    ).scalar_one_or_none()
    await send_safely(
        svc.email, invite_email(inv.email, existing, ws.name, WorkspaceRole(inv.role).value, url)
    )
    return None


@router.get("/{workspace_id}/invites", operation_id="listInvites", openapi_extra=VALIDATION_400)
async def list_invites(
    workspace_id: uuid.UUID,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    ensure_role(principal, workspace_id, WorkspaceRole.ADMIN)
    rows = await db.execute(
        select(Invite, User)
        .outerjoin(User, User.id == Invite.invited_by)
        .where(Invite.workspace_id == workspace_id, Invite.accepted_at.is_(None), Invite.revoked_at.is_(None))
        .order_by(Invite.created_at.desc(), Invite.id)
        .limit(200)
    )
    return {"items": [invite_out(i, u) for i, u in rows.all()]}


@router.post("/{workspace_id}/invites", operation_id="createInvite", status_code=201)
async def create_invite(
    workspace_id: uuid.UUID,
    body: InviteCreate,
    request: Request,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = services(request)
    actor_role = ensure_role(principal, workspace_id, WorkspaceRole.ADMIN)
    role = WorkspaceRole(body.role)
    if role == WorkspaceRole.ADMIN and actor_role != WorkspaceRole.OWNER:
        raise ProblemError(403, ErrorCode.FORBIDDEN, "Only owners can invite admins")
    await svc.limiter.hit(
        "invite:create", str(workspace_id), limit=svc.settings.rl_invite_create_per_hour, window_s=3600
    )
    ws = await _live_workspace(db, workspace_id)
    email = str(body.email).lower()
    member = (
        await db.execute(
            select(Membership.id)
            .join(User, User.id == Membership.user_id)
            .where(Membership.workspace_id == workspace_id, func.lower(User.email) == email)
        )
    ).scalar_one_or_none()
    if member is not None:
        raise ProblemError(409, ErrorCode.MEMBER_EXISTS)
    now = datetime.now(UTC)
    await db.execute(  # only the latest invite per (workspace, email) stays valid
        update(Invite)
        .where(
            Invite.workspace_id == workspace_id,
            Invite.email == email,
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    token, token_hash, expires = new_invite_token(svc.settings.invite_ttl_s)
    inv = Invite(
        workspace_id=workspace_id,
        email=email,
        role=role,
        token_hash=token_hash,
        invited_by=principal.user_id,
        expires_at=expires,
    )
    db.add(inv)
    await db.flush()
    await record(
        AuditAction.INVITE_CREATED,
        db=db,
        actor=principal,
        workspace_id=workspace_id,
        target_type="invite",
        target_id=inv.id,
        details={"role": role.value, "email_domain": email.split("@")[-1]},
    )
    await db.commit()
    await db.refresh(inv)
    inviter = await db.get(User, principal.user_id)
    out = invite_out(inv, inviter)
    out["accept_url"] = await _send_invite(request, db, ws, inv, token)
    return out


async def _pending_invite(db: AsyncSession, workspace_id: uuid.UUID, invite_id: uuid.UUID) -> Invite:
    inv = (
        await db.execute(
            select(Invite)
            .where(Invite.id == invite_id, Invite.workspace_id == workspace_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if inv is None or inv.accepted_at is not None or inv.revoked_at is not None:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    return inv


@router.delete(
    "/{workspace_id}/invites/{invite_id}",
    operation_id="revokeInvite",
    openapi_extra=VALIDATION_400,
    status_code=204,
    response_class=Response,
)
async def revoke_invite(
    workspace_id: uuid.UUID,
    invite_id: uuid.UUID,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    ensure_role(principal, workspace_id, WorkspaceRole.ADMIN)
    inv = await _pending_invite(db, workspace_id, invite_id)
    inv.revoked_at = datetime.now(UTC)
    await record(
        AuditAction.INVITE_REVOKED,
        db=db,
        actor=principal,
        workspace_id=workspace_id,
        target_type="invite",
        target_id=inv.id,
    )
    await db.commit()
    return None


@router.post(
    "/{workspace_id}/invites/{invite_id}/resend", operation_id="resendInvite", openapi_extra=VALIDATION_400
)
async def resend_invite(
    workspace_id: uuid.UUID,
    invite_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = services(request)
    actor_role = ensure_role(principal, workspace_id, WorkspaceRole.ADMIN)
    await svc.limiter.hit(
        "invite:resend", str(invite_id), limit=svc.settings.rl_resend_per_hour, window_s=3600
    )
    ws = await _live_workspace(db, workspace_id)
    inv = await _pending_invite(db, workspace_id, invite_id)
    if WorkspaceRole(inv.role) == WorkspaceRole.ADMIN and actor_role != WorkspaceRole.OWNER:
        raise ProblemError(403, ErrorCode.FORBIDDEN)
    token, token_hash, expires = new_invite_token(svc.settings.invite_ttl_s)
    inv.token_hash = token_hash
    inv.expires_at = expires
    await record(
        AuditAction.INVITE_CREATED,
        db=db,
        actor=principal,
        workspace_id=workspace_id,
        target_type="invite",
        target_id=inv.id,
        details={"resend": True, "role": WorkspaceRole(inv.role).value},
    )
    await db.commit()
    await db.refresh(inv)
    inviter = await db.get(User, inv.invited_by) if inv.invited_by else None
    out = invite_out(inv, inviter)
    out["accept_url"] = await _send_invite(request, db, ws, inv, token)
    return out


# --------------------------------------------------------------------------------------------
# Usage & events
# --------------------------------------------------------------------------------------------
@router.get("/{workspace_id}/usage", operation_id="getWorkspaceUsage", openapi_extra=VALIDATION_400)
async def get_workspace_usage(
    workspace_id: uuid.UUID,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    ensure_role(principal, workspace_id, WorkspaceRole.VIEWER)
    await _live_workspace(db, workspace_id)
    ws_active, ws_queued, ws_hours = await run_counts(db, workspace_id)
    me_active, me_queued, me_hours = await run_counts(db, workspace_id, principal.user_id)
    return {
        "workspace": {
            "limits": await effective_limits(db, workspace_id),
            "storage_bytes_used": await storage_used(db, workspace_id),
            "gpu_hours_this_month": ws_hours,
            "active_runs": ws_active,
            "queued_runs": ws_queued,
        },
        "me": {
            "limits": await effective_limits(db, workspace_id, principal.user_id),
            "gpu_hours_this_month": me_hours,
            "active_runs": me_active,
            "queued_runs": me_queued,
            "fair_share_gpu_hours_7d": await fair_share_hours_7d(db, principal.user_id),
        },
    }


@router.get("/{workspace_id}/events", operation_id="streamWorkspaceEvents", openapi_extra=VALIDATION_400)
async def stream_workspace_events(
    workspace_id: uuid.UUID, request: Request, principal: Principal = Depends(session_principal)
) -> EventSourceResponse:
    ensure_role(principal, workspace_id, WorkspaceRole.VIEWER)
    redis = services(request).redis
    # Re-checks the session and membership while the stream is open, and caps its lifetime: a
    # logout, session revoke or member removal ends the stream (SEC-auth-03).
    guard = StreamAuthGuard.for_request(request, principal, workspace_id)

    async def gen() -> AsyncIterator[ServerSentEvent]:
        pubsub: PubSub | None = redis.pubsub()
        try:
            assert pubsub is not None  # noqa: S101 - just created
            await pubsub.subscribe(workspace_channel(workspace_id))
        except (RedisError, OSError):
            pubsub = None
        try:
            while True:
                if await request.is_disconnected() or not await guard.ok():
                    break
                msg = None
                if pubsub is not None:
                    try:
                        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    except (RedisError, OSError):
                        pubsub = None
                else:
                    await asyncio.sleep(1.0)
                if msg and msg.get("type") == "message":
                    try:
                        env = json.loads(msg["data"])
                        addressed = env.get("user_id")
                        if addressed is not None and addressed != str(principal.user_id):
                            continue  # per-user event (notification) for another member
                        yield ServerSentEvent(
                            event=str(env["event"]), data=json.dumps(env["data"], default=str)
                        )
                    except (ValueError, KeyError, TypeError):
                        continue
        finally:
            if pubsub is not None:
                await pubsub.aclose()  # type: ignore[no-untyped-call]  # redis-py: aclose is untyped

    return EventSourceResponse(
        gen(),
        ping=int(HEARTBEAT_S),
        ping_message_factory=lambda: ServerSentEvent(
            event="heartbeat", data=json.dumps({"kind": "heartbeat", "ts": iso_req(datetime.now(UTC))})
        ),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
