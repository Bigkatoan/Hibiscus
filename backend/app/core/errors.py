"""RFC 9457 problem+json errors with the contract's ``ErrorCode`` catalogue (api/openapi.yaml).

Usage (all packages)::

    from app.core.errors import ErrorCode, ProblemError
    raise ProblemError(404, ErrorCode.NOT_FOUND)
    raise ProblemError(429, ErrorCode.RATE_LIMITED, retry_after_s=30)

Extra keyword arguments become extension members of the problem body (``errors``,
``retry_after_s``, ``missing_parts``, ``params``). ``retry_after_s`` also sets ``Retry-After``.
"""

from __future__ import annotations

import enum
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, Response

log = logging.getLogger("hibiscus.errors")


class ErrorCode(enum.StrEnum):
    BAD_REQUEST = "bad_request"
    VALIDATION_FAILED = "validation_failed"
    UNAUTHENTICATED = "unauthenticated"
    TOKEN_EXPIRED = "token_expired"  # noqa: S105 - error code label
    FORBIDDEN = "forbidden"
    INSUFFICIENT_SCOPE = "insufficient_scope"
    CSRF_FAILED = "csrf_failed"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    GONE = "gone"
    LENGTH_REQUIRED = "length_required"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    RANGE_NOT_SATISFIABLE = "range_not_satisfiable"
    RATE_LIMITED = "rate_limited"
    INTERNAL_ERROR = "internal_error"
    SERVICE_UNAVAILABLE = "service_unavailable"
    INVALID_CREDENTIALS = "invalid_credentials"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_DISABLED = "account_disabled"
    EMAIL_NOT_VERIFIED = "email_not_verified"
    MFA_INVALID_CODE = "mfa_invalid_code"
    MFA_TOKEN_INVALID = "mfa_token_invalid"  # noqa: S105
    MFA_ENROLLMENT_REQUIRED = "mfa_enrollment_required"
    MFA_REQUIRED_BY_ROLE = "mfa_required_by_role"
    MFA_ALREADY_ENABLED = "mfa_already_enabled"
    MFA_REAUTH_REQUIRED = "mfa_reauth_required"
    TURNSTILE_FAILED = "turnstile_failed"
    REFRESH_REUSE_DETECTED = "refresh_reuse_detected"
    SESSION_REVOKED = "session_revoked"
    TOKEN_REVOKED = "token_revoked"  # noqa: S105
    PASSWORD_TOO_WEAK = "password_too_weak"  # noqa: S105
    PASSWORD_BREACHED = "password_breached"  # noqa: S105
    PASSWORD_INCORRECT = "password_incorrect"  # noqa: S105
    ONE_TIME_TOKEN_INVALID = "one_time_token_invalid"  # noqa: S105
    INVITE_INVALID = "invite_invalid"
    INVITE_EXPIRED = "invite_expired"
    INVITE_EMAIL_MISMATCH = "invite_email_mismatch"
    EMAIL_TAKEN = "email_taken"
    WORKSPACE_SLUG_TAKEN = "workspace_slug_taken"
    WORKSPACE_NOT_EMPTY = "workspace_not_empty"
    LAST_OWNER = "last_owner"
    MEMBER_EXISTS = "member_exists"
    QUOTA_EXCEEDED = "quota_exceeded"
    DATASET_NAME_TAKEN = "dataset_name_taken"
    DATASET_IN_USE = "dataset_in_use"
    DATASET_VERSION_NOT_READY = "dataset_version_not_ready"
    DATASET_VERSION_DUPLICATE = "dataset_version_duplicate"
    DATASET_SCHEMA_MISMATCH = "dataset_schema_mismatch"
    HF_URI_INVALID = "hf_uri_invalid"
    HF_TOKEN_MISSING = "hf_token_missing"  # noqa: S105
    UPLOAD_NOT_ACTIVE = "upload_not_active"
    UPLOAD_INCOMPLETE = "upload_incomplete"
    UPLOAD_PART_OUT_OF_RANGE = "upload_part_out_of_range"
    UPLOAD_PART_SIZE_INVALID = "upload_part_size_invalid"
    UPLOAD_PART_CHECKSUM_MISMATCH = "upload_part_checksum_mismatch"
    UPLOAD_TOO_LARGE = "upload_too_large"
    ARCHIVE_FORMAT_UNSUPPORTED = "archive_format_unsupported"
    POLICY_UNKNOWN = "policy_unknown"
    POLICY_NOT_TRAINABLE = "policy_not_trainable"
    POLICY_CONFIG_INVALID = "policy_config_invalid"
    POLICY_REQUIRES_PEFT = "policy_requires_peft"
    PREFLIGHT_FAILED = "preflight_failed"
    GPU_UNKNOWN = "gpu_unknown"
    GPU_INSUFFICIENT_VRAM = "gpu_insufficient_vram"
    RUN_INVALID_TRANSITION = "run_invalid_transition"
    RUN_NOT_RESUMABLE = "run_not_resumable"
    CHECKPOINT_NOT_FOUND = "checkpoint_not_found"
    MODEL_NOT_READY = "model_not_ready"
    HUB_REPO_INVALID = "hub_repo_invalid"
    JOB_NOT_CANCELLABLE = "job_not_cancellable"


