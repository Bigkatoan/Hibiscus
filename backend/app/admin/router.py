"""/api/v1/admin/* (OpenAPI tag ``admin``): users, audit log, quotas, system status.

Every route requires a platform admin with a 2FA-verified browser session (and a valid
Cloudflare Access assertion when that gate is enabled). ``PATCH /admin/gpus/{gpu_id}`` is A4's.
"""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import mfa, one_time
from app.auth.serializers import iso, iso_req, membership_out, user_out, user_ref
from app.auth.sessions import revoke_user_sessions
from app.core.audit import AuditAction, record
from app.core.deps import Principal, get_db, platform_admin, services
from app.core.errors import VALIDATION_400, ErrorCode, ProblemError
from app.core.pagination import decode_cursor, encode_cursor
from app.core.storage import ALL_BUCKETS
from app.db.models import (
    ApiToken,
    AuditEvent,
    GpuNode,
    Membership,
    OneTimeTokenPurpose,
    Quota,
    Run,
    RunStatus,
    SessionRevokeReason,
    User,
    Workspace,
)
from app.workspaces.quotas import quota_out
from app.workspaces.schemas import QuotaUpsert

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
Limit = Annotated[int, Query(ge=1, le=200)]
Cursor = Annotated[str | None, Query(max_length=512)]


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool | None = None
    is_platform_admin: bool | None = None
    unlock: bool | None = None
    reset_mfa: bool | None = None

    @model_validator(mode="after")
    def _check(self) -> AdminUserUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one property is required")
        for f in ("unlock", "reset_mfa"):
            if f in self.model_fields_set and getattr(self, f) is not True:
                raise ValueError(f"{f} must be true")
        for f in ("is_active", "is_platform_admin"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        return self


async def _admin_user_out(db: AsyncSession, u: User) -> dict[str, Any]:
    rows = await db.execute(
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == u.id, Workspace.deleted_at.is_(None))
        .order_by(Workspace.name)
    )
    out = user_out(u)
    out.update(
        {
            "is_active": u.is_active,
            "locked_until": iso(u.locked_until),
            "last_login_at": iso(u.last_login_at),
            "workspaces": [membership_out(ws, r) for ws, r in rows.all()],
        }
    )
    return out


def _like(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped.lower()}%"


