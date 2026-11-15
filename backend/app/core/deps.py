"""FastAPI dependencies shared by every package (OWNERSHIP.md note 1).

* ``get_db() -> AsyncSession`` — one session per request; callers ``await db.commit()`` explicitly.
* ``current_principal() -> Principal`` — cookie session (``hb_access`` JWT + CSRF on unsafe
  methods) or ``Authorization: Bearer hbp_...`` PAT.
* ``session_principal()`` — like ``current_principal`` but PATs get 403 ``forbidden``
  (cookie-only operations: member/invite/token management, /auth/*).
* ``require_scope(scope)`` — dependency factory; PATs must hold the scope (implications
  ``datasets:write ⇒ datasets:read``, ``runs:write ⇒ runs:read``); sessions always pass.
* ``require_role(workspace_id, min_role)`` — dependency factory. ``workspace_id`` is either a
  UUID or the *name* of the path/query parameter holding it (default ``"workspace_id"``).
  Non-members get 404 ``not_found``; a PAT bound to another workspace gets 403 ``forbidden``;
  insufficient role gets 403 ``forbidden``.
* ``ensure_role(principal, workspace_id, min_role)`` — the same check, imperative (use after
  loading an item to check its workspace).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import Depends, Request
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import AccessClaims, AccessTokenExpiredError, AccessTokenInvalidError
from app.auth.pat import expand_scopes, parse_pat, pat_hash
from app.core.crypto import constant_time_eq
from app.core.errors import ErrorCode, ProblemError
from app.core.services import Services
from app.db.models import ApiToken, Membership, PatScope, User, Workspace, WorkspaceRole
from app.db.models import Session as DbSession

ACCESS_COOKIE = "hb_access"
REFRESH_COOKIE = "hb_refresh"
CSRF_COOKIE = "hb_csrf"
CSRF_HEADER = "X-CSRF-Token"
API_PREFIX = "/api/v1"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

ROLE_RANK: dict[WorkspaceRole, int] = {
    WorkspaceRole.OWNER: 40,
    WorkspaceRole.ADMIN: 30,
    WorkspaceRole.MEMBER: 20,
    WorkspaceRole.VIEWER: 10,
}
MFA_ROLES = frozenset({WorkspaceRole.OWNER, WorkspaceRole.ADMIN})

# Paths a session that still has to enrol in 2FA may use (OpenAPI `login` description). The same
# list applies to a session of a 2FA-enabled owner/admin/platform admin that never passed 2FA
# (SEC-auth-01: e.g. opened before 2FA was enabled): everything else is 403 `mfa_reauth_required`.
_ENROLMENT_ALLOWED = (
    f"{API_PREFIX}/auth/me",
    f"{API_PREFIX}/auth/2fa/",
    f"{API_PREFIX}/auth/logout",
    f"{API_PREFIX}/auth/refresh",
)


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    workspace_ids_roles: Mapping[uuid.UUID, WorkspaceRole]
    auth_method: Literal["session", "pat"]
    token_scopes: frozenset[str]
    token_workspace_id: uuid.UUID | None
    mfa_verified: bool
    session_id: uuid.UUID | None = None  # session family id (cookie auth)
    token_id: uuid.UUID | None = None  # PAT id
    is_platform_admin: bool = False
    mfa_enabled: bool = False
    mfa_enrollment_required: bool = False
    email: str = field(default="", repr=False)

    def role_in(self, workspace_id: uuid.UUID) -> WorkspaceRole | None:
        return self.workspace_ids_roles.get(workspace_id)

    def has_scope(self, scope: PatScope | str) -> bool:
        if self.auth_method == "session":
            return True
        return str(scope) in self.token_scopes


def services(request: Request) -> Services:
    svc: Services = request.app.state.services
    return svc


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with services(request).db.sessionmaker() as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()


def mfa_required_for(user: User, roles: Mapping[uuid.UUID, WorkspaceRole] | list[WorkspaceRole]) -> bool:
    values = roles.values() if isinstance(roles, Mapping) else roles
    return user.is_platform_admin or any(r in MFA_ROLES for r in values)


async def load_roles(db: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, WorkspaceRole]:
    rows = await db.execute(
        select(Membership.workspace_id, Membership.role)
        .join(Workspace, Workspace.id == Membership.workspace_id)
        .where(Membership.user_id == user_id, Workspace.deleted_at.is_(None))
    )
    return {ws: WorkspaceRole(role) for ws, role in rows.all()}


def check_csrf(request: Request) -> None:
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or not constant_time_eq(cookie, header):
        raise ProblemError(403, ErrorCode.CSRF_FAILED)


async def _pat_principal(request: Request, db: AsyncSession, token: str) -> Principal:
    svc = services(request)
    if parse_pat(token) is None:
        raise ProblemError(401, ErrorCode.UNAUTHENTICATED, "Malformed bearer token")
    row = (
        await db.execute(select(ApiToken).where(ApiToken.token_hash == pat_hash(token)))
    ).scalar_one_or_none()
    if row is None:
        raise ProblemError(401, ErrorCode.UNAUTHENTICATED)
    now = datetime.now(UTC)
    if row.revoked_at is not None:
        raise ProblemError(401, ErrorCode.TOKEN_REVOKED)
    if row.expires_at is not None and row.expires_at <= now:
        raise ProblemError(401, ErrorCode.TOKEN_EXPIRED, "Personal access token expired")
    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise ProblemError(401, ErrorCode.TOKEN_REVOKED)
    roles = await load_roles(db, user.id)
    role = roles.get(row.workspace_id)
    if role is None:
        raise ProblemError(401, ErrorCode.TOKEN_REVOKED, "Token workspace membership ended")
    if role in MFA_ROLES and (user.totp_enabled_at is None or not row.mfa_verified):
        # SEC-auth-01 residual: owner/admin power through a PAT needs 2FA enabled on the account
        # *now* and the PAT minted from a 2FA-verified session. Anything else acts as a member.
        role = WorkspaceRole.MEMBER
    path = request.url.path
    if path.startswith(f"{API_PREFIX}/admin") or (
        path.startswith(f"{API_PREFIX}/auth/") and path != f"{API_PREFIX}/auth/me"
    ):
        raise ProblemError(403, ErrorCode.FORBIDDEN, "Personal access tokens cannot call this endpoint")
    ip = getattr(request.state, "client_ip", None)
    if row.last_used_at is None or now - row.last_used_at > timedelta(seconds=60) or row.last_used_ip != ip:
        await db.execute(
            update(ApiToken).where(ApiToken.id == row.id).values(last_used_at=now, last_used_ip=ip)
        )
        await db.commit()
    _ = svc
    return Principal(
        user_id=user.id,
        workspace_ids_roles={row.workspace_id: role},
        auth_method="pat",
        token_scopes=expand_scopes(list(row.scopes)),
        token_workspace_id=row.workspace_id,
        mfa_verified=False,
        token_id=row.id,
        is_platform_admin=False,  # PATs never carry platform-admin power
        mfa_enabled=user.totp_enabled_at is not None,
        email=user.email,
    )


async def _session_principal(request: Request, db: AsyncSession, access: str) -> Principal:
    svc = services(request)
    try:
        claims = svc.jwt.decode(access)
    except AccessTokenExpiredError as e:
        raise ProblemError(401, ErrorCode.TOKEN_EXPIRED) from e
    except AccessTokenInvalidError as e:
        raise ProblemError(401, ErrorCode.UNAUTHENTICATED) from e
    now = datetime.now(UTC)
    sess = (
        await db.execute(
            select(DbSession).where(DbSession.family_id == claims.session_id, DbSession.rotated_at.is_(None))
        )
    ).scalar_one_or_none()
    if sess is None or sess.user_id != claims.user_id or sess.revoked_at is not None:
        raise ProblemError(401, ErrorCode.SESSION_REVOKED)
    if sess.expires_at <= now:
        raise ProblemError(401, ErrorCode.SESSION_REVOKED, "Session expired")
    user = await db.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise ProblemError(401, ErrorCode.SESSION_REVOKED)
    if request.method in UNSAFE_METHODS:
        check_csrf(request)
    roles = await load_roles(db, user.id)
    enrol = user.totp_enabled_at is None and mfa_required_for(user, roles)
    principal = Principal(
        user_id=user.id,
        workspace_ids_roles=roles,
        auth_method="session",
        token_scopes=frozenset(),
        token_workspace_id=None,
        mfa_verified=sess.mfa_verified,
        session_id=sess.family_id,
        is_platform_admin=user.is_platform_admin,
        mfa_enabled=user.totp_enabled_at is not None,
        mfa_enrollment_required=enrol,
        email=user.email,
    )
    allowed = request.url.path.startswith(_ENROLMENT_ALLOWED)
    if enrol and not allowed:
        raise ProblemError(403, ErrorCode.MFA_ENROLLMENT_REQUIRED)
    if (
        not allowed
        and user.totp_enabled_at is not None
        and not sess.mfa_verified
        and mfa_required_for(user, roles)
    ):
        raise ProblemError(403, ErrorCode.MFA_REAUTH_REQUIRED)
    await _confirm_refresh(db, sess, claims, now)
    return principal


async def _confirm_refresh(db: AsyncSession, sess: DbSession, claims: AccessClaims, now: datetime) -> None:
    """Record that the browser holds the cookies of the current refresh row (QC-e2e-07).

    Only an access token issued in the same response as that row (``rid``) proves it. Once
    ``last_used_at`` moved past the rotation time, presenting the predecessor is token reuse.
    """
    if claims.refresh_id is None or claims.refresh_id != sess.id:
        return
    if sess.last_used_at > datetime.fromtimestamp(claims.issued_at + 2, UTC):
        return  # already confirmed
    await db.execute(update(DbSession).where(DbSession.id == sess.id).values(last_used_at=now))
    await db.commit()


async def principal_still_valid(db: AsyncSession, principal: Principal, workspace_id: uuid.UUID) -> bool:
    """Re-check a long-lived request (SSE, SEC-auth-03): credential alive, user active, still a member."""
    now = datetime.now(UTC)
    if principal.auth_method == "session":
        sess = (
            await db.execute(
                select(DbSession).where(
                    DbSession.family_id == principal.session_id, DbSession.rotated_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        if sess is None or sess.revoked_at is not None or sess.expires_at <= now:
            return False
    else:
        tok = await db.get(ApiToken, principal.token_id) if principal.token_id else None
        if tok is None or tok.revoked_at is not None:
            return False
        if tok.expires_at is not None and tok.expires_at <= now:
            return False
    user = await db.get(User, principal.user_id)
    if user is None or not user.is_active:
        return False
    return workspace_id in await load_roles(db, principal.user_id)


class StreamAuthGuard:
    """Periodic re-authorization of a server-sent event stream (SEC-auth-03).

    ``await guard.ok()`` is cheap to call on every loop iteration: it re-checks
    :func:`principal_still_valid` at most every ``recheck_s`` seconds (in a fresh DB session, so
    the stream holds no pooled connection in between) and returns False for good once the
    credential or membership is gone, a check fails, or the stream is older than ``max_lifetime_s``.
    """

    def __init__(
        self,
        principal: Principal,
        workspace_id: uuid.UUID,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        recheck_s: float,
        max_lifetime_s: float,
    ) -> None:
        self.principal = principal
        self.workspace_id = workspace_id
        self._maker = sessionmaker
        self.recheck_s = recheck_s
        self.max_lifetime_s = max_lifetime_s
        self._started = self._checked = time.monotonic()
        self._closed = False

    @classmethod
    def for_request(
        cls,
        request: Request,
        principal: Principal,
        workspace_id: uuid.UUID,
        sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    ) -> StreamAuthGuard:
        svc: Services | None = getattr(request.app.state, "services", None)
        maker = sessionmaker or (svc.db.sessionmaker if svc is not None else None)
        if maker is None:  # pragma: no cover - every app has one of the two
            raise RuntimeError("no sessionmaker for the stream auth guard")
        settings = svc.settings if svc is not None else None
        return cls(
            principal,
            workspace_id,
            maker,
            recheck_s=settings.sse_auth_recheck_s if settings else 15.0,
            max_lifetime_s=settings.sse_max_lifetime_s if settings else 900.0,
        )

    async def ok(self) -> bool:
        if self._closed:
            return False
        now = time.monotonic()
        if now - self._started >= self.max_lifetime_s:
            self._closed = True
        elif now - self._checked >= self.recheck_s:
            self._checked = now
            try:
                async with self._maker() as db:
                    valid = await principal_still_valid(db, self.principal, self.workspace_id)
            except (SQLAlchemyError, OSError):
                valid = False  # fail closed: the client reconnects and is authorized afresh
            self._closed = not valid
        return not self._closed


async def current_principal(request: Request, db: AsyncSession = Depends(get_db)) -> Principal:
    cached = getattr(request.state, "principal", None)
    if isinstance(cached, Principal):
        return cached
    authz = request.headers.get("Authorization")
    if authz:
        scheme, _, token = authz.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise ProblemError(401, ErrorCode.UNAUTHENTICATED, "Unsupported Authorization scheme")
        principal = await _pat_principal(request, db, token.strip())
    else:
        access = request.cookies.get(ACCESS_COOKIE)
        if not access:
            raise ProblemError(401, ErrorCode.UNAUTHENTICATED)
        principal = await _session_principal(request, db, access)
    request.state.principal = principal
    return principal


async def session_principal(principal: Principal = Depends(current_principal)) -> Principal:
    if principal.auth_method != "session":
        raise ProblemError(403, ErrorCode.FORBIDDEN, "This endpoint requires a browser session")
    return principal


def require_scope(scope: PatScope | str) -> Callable[..., Awaitable[Principal]]:
    async def dep(principal: Principal = Depends(current_principal)) -> Principal:
        if not principal.has_scope(scope):
            raise ProblemError(403, ErrorCode.INSUFFICIENT_SCOPE, params={"scope": str(scope)})
        return principal

    return dep


def ensure_role(principal: Principal, workspace_id: uuid.UUID, min_role: WorkspaceRole) -> WorkspaceRole:
    if principal.token_workspace_id is not None and principal.token_workspace_id != workspace_id:
        raise ProblemError(403, ErrorCode.FORBIDDEN, "Token is bound to another workspace")
    role = principal.role_in(workspace_id)
    if role is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    if ROLE_RANK[role] < ROLE_RANK[min_role]:
        raise ProblemError(403, ErrorCode.FORBIDDEN, params={"required_role": min_role.value})
    return role


def require_role(
    workspace_id: uuid.UUID | str = "workspace_id", min_role: WorkspaceRole = WorkspaceRole.VIEWER
) -> Callable[..., Awaitable[Principal]]:
    async def dep(request: Request, principal: Principal = Depends(current_principal)) -> Principal:
        if isinstance(workspace_id, uuid.UUID):
            ws = workspace_id
        else:
            raw = request.path_params.get(workspace_id) or request.query_params.get(workspace_id)
            try:
                ws = uuid.UUID(str(raw))
            except ValueError as e:
                raise ProblemError(404, ErrorCode.NOT_FOUND) from e
        ensure_role(principal, ws, min_role)
        return principal

    return dep


async def platform_admin(request: Request, principal: Principal = Depends(session_principal)) -> Principal:
    """Platform admin with a 2FA-verified session (+ Cloudflare Access assertion when enabled)."""
    svc = services(request)
    if svc.cf_access is not None:
        await svc.cf_access.verify_request(request)
    if not principal.is_platform_admin:
        raise ProblemError(403, ErrorCode.FORBIDDEN)
    if not principal.mfa_verified:
        raise ProblemError(403, ErrorCode.MFA_REAUTH_REQUIRED)
    return principal