#: Stable English titles (clients localise from ``code``).
_TITLES: dict[ErrorCode, str] = {
    ErrorCode.BAD_REQUEST: "Bad request",
    ErrorCode.VALIDATION_FAILED: "Validation failed",
    ErrorCode.UNAUTHENTICATED: "Authentication required",
    ErrorCode.TOKEN_EXPIRED: "Access token expired",
    ErrorCode.FORBIDDEN: "Forbidden",
    ErrorCode.INSUFFICIENT_SCOPE: "Token scope insufficient",
    ErrorCode.CSRF_FAILED: "CSRF check failed",
    ErrorCode.NOT_FOUND: "Not found",
    ErrorCode.CONFLICT: "Conflict",
    ErrorCode.GONE: "Gone",
    ErrorCode.PAYLOAD_TOO_LARGE: "Payload too large",
    ErrorCode.RATE_LIMITED: "Too many requests",
    ErrorCode.INTERNAL_ERROR: "Internal server error",
    ErrorCode.SERVICE_UNAVAILABLE: "Service unavailable",
    ErrorCode.INVALID_CREDENTIALS: "Invalid email or password",
    ErrorCode.ACCOUNT_LOCKED: "Account temporarily locked",
    ErrorCode.ACCOUNT_DISABLED: "Account disabled",
    ErrorCode.MFA_INVALID_CODE: "Invalid verification code",
    ErrorCode.MFA_TOKEN_INVALID: "Second-factor challenge invalid or expired",
    ErrorCode.MFA_ENROLLMENT_REQUIRED: "Two-factor enrolment required",
    ErrorCode.MFA_REQUIRED_BY_ROLE: "Two-factor authentication is required for this role",
    ErrorCode.MFA_ALREADY_ENABLED: "Two-factor authentication already enabled",
    ErrorCode.MFA_REAUTH_REQUIRED: "Second-factor verification required",
    ErrorCode.TURNSTILE_FAILED: "Bot check failed",
    ErrorCode.REFRESH_REUSE_DETECTED: "Refresh token reuse detected",
    ErrorCode.SESSION_REVOKED: "Session revoked",
    ErrorCode.TOKEN_REVOKED: "Token revoked",
    ErrorCode.PASSWORD_TOO_WEAK: "Password too weak",
    ErrorCode.PASSWORD_BREACHED: "Password found in breach list",
    ErrorCode.PASSWORD_INCORRECT: "Password incorrect",
    ErrorCode.ONE_TIME_TOKEN_INVALID: "Link invalid or expired",
    ErrorCode.INVITE_INVALID: "Invite invalid",
    ErrorCode.INVITE_EXPIRED: "Invite expired",
    ErrorCode.INVITE_EMAIL_MISMATCH: "Invite is for another email",
    ErrorCode.EMAIL_TAKEN: "Email already registered",
    ErrorCode.WORKSPACE_SLUG_TAKEN: "Workspace slug taken",
    ErrorCode.WORKSPACE_NOT_EMPTY: "Workspace has active runs",
    ErrorCode.LAST_OWNER: "Workspace needs at least one owner",
    ErrorCode.MEMBER_EXISTS: "Already a member",
    ErrorCode.QUOTA_EXCEEDED: "Quota exceeded",
}


