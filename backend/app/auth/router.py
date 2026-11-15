"""/api/v1/auth/* (OpenAPI tag ``auth``)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Path, Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import mfa, one_time
from app.auth.emails import reset_email, verify_email
from app.auth.jwt import AccessTokenExpiredError, AccessTokenInvalidError
from app.auth.lockout import ensure_not_locked, register_failure, register_success
from app.auth.pat import READ_SCOPES, generate_pat, pat_hash
from app.auth.schemas import (
    ApiTokenCreate,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginSecondFactorRequest,
    PasswordConfirmRequest,
    RegisterInviteRequest,
    ResetPasswordRequest,
    TokenRequest,
    TotpCodeRequest,
    TotpDisableRequest,
)
from app.auth.serializers import api_token_out, iso_req, membership_out, memberships_for, user_out
from app.auth.sessions import (
    IssuedSession,
    clear_session_cookies,
    create_session,
    current_row,
    ensure_csrf_cookie,
    revoke_family,
    revoke_user_sessions,
    set_access_cookie,
    set_session_cookies,
)
from app.core.audit import AuditAction, record
from app.core.crypto import random_token, sha256
from app.core.deps import (
    ACCESS_COOKIE,
    MFA_ROLES,
    REFRESH_COOKIE,
    Principal,
    check_csrf,
    current_principal,
    ensure_role,
    get_db,
    load_roles,
    mfa_required_for,
    services,
    session_principal,
)
from app.core.email import send_safely
from app.core.errors import VALIDATION_400, ErrorCode, ProblemError
from app.db.models import ApiToken, OneTimeTokenPurpose, SessionRevokeReason, User, WorkspaceRole
from app.db.models import Session as DbSession
from app.workspaces.invites import accept_invite, lookup_invite

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

InviteToken = Path(min_length=32, max_length=128)


def _ip(request: Request) -> str | None:
    ip = getattr(request.state, "client_ip", None)
    return str(ip) if ip else None


async def _user_by_email(db: AsyncSession, email: str, *, for_update: bool = False) -> User | None:
    stmt = select(User).where(func.lower(User.email) == email.lower())
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def _finish_login(
    db: AsyncSession, request: Request, response: Response, user: User, *, mfa_verified: bool
) -> dict[str, Any]:
    svc = services(request)
    register_success(user)
    issued = await create_session(db, svc, request, user.id, mfa_verified=mfa_verified)
    await record(
        AuditAction.AUTH_LOGIN, db=db, actor=user.id, target_type="session", target_id=issued.family_id
    )
    roles = await load_roles(db, user.id)
    await db.commit()
    set_session_cookies(response, request, issued)
    enrol = user.totp_enabled_at is None and mfa_required_for(user, roles)
    return {"status": "ok", "user": user_out(user), "mfa_enrollment_required": enrol}


async def _fail_login(db: AsyncSession, request: Request, user: User | None, email: str, reason: str) -> None:
    svc = services(request)
    locked = False
    if user is not None:
        locked = register_failure(user, svc.settings)
    await record(
        AuditAction.AUTH_LOGIN_FAILED,
        db=db,
        actor=user.id if user else None,
        target_type="user",
        target_id=user.id if user else None,
        outcome="failure",
        details={"reason": reason, "email_sha256": sha256(email.lower()).hex()[:16]},
    )
    if locked and user is not None:
        await record(
            AuditAction.AUTH_ACCOUNT_LOCKED,
            db=db,
            actor=user.id,
            target_type="user",
            target_id=user.id,
            details={"failed_count": user.failed_login_count},
        )
    await db.commit()


def _is_locked(user: User) -> bool:
    try:
        ensure_not_locked(user)
    except ProblemError:
        return True
    return False


# --------------------------------------------------------------------------------------------
# Invites (public preview, register, accept)
#
# The token travels in the request body (SEC-auth-04): URL paths end up in the API and Caddy access
# logs. The path-token variants remain for old clients (deprecated); their paths are redacted in
# both logs.
# --------------------------------------------------------------------------------------------
@router.post("/invites/preview", operation_id="previewInvite", openapi_extra=VALIDATION_400)
async def preview_invite(
    body: TokenRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    return await _invite_preview(request, db, body.token)


@router.get(
    "/invites/{token}", operation_id="getInvitePreview", openapi_extra=VALIDATION_400, deprecated=True
)
async def get_invite_preview(
    request: Request, token: str = InviteToken, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    return await _invite_preview(request, db, token)


async def _invite_preview(request: Request, db: AsyncSession, token: str) -> dict[str, Any]:
    svc = services(request)
    await svc.limiter.hit(
        "invite:preview", _ip(request), limit=svc.settings.rl_invite_preview_per_min, window_s=60
    )
    inv, ws = await lookup_invite(db, token)
    inviter = await db.get(User, inv.invited_by) if inv.invited_by else None
    exists = await _user_by_email(db, inv.email) is not None
    return {
        "workspace_name": ws.name,
        "email": inv.email,
        "role": WorkspaceRole(inv.role).value,
        "invited_by": inviter.display_name if inviter else None,
        "expires_at": iso_req(inv.expires_at),
        "account_exists": exists,
    }


@router.post("/register-invite", operation_id="registerWithInvite", status_code=201)
async def register_with_invite(
    body: RegisterInviteRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    svc = services(request)
    await svc.limiter.hit("register:ip", _ip(request), limit=svc.settings.rl_login_ip_per_min, window_s=60)
    await svc.turnstile.verify(body.turnstile_token, _ip(request))
    inv, ws = await lookup_invite(db, body.invite_token, for_update=True)
    if await _user_by_email(db, inv.email) is not None:
        raise ProblemError(409, ErrorCode.EMAIL_TAKEN)
    svc.passwords.check_policy(body.password, email=inv.email, display_name=body.display_name)
    now = datetime.now(UTC)
    user = User(
        email=inv.email.lower(),
        display_name=body.display_name.strip(),
        password_hash=svc.passwords.hash(body.password),
        password_changed_at=now,
        email_verified_at=now,  # the invite link proves control of the address
        locale=body.locale or "vi",
    )
    db.add(user)
    await db.flush()
    await accept_invite(db, inv, user)
    await record(
        AuditAction.USER_REGISTERED,
        db=db,
        actor=user.id,
        workspace_id=ws.id,
        target_type="user",
        target_id=user.id,
    )
    await record(
        AuditAction.INVITE_ACCEPTED,
        db=db,
        actor=user.id,
        workspace_id=ws.id,
        target_type="invite",
        target_id=inv.id,
        details={"role": WorkspaceRole(inv.role).value},
    )
    await db.refresh(user)
    return await _finish_login(db, request, response, user, mfa_verified=False)


@router.post("/invites/accept", operation_id="acceptInviteToken", openapi_extra=VALIDATION_400)
async def accept_invite_token(
    body: TokenRequest,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _accept_invite(db, principal, body.token)


@router.post(
    "/invites/{token}/accept", operation_id="acceptInvite", openapi_extra=VALIDATION_400, deprecated=True
)
async def accept_invite_route(
    token: str = InviteToken,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _accept_invite(db, principal, token)


async def _accept_invite(db: AsyncSession, principal: Principal, token: str) -> dict[str, Any]:
    inv, ws = await lookup_invite(db, token, for_update=True)
    user = await db.get(User, principal.user_id)
    if user is None:  # pragma: no cover - principal implies the user exists
        raise ProblemError(401, ErrorCode.UNAUTHENTICATED)
    if user.email.lower() != inv.email.lower():
        raise ProblemError(403, ErrorCode.INVITE_EMAIL_MISMATCH)
    m = await accept_invite(db, inv, user)
    await record(
        AuditAction.INVITE_ACCEPTED,
        db=db,
        actor=principal,
        workspace_id=ws.id,
        target_type="invite",
        target_id=inv.id,
        details={"role": WorkspaceRole(inv.role).value},
    )
    await db.commit()
    return membership_out(ws, m.role)


# --------------------------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------------------------
@router.post("/login", operation_id="login", openapi_extra=VALIDATION_400)
async def login(
    body: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    svc = services(request)
    s = svc.settings
    email = str(body.email).lower()
    await svc.limiter.hit("login:ip", _ip(request), limit=s.rl_login_ip_per_min, window_s=60)
    await svc.limiter.hit("login:email", email, limit=s.rl_login_email_per_min, window_s=60)
    await svc.turnstile.verify(body.turnstile_token, _ip(request))
    user = await _user_by_email(db, email, for_update=True)
    if user is None:
        svc.passwords.dummy_verify(body.password)
        await _fail_login(db, request, None, email, "unknown_email")
        raise ProblemError(401, ErrorCode.INVALID_CREDENTIALS)
    if _is_locked(user):
        # Same answer (and the same argon2 work) as a wrong password or an unknown email: a 423 here
        # would tell anyone that the address has an account (SEC-auth-06). Attempts while locked do
        # not extend the lock.
        svc.passwords.verify(user.password_hash, body.password)
        await record(
            AuditAction.AUTH_LOGIN_FAILED,
            db=db,
            actor=user.id,
            target_type="user",
            target_id=user.id,
            outcome="denied",
            details={"reason": "locked", "email_sha256": sha256(email).hex()[:16]},
        )
        await db.commit()
        raise ProblemError(401, ErrorCode.INVALID_CREDENTIALS)
    if not svc.passwords.verify(user.password_hash, body.password):
        await _fail_login(db, request, user, email, "bad_password")
        raise ProblemError(401, ErrorCode.INVALID_CREDENTIALS)
    if not user.is_active:
        await _fail_login(db, request, user, email, "disabled")
        raise ProblemError(403, ErrorCode.ACCOUNT_DISABLED)
    if svc.passwords.needs_rehash(user.password_hash):
        user.password_hash = svc.passwords.hash(body.password)
    if user.totp_enabled_at is not None:
        token, _ = await one_time.issue(db, user.id, OneTimeTokenPurpose.MFA_CHALLENGE, s.mfa_token_ttl_s)
        await db.commit()
        return {"status": "mfa_required", "mfa_token": token}
    return await _finish_login(db, request, response, user, mfa_verified=False)


@router.post("/login/2fa", operation_id="loginSecondFactor", openapi_extra=VALIDATION_400)
async def login_second_factor(
    body: LoginSecondFactorRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    svc = services(request)
    await svc.limiter.hit("login2fa:ip", _ip(request), limit=svc.settings.rl_login_ip_per_min, window_s=60)
    challenge = await one_time.find_valid(db, body.mfa_token, OneTimeTokenPurpose.MFA_CHALLENGE)
    if challenge is None:
        raise ProblemError(401, ErrorCode.MFA_TOKEN_INVALID)
    user = (await db.execute(select(User).where(User.id == challenge.user_id).with_for_update())).scalar_one()
    if not user.is_active or user.totp_enabled_at is None:
        raise ProblemError(401, ErrorCode.MFA_TOKEN_INVALID)
    ensure_not_locked(user)
    used_recovery = False
    if body.code is not None:
        ok = mfa.verify_user_code(svc.cipher, user, body.code)
    else:
        assert body.recovery_code is not None  # noqa: S101 - validated: exactly one of code/recovery_code
        ok = await mfa.use_recovery_code(db, svc.passwords, user.id, body.recovery_code)
        used_recovery = ok
    if not ok:
        await _fail_login(db, request, user, user.email, "bad_second_factor")
        raise ProblemError(401, ErrorCode.MFA_INVALID_CODE)
    challenge.used_at = datetime.now(UTC)
    if used_recovery:
        await record(
            AuditAction.AUTH_RECOVERY_CODE_USED, db=db, actor=user.id, target_type="user", target_id=user.id
        )
    result = await _finish_login(db, request, response, user, mfa_verified=True)
    result["recovery_codes_remaining"] = await mfa.remaining_recovery_codes(db, user.id)
    return result


# --------------------------------------------------------------------------------------------
# Refresh / logout / me / config
# --------------------------------------------------------------------------------------------
@router.post(
    "/refresh",
    operation_id="refreshSession",
    openapi_extra=VALIDATION_400,
    status_code=204,
    response_class=Response,
)
async def refresh_session(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> None:
    svc = services(request)
    s = svc.settings
    check_csrf(request)
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise ProblemError(401, ErrorCode.UNAUTHENTICATED)
    row = (
        await db.execute(
            select(DbSession).where(DbSession.refresh_token_hash == sha256(token)).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise ProblemError(401, ErrorCode.UNAUTHENTICATED)
    now = datetime.now(UTC)
    if row.revoked_at is not None:
        raise ProblemError(401, ErrorCode.SESSION_REVOKED)
    # Rows to retire in favour of the new successor (the presented row, plus its unconfirmed head).
    retire = [row]
    if row.rotated_at is not None:
        head = await _unconfirmed_head(db, row)
        if head is not None:
            # The response that carried the successor never reached the browser (aborted by a page
            # reload / navigation, QC-e2e-07) and nobody has used it since: the successor is
            # provably unused, so this is not token theft. Rotate again from here.
            retire.append(head)
        elif now - row.rotated_at <= timedelta(seconds=s.refresh_reuse_grace_s):
            # Concurrent refresh from another tab whose successor is already in use: the browser
            # already holds (or is about to receive) the successor cookies. Nothing is issued here.
            return None
        else:
            await _refresh_reuse(db, row)
    if row.expires_at <= now or row.idle_expires_at <= now:
        await revoke_family(db, row.family_id, SessionRevokeReason.EXPIRED)
        await db.commit()
        raise ProblemError(401, ErrorCode.SESSION_REVOKED, "Session expired")
    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise ProblemError(401, ErrorCode.SESSION_REVOKED)
    new_refresh = random_token(32)
    successor = DbSession(
        id=uuid.uuid4(),
        user_id=row.user_id,
        family_id=row.family_id,
        refresh_token_hash=sha256(new_refresh),
        expires_at=row.expires_at,
        idle_expires_at=min(row.expires_at, now + timedelta(seconds=s.session_idle_ttl_s)),
        last_used_at=now,  # == rotated_at below: "unconfirmed" until a request carries its rid
        mfa_verified=row.mfa_verified,
        ip=_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
    )
    db.add(successor)
    await db.flush()
    for r in retire:
        r.rotated_at = now
        r.replaced_by_id = successor.id
    await db.commit()
    issued = IssuedSession(
        family_id=row.family_id,
        access_token=svc.jwt.issue(row.user_id, row.family_id, row.mfa_verified, refresh_id=successor.id),
        refresh_token=new_refresh,
        csrf_token=request.cookies.get("hb_csrf") or random_token(32),
        expires_at=row.expires_at,
    )
    set_session_cookies(response, request, issued)
    return None


async def _unconfirmed_head(db: AsyncSession, row: DbSession) -> DbSession | None:
    """The current refresh row of ``row``'s family if it directly replaced ``row`` and was never used.

    "Used" means a request carried an access token issued together with it (``rid`` claim, see
    ``deps._confirm_refresh``), which moves its ``last_used_at`` past ``row.rotated_at``. Presenting
    ``row`` after that is genuine reuse; before it, the browser simply never got the successor.
    """
    if row.replaced_by_id is None or row.rotated_at is None:
        return None
    head = (
        await db.execute(select(DbSession).where(DbSession.id == row.replaced_by_id).with_for_update())
    ).scalar_one_or_none()
    if (
        head is None
        or head.family_id != row.family_id
        or head.rotated_at is not None
        or head.revoked_at is not None
        or head.last_used_at > row.rotated_at
    ):
        return None
    return head


async def _refresh_reuse(db: AsyncSession, row: DbSession) -> NoReturn:
    await revoke_family(db, row.family_id, SessionRevokeReason.REFRESH_REUSE)
    await record(
        AuditAction.AUTH_REFRESH_REUSE,
        db=db,
        actor=row.user_id,
        target_type="session",
        target_id=row.family_id,
        outcome="denied",
    )
    await db.commit()
    raise ProblemError(401, ErrorCode.REFRESH_REUSE_DETECTED)


@router.post(
    "/logout", operation_id="logout", openapi_extra=VALIDATION_400, status_code=204, response_class=Response
)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> None:
    svc = services(request)
    family: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    access = request.cookies.get(ACCESS_COOKIE)
    if access:
        try:
            claims = svc.jwt.decode(access, verify_exp=False)
            family, user_id = claims.session_id, claims.user_id
        except (AccessTokenInvalidError, AccessTokenExpiredError):
            family = None
    refresh = request.cookies.get(REFRESH_COOKIE)
    if family is None and refresh:
        row = (
            await db.execute(select(DbSession).where(DbSession.refresh_token_hash == sha256(refresh)))
        ).scalar_one_or_none()
        if row is not None:
            family, user_id = row.family_id, row.user_id
    if family is not None:
        check_csrf(request)
        n = await revoke_family(db, family, SessionRevokeReason.LOGOUT, user_id=user_id)
        if n:
            await record(
                AuditAction.AUTH_LOGOUT, db=db, actor=user_id, target_type="session", target_id=family
            )
        await db.commit()
    clear_session_cookies(response, request)
    return None


@router.get("/me", operation_id="getMe", openapi_extra=VALIDATION_400)
async def get_me(
    request: Request,
    response: Response,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    user = await db.get(User, principal.user_id)
    if user is None:  # pragma: no cover
        raise ProblemError(401, ErrorCode.UNAUTHENTICATED)
    memberships = await memberships_for(db, user.id)
    out: dict[str, Any] = {
        "user": user_out(user),
        "memberships": memberships,
        "auth_method": principal.auth_method,
        "session_id": str(principal.session_id) if principal.session_id else None,
        "mfa_verified": principal.mfa_verified,
        "mfa_enrollment_required": principal.mfa_enrollment_required,
        "token": None,
    }
    if principal.auth_method == "pat" and principal.token_id is not None:
        tok = await db.get(ApiToken, principal.token_id)
        out["token"] = api_token_out(tok) if tok else None
        ws_id = principal.token_workspace_id
        out["memberships"] = [m for m in memberships if m["workspace_id"] == str(ws_id)]
    else:
        ensure_csrf_cookie(response, request)
    return out


@router.get("/config", operation_id="getAuthConfig", openapi_extra=VALIDATION_400)
async def get_auth_config(request: Request) -> dict[str, Any]:
    s = services(request).settings
    return {
        "turnstile_site_key": s.turnstile_site_key,
        "email_delivery_enabled": services(request).email.enabled,
        "password_min_length": 12,
        "supported_locales": ["vi", "en"],
    }


# --------------------------------------------------------------------------------------------
# Email verification, password reset / change
# --------------------------------------------------------------------------------------------
@router.post(
    "/email/verify",
    operation_id="verifyEmail",
    openapi_extra=VALIDATION_400,
    status_code=204,
    response_class=Response,
)
async def verify_email_route(body: TokenRequest, db: AsyncSession = Depends(get_db)) -> None:
    tok = await one_time.consume(db, body.token, OneTimeTokenPurpose.EMAIL_VERIFY)
    if tok is None:
        raise ProblemError(400, ErrorCode.ONE_TIME_TOKEN_INVALID)
    user = await db.get(User, tok.user_id)
    if user is not None and user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
    await db.commit()
    return None


@router.post(
    "/email/resend",
    operation_id="resendVerificationEmail",
    openapi_extra=VALIDATION_400,
    status_code=202,
    response_class=Response,
)
async def resend_verification(
    request: Request, principal: Principal = Depends(session_principal), db: AsyncSession = Depends(get_db)
) -> Response:
    svc = services(request)
    await svc.limiter.hit(
        "verify:resend", str(principal.user_id), limit=svc.settings.rl_resend_per_hour, window_s=3600
    )
    user = await db.get(User, principal.user_id)
    if user is not None and user.email_verified_at is None:
        token, _ = await one_time.issue(
            db, user.id, OneTimeTokenPurpose.EMAIL_VERIFY, svc.settings.email_verify_ttl_s
        )
        await db.commit()
        url = svc.settings.link(svc.settings.verify_email_path, token)
        await send_safely(svc.email, verify_email(user.email, user.locale, url))
    return Response(status_code=202)


@router.post(
    "/password/forgot",
    operation_id="forgotPassword",
    openapi_extra=VALIDATION_400,
    status_code=202,
    response_class=Response,
)
async def forgot_password(
    body: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> Response:
    svc = services(request)
    s = svc.settings
    email = str(body.email).lower()
    await svc.limiter.hit("forgot:ip", _ip(request), limit=s.rl_forgot_per_hour * 4, window_s=3600)
    await svc.turnstile.verify(body.turnstile_token, _ip(request))
    user = await _user_by_email(db, email)
    try:
        await svc.limiter.hit("forgot:email", email, limit=s.rl_forgot_per_hour, window_s=3600)
    except ProblemError:
        return Response(status_code=202)  # silently drop (no enumeration, no mail bombing)
    if user is not None and user.is_active:
        token, _ = await one_time.issue(
            db, user.id, OneTimeTokenPurpose.PASSWORD_RESET, s.password_reset_ttl_s
        )
        await record(
            AuditAction.AUTH_PASSWORD_RESET_REQUESTED,
            db=db,
            actor=None,
            target_type="user",
            target_id=user.id,
            details={"delivery": svc.email.provider},
        )
        await db.commit()
        await send_safely(
            svc.email, reset_email(user.email, user.locale, s.link(s.reset_password_path, token))
        )
    return Response(status_code=202)


@router.post("/password/reset", operation_id="resetPassword", status_code=204, response_class=Response)
async def reset_password(
    body: ResetPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> None:
    svc = services(request)
    await svc.limiter.hit("reset:ip", _ip(request), limit=svc.settings.rl_login_ip_per_min, window_s=60)
    tok = await one_time.find_valid(db, body.token, OneTimeTokenPurpose.PASSWORD_RESET)
    if tok is None:
        raise ProblemError(400, ErrorCode.ONE_TIME_TOKEN_INVALID)
    user = await db.get(User, tok.user_id)
    if user is None or not user.is_active:
        raise ProblemError(400, ErrorCode.ONE_TIME_TOKEN_INVALID)
    svc.passwords.check_policy(body.new_password, email=user.email, display_name=user.display_name)
    now = datetime.now(UTC)
    tok.used_at = now
    user.password_hash = svc.passwords.hash(body.new_password)
    user.password_changed_at = now
    user.failed_login_count = 0
    user.locked_until = None
    if user.email_verified_at is None:
        user.email_verified_at = now  # the link was delivered to / generated for this address
    await revoke_user_sessions(db, user.id, SessionRevokeReason.PASSWORD_CHANGED)
    await record(AuditAction.AUTH_PASSWORD_RESET, db=db, actor=user.id, target_type="user", target_id=user.id)
    await db.commit()
    return None


@router.post("/password/change", operation_id="changePassword", status_code=204, response_class=Response)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = services(request)
    user = await _locked_user(db, principal.user_id)
    await _reauth_guard(request, user)
    if not svc.passwords.verify(user.password_hash, body.current_password):
        await _reauth_failed(db, request, principal, user, _BAD_PASSWORD, ErrorCode.PASSWORD_INCORRECT)
    svc.passwords.check_policy(body.new_password, email=user.email, display_name=user.display_name)
    user.password_hash = svc.passwords.hash(body.new_password)
    user.password_changed_at = datetime.now(UTC)
    await revoke_user_sessions(
        db, user.id, SessionRevokeReason.PASSWORD_CHANGED, except_family=principal.session_id
    )
    await record(
        AuditAction.AUTH_PASSWORD_CHANGED, db=db, actor=principal, target_type="user", target_id=user.id
    )
    await db.commit()
    return None


# --------------------------------------------------------------------------------------------
# 2FA
# --------------------------------------------------------------------------------------------
async def _locked_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    return (await db.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one()


_BAD_PASSWORD = "reauth_bad_password"  # noqa: S105 - audit reason, not a secret


async def _reauth_guard(request: Request, user: User) -> None:
    """Rate limit + lockout for password / TOTP checks by a logged-in session (SEC-auth-02).

    The failure counter is the login one, so guessing from a stolen session locks the account
    exactly like guessing at /auth/login. 423 is fine here: the caller is already authenticated.
    """
    svc = services(request)
    await svc.limiter.hit("reauth:user", str(user.id), limit=svc.settings.rl_reauth_per_15min, window_s=900)
    ensure_not_locked(user)


async def _reauth_failed(
    db: AsyncSession, request: Request, principal: Principal, user: User, reason: str, code: ErrorCode
) -> NoReturn:
    svc = services(request)
    locked = register_failure(user, svc.settings)
    await record(
        AuditAction.AUTH_LOGIN_FAILED,
        db=db,
        actor=principal,
        target_type="user",
        target_id=user.id,
        outcome="failure",
        details={"reason": reason},
    )
    if locked:
        await record(
            AuditAction.AUTH_ACCOUNT_LOCKED,
            db=db,
            actor=principal,
            target_type="user",
            target_id=user.id,
            details={"failed_count": user.failed_login_count},
        )
    await db.commit()
    raise ProblemError(401, code)


@router.post("/2fa/totp/setup", operation_id="setupTotp", openapi_extra=VALIDATION_400)
async def setup_totp(
    body: PasswordConfirmRequest,
    request: Request,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = services(request)
    user = await _locked_user(db, principal.user_id)
    await _reauth_guard(request, user)
    if not svc.passwords.verify(user.password_hash, body.password):
        await _reauth_failed(db, request, principal, user, _BAD_PASSWORD, ErrorCode.PASSWORD_INCORRECT)
    if user.totp_enabled_at is not None:
        raise ProblemError(409, ErrorCode.MFA_ALREADY_ENABLED)
    secret = mfa.new_secret()
    user.totp_secret_enc = mfa.encrypt_secret(svc.cipher, user.id, secret)
    user.totp_last_used_step = None
    await db.commit()
    return {"secret": secret, "otpauth_uri": mfa.otpauth_uri(secret, user.email)}


@router.post("/2fa/totp/enable", operation_id="enableTotp", openapi_extra=VALIDATION_400)
async def enable_totp(
    body: TotpCodeRequest,
    request: Request,
    response: Response,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = services(request)
    user = await _locked_user(db, principal.user_id)
    if user.totp_enabled_at is not None:
        raise ProblemError(409, ErrorCode.MFA_ALREADY_ENABLED)
    if user.totp_secret_enc is None:
        raise ProblemError(409, ErrorCode.CONFLICT, "Call /auth/2fa/totp/setup first")
    await _reauth_guard(request, user)
    if not mfa.verify_user_code(svc.cipher, user, body.code):
        await _reauth_failed(db, request, principal, user, "bad_second_factor", ErrorCode.MFA_INVALID_CODE)
    user.totp_enabled_at = datetime.now(UTC)
    codes = await mfa.replace_recovery_codes(db, svc.passwords, user.id)
    sess = await current_row(db, principal.session_id) if principal.session_id else None
    if sess is not None:
        sess.mfa_verified = True
    # Every other session was opened without 2FA and must not keep working (SEC-auth-01).
    revoked = await revoke_user_sessions(
        db, user.id, SessionRevokeReason.USER_REVOKED, except_family=principal.session_id
    )
    # Every PAT of the user was minted without 2FA and is revoked too (SEC-auth-01 residual): the
    # user mints new ones from this 2FA-verified session.
    now = datetime.now(UTC)
    tokens_revoked = (
        await db.execute(
            update(ApiToken)
            .where(ApiToken.user_id == user.id, ApiToken.revoked_at.is_(None))
            .values(revoked_at=now)
            .returning(ApiToken.id)
        )
    ).all()
    await record(
        AuditAction.AUTH_MFA_ENABLED,
        db=db,
        actor=principal,
        target_type="user",
        target_id=user.id,
        details={"other_sessions_revoked": revoked, "api_tokens_revoked": len(tokens_revoked)},
    )
    await db.commit()
    if sess is not None and principal.session_id is not None:
        set_access_cookie(
            response, request, svc.jwt.issue(user.id, principal.session_id, True), sess.expires_at
        )
    return {"recovery_codes": codes, "api_tokens_revoked": len(tokens_revoked)}


@router.post(
    "/2fa/totp/disable",
    operation_id="disableTotp",
    openapi_extra=VALIDATION_400,
    status_code=204,
    response_class=Response,
)
async def disable_totp(
    body: TotpDisableRequest,
    request: Request,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = services(request)
    user = await _locked_user(db, principal.user_id)
    await _reauth_guard(request, user)
    if not svc.passwords.verify(user.password_hash, body.password):
        await _reauth_failed(db, request, principal, user, _BAD_PASSWORD, ErrorCode.PASSWORD_INCORRECT)
    if user.totp_enabled_at is None:
        raise ProblemError(409, ErrorCode.CONFLICT, "Two-factor authentication is not enabled")
    if mfa_required_for(user, principal.workspace_ids_roles):
        raise ProblemError(409, ErrorCode.MFA_REQUIRED_BY_ROLE)
    if not mfa.verify_user_code(svc.cipher, user, body.code):
        await _reauth_failed(db, request, principal, user, "bad_second_factor", ErrorCode.MFA_INVALID_CODE)
    await mfa.clear_mfa(db, user)
    await record(AuditAction.AUTH_MFA_DISABLED, db=db, actor=principal, target_type="user", target_id=user.id)
    await db.commit()
    return None


@router.post("/2fa/recovery-codes", operation_id="regenerateRecoveryCodes", openapi_extra=VALIDATION_400)
async def regenerate_recovery_codes(
    body: TotpCodeRequest,
    request: Request,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    svc = services(request)
    user = await _locked_user(db, principal.user_id)
    if user.totp_enabled_at is None:
        raise ProblemError(409, ErrorCode.CONFLICT, "Two-factor authentication is not enabled")
    await _reauth_guard(request, user)
    if not mfa.verify_user_code(svc.cipher, user, body.code):
        await _reauth_failed(db, request, principal, user, "bad_second_factor", ErrorCode.MFA_INVALID_CODE)
    codes = await mfa.replace_recovery_codes(db, svc.passwords, user.id)
    await record(
        AuditAction.AUTH_RECOVERY_CODES_REGENERATED,
        db=db,
        actor=principal,
        target_type="user",
        target_id=user.id,
    )
    await db.commit()
    return {"recovery_codes": codes}


# --------------------------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------------------------
@router.get("/sessions", operation_id="listSessions", openapi_extra=VALIDATION_400)
async def list_sessions(
    principal: Principal = Depends(session_principal), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    now = datetime.now(UTC)
    starts = (
        select(DbSession.family_id, func.min(DbSession.created_at).label("started"))
        .where(DbSession.user_id == principal.user_id)
        .group_by(DbSession.family_id)
        .subquery()
    )
    rows = await db.execute(
        select(DbSession, starts.c.started)
        .join(starts, starts.c.family_id == DbSession.family_id)
        .where(
            DbSession.user_id == principal.user_id,
            DbSession.rotated_at.is_(None),
            DbSession.revoked_at.is_(None),
            DbSession.expires_at > now,
            DbSession.idle_expires_at > now,
        )
        .order_by(DbSession.last_used_at.desc())
    )
    items = [
        {
            "id": str(s.family_id),
            "created_at": iso_req(started),
            "last_used_at": iso_req(s.last_used_at),
            "expires_at": iso_req(s.expires_at),
            "ip": str(s.ip) if s.ip is not None else None,
            "user_agent": s.user_agent,
            "current": s.family_id == principal.session_id,
            "mfa_verified": s.mfa_verified,
        }
        for s, started in rows.all()
    ]
    return {"items": items}


@router.delete(
    "/sessions/{session_id}",
    operation_id="revokeSession",
    openapi_extra=VALIDATION_400,
    status_code=204,
    response_class=Response,
)
async def revoke_session(
    session_id: uuid.UUID,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    exists = (
        await db.execute(
            select(DbSession.id)
            .where(DbSession.family_id == session_id, DbSession.user_id == principal.user_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if exists is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    n = await revoke_family(db, session_id, SessionRevokeReason.USER_REVOKED, user_id=principal.user_id)
    if n:
        await record(
            AuditAction.AUTH_SESSION_REVOKED,
            db=db,
            actor=principal,
            target_type="session",
            target_id=session_id,
        )
    await db.commit()
    return None


@router.post(
    "/sessions/revoke-others",
    operation_id="revokeOtherSessions",
    openapi_extra=VALIDATION_400,
    status_code=204,
    response_class=Response,
)
async def revoke_other_sessions(
    principal: Principal = Depends(session_principal), db: AsyncSession = Depends(get_db)
) -> None:
    n = await revoke_user_sessions(
        db, principal.user_id, SessionRevokeReason.USER_REVOKED, except_family=principal.session_id
    )
    if n:
        await record(
            AuditAction.AUTH_SESSION_REVOKED,
            db=db,
            actor=principal,
            target_type="user",
            target_id=principal.user_id,
            details={"scope": "others", "count": n},
        )
    await db.commit()
    return None


# --------------------------------------------------------------------------------------------
# Personal access tokens
# --------------------------------------------------------------------------------------------
@router.get("/tokens", operation_id="listApiTokens", openapi_extra=VALIDATION_400)
async def list_api_tokens(
    principal: Principal = Depends(session_principal), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    rows = (
        (
            await db.execute(
                select(ApiToken)
                .where(ApiToken.user_id == principal.user_id)
                .order_by(ApiToken.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {"items": [api_token_out(t) for t in rows]}


@router.post("/tokens", operation_id="createApiToken", status_code=201)
async def create_api_token(
    body: ApiTokenCreate,
    request: Request,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    role = ensure_role(principal, body.workspace_id, WorkspaceRole.VIEWER)
    if principal.mfa_enabled and not principal.mfa_verified:
        raise ProblemError(403, ErrorCode.MFA_REAUTH_REQUIRED)
    if role in MFA_ROLES and not principal.mfa_verified:
        # Owner/admin PATs only from a 2FA-verified session (SEC-auth-01 residual).
        raise ProblemError(
            403,
            ErrorCode.MFA_ENROLLMENT_REQUIRED if not principal.mfa_enabled else ErrorCode.MFA_REAUTH_REQUIRED,
        )
    scopes = [s.value for s in body.scopes]
    if role == WorkspaceRole.VIEWER and not set(scopes) <= READ_SCOPES:
        raise ProblemError(403, ErrorCode.FORBIDDEN, "Viewers can only create read-only tokens")
    now = datetime.now(UTC)
    expires_at = None
    if body.expires_in_days is not None:
        expires_at = now + timedelta(days=body.expires_in_days)
    for _ in range(5):
        prefix, plaintext = generate_pat()
        clash = (await db.execute(select(ApiToken.id).where(ApiToken.prefix == prefix))).scalar_one_or_none()
        if clash is None:
            break
    else:  # pragma: no cover - 62^8 space
        raise ProblemError(500, ErrorCode.INTERNAL_ERROR)
    tok = ApiToken(
        user_id=principal.user_id,
        workspace_id=body.workspace_id,
        name=body.name.strip(),
        prefix=prefix,
        token_hash=pat_hash(plaintext),
        scopes=scopes,
        expires_at=expires_at,
        mfa_verified=principal.mfa_verified,
    )
    db.add(tok)
    await db.flush()
    await record(
        AuditAction.TOKEN_CREATED,
        db=db,
        actor=principal,
        workspace_id=body.workspace_id,
        target_type="api_token",
        target_id=tok.id,
        details={
            "scopes": scopes,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "name": tok.name,
        },
    )
    await db.commit()
    await db.refresh(tok)
    out = api_token_out(tok)
    out["token"] = plaintext
    return out


@router.delete(
    "/tokens/{token_id}",
    operation_id="revokeApiToken",
    openapi_extra=VALIDATION_400,
    status_code=204,
    response_class=Response,
)
async def revoke_api_token(
    token_id: uuid.UUID, principal: Principal = Depends(session_principal), db: AsyncSession = Depends(get_db)
) -> None:
    tok = (
        await db.execute(
            select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == principal.user_id)
        )
    ).scalar_one_or_none()
    if tok is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    if tok.revoked_at is None:
        tok.revoked_at = datetime.now(UTC)
        await record(
            AuditAction.TOKEN_REVOKED,
            db=db,
            actor=principal,
            workspace_id=tok.workspace_id,
            target_type="api_token",
            target_id=tok.id,
        )
        await db.commit()
    return None