@router.get("/users", operation_id="adminListUsers", openapi_extra=VALIDATION_400)
async def admin_list_users(
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Limit = 50,
    cursor: Cursor = None,
    _admin: Principal = Depends(platform_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(User)
    if q:
        pattern = _like(q)
        stmt = stmt.where(
            or_(
                func.lower(User.email).like(pattern, escape="\\"),
                func.lower(User.display_name).like(pattern, escape="\\"),
            )
        )
    if cursor:
        c = decode_cursor(cursor)
        stmt = stmt.where(User.email > str(c.get("email", "")))
    users = (await db.execute(stmt.order_by(User.email).limit(limit + 1))).scalars().all()
    page, more = users[:limit], len(users) > limit
    return {
        "items": [await _admin_user_out(db, u) for u in page],
        "next_cursor": encode_cursor({"email": page[-1].email}) if more and page else None,
    }


async def _target(db: AsyncSession, user_id: uuid.UUID) -> User:
    u = (await db.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one_or_none()
    if u is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    return u


@router.patch("/users/{user_id}", operation_id="adminUpdateUser", openapi_extra=VALIDATION_400)
async def admin_update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    admin: Principal = Depends(platform_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    u = await _target(db, user_id)
    changes: dict[str, Any] = {}
    if body.is_platform_admin is not None and body.is_platform_admin != u.is_platform_admin:
        if body.is_platform_admin and u.totp_enabled_at is None:
            raise ProblemError(409, ErrorCode.MFA_REQUIRED_BY_ROLE)
        if not body.is_platform_admin:
            others = (
                await db.execute(
                    select(func.count())
                    .select_from(User)
                    .where(User.is_platform_admin.is_(True), User.is_active.is_(True), User.id != u.id)
                )
            ).scalar_one()
            if others == 0:
                raise ProblemError(409, ErrorCode.CONFLICT, "Cannot remove the last platform admin")
        u.is_platform_admin = body.is_platform_admin
        changes["is_platform_admin"] = body.is_platform_admin
    if body.is_active is not None and body.is_active != u.is_active:
        if not body.is_active and u.id == admin.user_id:
            raise ProblemError(409, ErrorCode.CONFLICT, "Cannot disable your own account")
        u.is_active = body.is_active
        changes["is_active"] = body.is_active
        if not body.is_active:
            await revoke_user_sessions(db, u.id, SessionRevokeReason.ADMIN_REVOKED)
    if body.unlock:
        u.failed_login_count = 0
        u.locked_until = None
        changes["unlock"] = True
    if body.reset_mfa:
        if u.id == admin.user_id:
            raise ProblemError(409, ErrorCode.CONFLICT, "Use /auth/2fa to manage your own second factor")
        await mfa.clear_mfa(db, u)
        await revoke_user_sessions(db, u.id, SessionRevokeReason.ADMIN_REVOKED)
        changes["reset_mfa"] = True
    await record(
        AuditAction.ADMIN_USER_UPDATED,
        db=db,
        actor=admin,
        target_type="user",
        target_id=u.id,
        details=changes,
    )
    await db.commit()
    await db.refresh(u)
    return await _admin_user_out(db, u)


@router.post(
    "/users/{user_id}/revoke-sessions",
    operation_id="adminRevokeUserSessions",
    openapi_extra=VALIDATION_400,
    status_code=204,
    response_class=Response,
)
async def admin_revoke_user_sessions(
    user_id: uuid.UUID, admin: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)
) -> None:
    u = await _target(db, user_id)
    n_sessions = await revoke_user_sessions(db, u.id, SessionRevokeReason.ADMIN_REVOKED)
    res = await db.execute(
        update(ApiToken)
        .where(ApiToken.user_id == u.id, ApiToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await record(
        AuditAction.ADMIN_SESSIONS_REVOKED,
        db=db,
        actor=admin,
        target_type="user",
        target_id=u.id,
        details={"sessions": n_sessions, "tokens": int(getattr(res, "rowcount", 0) or 0)},
    )
    await db.commit()


@router.post(
    "/users/{user_id}/password-reset-link",
    operation_id="adminCreatePasswordResetLink",
    openapi_extra=VALIDATION_400,
    status_code=201,
)
async def admin_create_password_reset_link(
    user_id: uuid.UUID,
    request: Request,
    admin: Principal = Depends(platform_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    s = services(request).settings
    u = await _target(db, user_id)
    token, expires = await one_time.issue(
        db, u.id, OneTimeTokenPurpose.PASSWORD_RESET, s.password_reset_ttl_s
    )
    await record(AuditAction.ADMIN_RESET_LINK_CREATED, db=db, actor=admin, target_type="user", target_id=u.id)
    await db.commit()
    return {"url": s.link(s.reset_password_path, token), "expires_at": iso_req(expires)}


def _audit_out(ev: AuditEvent, actor: User | None) -> dict[str, Any]:
    return {
        "id": ev.id,
        "created_at": iso_req(ev.created_at),
        "workspace_id": str(ev.workspace_id) if ev.workspace_id else None,
        "actor": user_ref(actor),
        "actor_token_id": str(ev.actor_token_id) if ev.actor_token_id else None,
        "action": ev.action,
        "target_type": ev.target_type,
        "target_id": ev.target_id,
        "outcome": ev.outcome,
        "ip": str(ev.ip) if ev.ip is not None else None,
        "user_agent": ev.user_agent,
        "request_id": ev.request_id,
        "details": ev.details or {},
    }


@router.get("/audit-events", operation_id="adminListAuditEvents", openapi_extra=VALIDATION_400)
async def admin_list_audit_events(
    workspace_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    action: AuditAction | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Limit = 50,
    cursor: Cursor = None,
    _admin: Principal = Depends(platform_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(AuditEvent, User).outerjoin(User, User.id == AuditEvent.actor_user_id)
    if workspace_id:
        stmt = stmt.where(AuditEvent.workspace_id == workspace_id)
    if actor_user_id:
        stmt = stmt.where(AuditEvent.actor_user_id == actor_user_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action.value)
    if since:
        stmt = stmt.where(AuditEvent.created_at >= since)
    if until:
        stmt = stmt.where(AuditEvent.created_at < until)
    if cursor:
        before = int(decode_cursor(cursor).get("before_id", 0))
        stmt = stmt.where(AuditEvent.id < before)
    rows = (await db.execute(stmt.order_by(AuditEvent.id.desc()).limit(limit + 1))).all()
    page, more = rows[:limit], len(rows) > limit
    return {
        "items": [_audit_out(ev, u) for ev, u in page],
        "next_cursor": encode_cursor({"before_id": page[-1][0].id}) if more and page else None,
    }


async def _live_ws(db: AsyncSession, workspace_id: uuid.UUID) -> Workspace:
    ws = await db.get(Workspace, workspace_id)
    if ws is None or ws.deleted_at is not None:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    return ws


@router.get("/workspaces/{workspace_id}/quotas", operation_id="adminListQuotas", openapi_extra=VALIDATION_400)
async def admin_list_quotas(
    workspace_id: uuid.UUID, _admin: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    await _live_ws(db, workspace_id)
    rows = (
        (
            await db.execute(
                select(Quota)
                .where(Quota.workspace_id == workspace_id)
                .order_by(Quota.user_id.is_not(None), Quota.created_at)
            )
        )
        .scalars()
        .all()
    )
    return {"items": [quota_out(q) for q in rows]}


@router.put("/workspaces/{workspace_id}/quotas", operation_id="adminUpsertQuota")
async def admin_upsert_quota(
    workspace_id: uuid.UUID,
    body: QuotaUpsert,
    admin: Principal = Depends(platform_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _live_ws(db, workspace_id)
    if body.user_id is not None:
        member = (
            await db.execute(
                select(Membership.id).where(
                    Membership.workspace_id == workspace_id, Membership.user_id == body.user_id
                )
            )
        ).scalar_one_or_none()
        if member is None:
            raise ProblemError(
                422,
                ErrorCode.VALIDATION_FAILED,
                errors=[
                    {"loc": ["body", "user_id"], "code": "not_a_member", "message": "User is not a member"}
                ],
            )
    cond = Quota.user_id.is_(None) if body.user_id is None else Quota.user_id == body.user_id
    q = (
        await db.execute(select(Quota).where(Quota.workspace_id == workspace_id, cond).with_for_update())
    ).scalar_one_or_none()
    values = body.model_dump(exclude={"user_id"})
    if q is None:
        q = Quota(workspace_id=workspace_id, user_id=body.user_id, **values)
        db.add(q)
    else:
        for k, v in values.items():
            setattr(q, k, v)
    await db.flush()
    await record(
        AuditAction.ADMIN_QUOTA_UPDATED,
        db=db,
        actor=admin,
        workspace_id=workspace_id,
        target_type="quota",
        target_id=q.id,
        details={"user_id": str(body.user_id) if body.user_id else None, **values},
    )
    await db.commit()
    await db.refresh(q)
    return quota_out(q)


def _gpu_out(g: GpuNode, run: Run | None) -> dict[str, Any]:
    current = None
    if run is not None:
        current = {
            "id": str(run.id),
            "name": run.name,
            "workspace_id": str(run.workspace_id),
            "step": run.current_step,
            "total_steps": run.total_steps,
        }
    return {
        "id": g.id,
        "name": g.name,
        "total_vram_mb": g.total_vram_mb,
        "compute_capability": g.compute_capability,
        "supports_bf16": g.supports_bf16,
        "supports_fast_fp16": g.supports_fast_fp16,
        "status": g.status.value if hasattr(g.status, "value") else str(g.status),
        "last_heartbeat_at": iso(g.last_heartbeat_at),
        "current_run": current,
        "telemetry": None,
    }


@router.get("/system", operation_id="adminGetSystem", openapi_extra=VALIDATION_400)
async def admin_get_system(
    request: Request, _admin: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    svc = services(request)
    queue_depth = (
        await db.execute(select(func.count()).select_from(Run).where(Run.status == RunStatus.QUEUED))
    ).scalar_one()
    gpus = (
        await db.execute(
            select(GpuNode, Run).outerjoin(Run, Run.id == GpuNode.current_run_id).order_by(GpuNode.id)
        )
    ).all()
    storage: dict[str, Any] = {}
    try:
        storage["disk_free_bytes"] = int(shutil.disk_usage(svc.settings.data_dir_for_disk_stats).free)
    except OSError:  # pragma: no cover - path missing
        pass
    buckets: dict[str, int] = {}
    for b in ALL_BUCKETS:
        try:
            buckets[b] = await svc.s3.bucket_size(b, max_objects=100_000)
        except Exception:  # noqa: S112 - storage optional in this view
            continue
    storage["buckets"] = buckets
    return {
        "hibiscus_version": svc.settings.version,
        "lerobot_version": svc.settings.lerobot_version,
        "api_version": "0.1.0",
        "queue_depth": int(queue_depth),
        "gpus": [_gpu_out(g, r) for g, r in gpus],
        "storage": storage,
        "email": {"provider": svc.email.provider, "enabled": svc.email.enabled},
    }
