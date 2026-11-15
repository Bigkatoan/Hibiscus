"""Immutable, hash-chained audit log (``audit_events``).

``await record(AuditAction.RUN_CREATED, db=session, actor=principal, workspace_id=ws,
target_type="run", target_id=str(run.id), details={...})`` inserts the row inside the caller's
transaction (it is persisted when the caller commits). ``hash = sha256(prev_hash || canonical
JSON of the row)``; writers are serialised with a transaction-scoped advisory lock so the chain is
linear. ``details`` must never contain secrets (they are additionally redacted by key name).
The DB trigger installed by the initial migration rejects UPDATE/DELETE (docs/db-schema.md).
"""

from __future__ import annotations

import enum
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import request_ctx
from app.core.logging import redact
from app.db.models import AuditEvent

if TYPE_CHECKING:
    from app.core.deps import Principal

_AUDIT_LOCK_KEY = 0x4C54_4155  # "LTAU"
Outcome = Literal["success", "failure", "denied"]


class AuditAction(enum.StrEnum):
    AUTH_LOGIN = "auth.login"
    AUTH_LOGIN_FAILED = "auth.login_failed"
    AUTH_LOGOUT = "auth.logout"
    AUTH_REFRESH_REUSE = "auth.refresh_reuse"
    AUTH_PASSWORD_RESET_REQUESTED = "auth.password_reset_requested"  # noqa: S105
    AUTH_PASSWORD_RESET = "auth.password_reset"  # noqa: S105
    AUTH_PASSWORD_CHANGED = "auth.password_changed"  # noqa: S105
    AUTH_MFA_ENABLED = "auth.mfa_enabled"
    AUTH_MFA_DISABLED = "auth.mfa_disabled"
    AUTH_RECOVERY_CODES_REGENERATED = "auth.recovery_codes_regenerated"
    AUTH_RECOVERY_CODE_USED = "auth.recovery_code_used"
    AUTH_SESSION_REVOKED = "auth.session_revoked"
    AUTH_ACCOUNT_LOCKED = "auth.account_locked"
    TOKEN_CREATED = "token.created"  # noqa: S105
    TOKEN_REVOKED = "token.revoked"  # noqa: S105
    USER_REGISTERED = "user.registered"
    USER_UPDATED = "user.updated"
    ADMIN_USER_UPDATED = "admin.user_updated"
    ADMIN_SESSIONS_REVOKED = "admin.sessions_revoked"
    ADMIN_RESET_LINK_CREATED = "admin.reset_link_created"
    ADMIN_QUOTA_UPDATED = "admin.quota_updated"
    ADMIN_GPU_UPDATED = "admin.gpu_updated"
    WORKSPACE_CREATED = "workspace.created"
    WORKSPACE_UPDATED = "workspace.updated"
    WORKSPACE_DELETED = "workspace.deleted"
    MEMBER_ROLE_CHANGED = "member.role_changed"
    MEMBER_REMOVED = "member.removed"
    INVITE_CREATED = "invite.created"
    INVITE_REVOKED = "invite.revoked"
    INVITE_ACCEPTED = "invite.accepted"
    DATASET_CREATED = "dataset.created"
    DATASET_DELETED = "dataset.deleted"
    DATASET_VERSION_CREATED = "dataset_version.created"
    DATASET_VERSION_DELETED = "dataset_version.deleted"
    RUN_CREATED = "run.created"
    RUN_CANCELLED = "run.cancelled"
    RUN_PAUSED = "run.paused"
    RUN_RESUMED = "run.resumed"
    MODEL_DOWNLOADED = "model.downloaded"
    MODEL_FILE_DOWNLOADED = "model.file_downloaded"
    MODEL_DELETED = "model.deleted"
    MODEL_PUSHED_HUB = "model.pushed_hub"
    SECRET_UPDATED = "secret.updated"  # noqa: S105


def _canonical(row: dict[str, Any]) -> bytes:
    return json.dumps(row, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False).encode()


def compute_hash(prev_hash: bytes | None, fields: dict[str, Any]) -> bytes:
    return hashlib.sha256((prev_hash or b"") + _canonical(fields)).digest()


def _hash_fields(ev: AuditEvent) -> dict[str, Any]:
    return {
        "created_at": ev.created_at.astimezone(UTC).isoformat(),
        "workspace_id": str(ev.workspace_id) if ev.workspace_id else None,
        "actor_user_id": str(ev.actor_user_id) if ev.actor_user_id else None,
        "actor_token_id": str(ev.actor_token_id) if ev.actor_token_id else None,
        "action": ev.action,
        "target_type": ev.target_type,
        "target_id": ev.target_id,
        "outcome": ev.outcome,
        "ip": str(ev.ip) if ev.ip is not None else None,
        "user_agent": ev.user_agent,
        "request_id": ev.request_id,
        "details": ev.details,
    }


async def record(
    action: AuditAction,
    *,
    db: AsyncSession,
    actor: Principal | uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    outcome: Outcome = "success",
    actor_token_id: uuid.UUID | None = None,
) -> AuditEvent:
    """Append an audit event to the caller's transaction. Commit is the caller's job."""
    actor_user_id: uuid.UUID | None
    if actor is None or isinstance(actor, uuid.UUID):
        actor_user_id = actor
    else:
        actor_user_id = actor.user_id
        actor_token_id = actor_token_id or actor.token_id
    ctx = request_ctx.get()
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _AUDIT_LOCK_KEY})
    prev = (await db.execute(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1))).scalar()
    now = datetime.now(UTC)
    ev = AuditEvent(
        created_at=now,
        updated_at=now,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        actor_token_id=actor_token_id,
        action=AuditAction(action).value,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        outcome=outcome,
        ip=ctx.ip,
        user_agent=ctx.user_agent[:512] if ctx.user_agent else None,
        request_id=ctx.request_id,
        details=redact(details or {}),
        prev_hash=prev,
    )
    ev.hash = compute_hash(prev, _hash_fields(ev))
    db.add(ev)
    await db.flush()
    return ev


async def verify_chain(db: AsyncSession, *, batch: int = 1000) -> tuple[bool, int | None]:
    """Recompute the chain. Returns ``(ok, first_bad_id)``."""
    prev: bytes | None = None
    last_id = 0
    total = (await db.execute(select(func.count()).select_from(AuditEvent))).scalar_one()
    seen = 0
    while seen < total:
        rows = (
            (
                await db.execute(
                    select(AuditEvent).where(AuditEvent.id > last_id).order_by(AuditEvent.id).limit(batch)
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            break
        for ev in rows:
            if ev.prev_hash != prev or ev.hash != compute_hash(prev, _hash_fields(ev)):
                return False, ev.id
            prev = ev.hash
            last_id = ev.id
            seen += 1
    return True, None