#: Route marker for operations whose contract documents no 422: request validation failures are
#: then rendered as 400 ``bad_request`` (still with ``errors[]``). Usage:
#: ``@router.post(..., openapi_extra=VALIDATION_400)``.
VALIDATION_STATUS_KEY = "x-hibiscus-validation-status"
VALIDATION_400: dict[str, int] = {VALIDATION_STATUS_KEY: 400}


def instance_of(scope: Any) -> str:
    """Percent-encoded request path (a valid RFC 3986 uri-reference, never raw unicode)."""
    from urllib.parse import quote

    raw = scope.get("raw_path")
    if isinstance(raw, bytes | bytearray) and raw:
        text = bytes(raw).decode("latin-1").split("?", 1)[0]
        return quote(text, safe="/%:@!$&'()*+,;=-._~")
    return quote(str(scope.get("path", "")), safe="/:@!$&'()*+,;=-._~")


def title_for(code: ErrorCode) -> str:
    return _TITLES.get(code, code.value.replace("_", " ").capitalize())


class ProblemError(Exception):
    """Raise anywhere; rendered as ``application/problem+json`` (``Problem`` schema)."""

    def __init__(
        self,
        status: int,
        code: ErrorCode,
        detail: str | None = None,
        *,
        headers: dict[str, str] | None = None,
        **ext: Any,
    ) -> None:
        super().__init__(detail or code.value)
        self.status = status
        self.code = ErrorCode(code)
        self.detail = detail
        self.headers = dict(headers or {})
        self.ext = ext
        retry = ext.get("retry_after_s")
        if retry is not None:
            self.headers.setdefault("Retry-After", str(int(retry)))


def _request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    return str(rid) if rid else "-"


def problem_response(
    request: Request,
    status: int,
    code: ErrorCode,
    detail: str | None = None,
    headers: dict[str, str] | None = None,
    **ext: Any,
) -> JSONResponse:
    from app.core.settings import get_settings

    base = getattr(request.app.state, "settings", None) or get_settings()
    body: dict[str, Any] = {
        "type": f"{base.problem_type_base}{code.value}",
        "title": title_for(code),
        "status": status,
        "code": code.value,
        "request_id": _request_id(request),
        "instance": instance_of(request.scope),
    }
    if detail:
        body["detail"] = detail
    for k, v in ext.items():
        if v is not None:
            body[k] = v
    return JSONResponse(body, status_code=status, headers=headers, media_type="application/problem+json")


_STATUS_CODES: dict[int, ErrorCode] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    410: ErrorCode.GONE,
    411: ErrorCode.LENGTH_REQUIRED,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    416: ErrorCode.RANGE_NOT_SATISFIABLE,
    422: ErrorCode.VALIDATION_FAILED,
    429: ErrorCode.RATE_LIMITED,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}


def _field_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for err in exc.errors():
        loc = [p if isinstance(p, int) else str(p) for p in err.get("loc", ())]
        out.append({"loc": loc, "code": str(err.get("type", "invalid")), "message": str(err.get("msg", ""))})
    return out


async def _problem_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, ProblemError):  # pragma: no cover - registered for this type only
        raise exc
    return problem_response(request, exc.status, exc.code, exc.detail, exc.headers, **exc.ext)


async def _validation_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover
        raise exc
    errors = _field_errors(exc)
    if any(
        e["code"] in ("json_invalid", "model_attributes_type") and e["loc"][:1] == ["body"] for e in errors
    ):
        return problem_response(request, 400, ErrorCode.BAD_REQUEST, "Malformed JSON body")
    route = request.scope.get("route")
    extra = getattr(route, "openapi_extra", None) or {}
    if extra.get(VALIDATION_STATUS_KEY) == 400:
        return problem_response(
            request, 400, ErrorCode.BAD_REQUEST, "Request validation failed", errors=errors
        )
    return problem_response(request, 422, ErrorCode.VALIDATION_FAILED, errors=errors)


async def _http_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover
        raise exc
    code = _STATUS_CODES.get(exc.status_code, ErrorCode.BAD_REQUEST)
    detail = exc.detail if isinstance(exc.detail, str) and exc.status_code not in (404,) else None
    return problem_response(request, exc.status_code, code, detail, dict(exc.headers or {}))


async def _unhandled_handler(request: Request, exc: Exception) -> Response:
    log.exception("unhandled error", exc_info=exc)
    return problem_response(request, 500, ErrorCode.INTERNAL_ERROR)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ProblemError, _problem_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
