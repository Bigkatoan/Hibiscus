"""/api/v1/users/me* (OpenAPI tag ``users``)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import HfTokenSet, UserUpdate
from app.auth.serializers import iso, user_out
from app.core.audit import AuditAction, record
from app.core.deps import Principal, get_db, services, session_principal
from app.core.errors import VALIDATION_400, ErrorCode, ProblemError
from app.db.models import User, UserSecret, UserSecretKind

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def hf_aad(user_id: object) -> bytes:
    return f"user_secret:hf_token:{user_id}".encode()


@router.patch("/me", operation_id="updateMe")
async def update_me(
    body: UserUpdate, principal: Principal = Depends(session_principal), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    user = await db.get(User, principal.user_id)
    if user is None:  # pragma: no cover
        raise ProblemError(401, ErrorCode.UNAUTHENTICATED)
    changed: list[str] = []
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
        changed.append("display_name")
    if body.locale is not None:
        user.locale = body.locale
        changed.append("locale")
    await record(
        AuditAction.USER_UPDATED,
        db=db,
        actor=principal,
        target_type="user",
        target_id=user.id,
        details={"fields": changed},
    )
    await db.commit()
    await db.refresh(user)
    return user_out(user)


async def _hf(db: AsyncSession, principal: Principal) -> UserSecret | None:
    return (
        await db.execute(
            select(UserSecret).where(
                UserSecret.user_id == principal.user_id, UserSecret.kind == UserSecretKind.HF_TOKEN
            )
        )
    ).scalar_one_or_none()


def _status(sec: UserSecret | None) -> dict[str, Any]:
    if sec is None:
        return {"present": False, "hint": None, "updated_at": None}
    return {"present": True, "hint": f"…{sec.hint}", "updated_at": iso(sec.updated_at)}


@router.get("/me/secrets/hf-token", operation_id="getHfTokenStatus", openapi_extra=VALIDATION_400)
async def get_hf_token_status(
    principal: Principal = Depends(session_principal), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    return _status(await _hf(db, principal))


@router.put("/me/secrets/hf-token", operation_id="setHfToken")
async def set_hf_token(
    body: HfTokenSet,
    request: Request,
    principal: Principal = Depends(session_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    cipher = services(request).cipher
    token = body.token.strip()
    blob = cipher.encrypt(token.encode(), hf_aad(principal.user_id))
    sec = await _hf(db, principal)
    if sec is None:
        sec = UserSecret(
            user_id=principal.user_id, kind=UserSecretKind.HF_TOKEN, ciphertext=blob, hint=token[-4:]
        )
        db.add(sec)
    else:
        sec.ciphertext = blob
        sec.hint = token[-4:]
    await record(
        AuditAction.SECRET_UPDATED,
        db=db,
        actor=principal,
        target_type="user_secret",
        target_id="hf_token",
        details={"op": "set"},
    )
    await db.commit()
    await db.refresh(sec)
    return _status(sec)


@router.delete(
    "/me/secrets/hf-token",
    operation_id="deleteHfToken",
    openapi_extra=VALIDATION_400,
    status_code=204,
    response_class=Response,
)
async def delete_hf_token(
    principal: Principal = Depends(session_principal), db: AsyncSession = Depends(get_db)
) -> None:
    res = await db.execute(
        delete(UserSecret).where(
            UserSecret.user_id == principal.user_id, UserSecret.kind == UserSecretKind.HF_TOKEN
        )
    )
    if getattr(res, "rowcount", 0):
        await record(
            AuditAction.SECRET_UPDATED,
            db=db,
            actor=principal,
            target_type="user_secret",
            target_id="hf_token",
            details={"op": "delete"},
        )
    await db.commit()
    return None


async def read_hf_token(db: AsyncSession, request: Request, user_id: object) -> str | None:
    """Decrypt a user's HF token (for A3/A5 server-side use; never returned by the API)."""
    import uuid

    uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    sec = (
        await db.execute(
            select(UserSecret).where(UserSecret.user_id == uid, UserSecret.kind == UserSecretKind.HF_TOKEN)
        )
    ).scalar_one_or_none()
    if sec is None:
        return None
    return services(request).cipher.decrypt(sec.ciphertext, hf_aad(uid)).decode()
