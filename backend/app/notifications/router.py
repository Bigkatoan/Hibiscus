"""Notifications API (OpenAPI tag ``notifications``) + dispatcher wiring.

Mounted through ``settings.extra_routers`` entry ``app.notifications.router``:

* ``router`` — ``/users/me/notification-channels*`` and ``/notifications*``. Every operation's
  contract security is ``cookieAuth`` only, so PATs get 403 ``forbidden`` (``session_principal``);
  unsafe methods need the CSRF double-submit.
* ``setup_app(app)`` — builds :class:`NotificationsState` (egress policy, sender, dispatcher).
* ``app_lifespan(app)`` — starts the leader-elected dispatcher loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, get_args

from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditAction, record
from app.core.deps import Principal, get_db, services, session_principal
from app.core.errors import VALIDATION_400, ErrorCode, ProblemError
from app.core.pagination import decode_cursor, encode_cursor
from app.core.services import Services
from app.db.models import Notification, NotificationChannel, NotificationChannelKind, User
from app.notifications.channels import (
    SUBSCRIBABLE_EVENTS,
    ChannelSender,
    decrypt_target,
    encrypt_target,
    target_hint,
    validate_target,
)
from app.notifications.dispatcher import Dispatcher, dispatcher_loop, iso, notification_out
from app.notifications.egress import (
    DeliveryError,
    EgressPolicy,
    Resolver,
    TargetRejectedError,
    build_ssl_context,
    parse_networks,
    system_resolve,
)
from app.notifications.render import absolute_link, render
from app.notifications.settings import NotificationSettings, get_notification_settings

router = APIRouter(prefix="/api/v1", tags=["notifications"])

DB = Annotated[AsyncSession, Depends(get_db)]
Me = Annotated[Principal, Depends(session_principal)]
Limit = Annotated[int, Query(ge=1, le=200)]
SubscribableEvent = Literal[
    "run.succeeded", "run.failed", "run.stalled", "model.ready", "dataset.ready", "dataset.invalid"
]
assert set(get_args(SubscribableEvent)) == set(SUBSCRIBABLE_EVENTS)  # noqa: S101


@dataclass
class NotificationsState:
    settings: NotificationSettings
    policy: EgressPolicy
    sender: ChannelSender
    dispatcher: Dispatcher
    tasks: list[asyncio.Task[None]] = field(default_factory=list)


def setup_app(
    app: FastAPI,
    settings: NotificationSettings | None = None,
    *,
    resolver: Resolver | None = None,
) -> NotificationsState:
    svc: Services = app.state.services
    s = settings or get_notification_settings()
    if s.ssrf_allow_cidrs and svc.settings.env == "prod":
        raise ValueError("HIBISCUS_NOTIFY_SSRF_ALLOW_CIDRS must be empty in production")
    policy = EgressPolicy(
        resolver=resolver or system_resolve,
        allow=parse_networks(s.ssrf_allow_cidrs),
        ssl_context=build_ssl_context(s.ca_file),
        connect_timeout_s=s.connect_timeout_s,
        timeout_s=s.timeout_s,
        max_response_bytes=s.max_response_bytes,
    )
    sender = ChannelSender(svc.email, s, policy)
    state = NotificationsState(
        settings=s, policy=policy, sender=sender, dispatcher=Dispatcher(svc, s, sender)
    )
    app.state.notifications = state
    return state


@contextlib.asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[NotificationsState]:
    state: NotificationsState = app.state.notifications
    if state.settings.dispatcher_enabled:
        state.tasks.append(asyncio.create_task(dispatcher_loop(state.dispatcher)))
    try:
        yield state
    finally:
        for t in state.tasks:
            t.cancel()
        for t in state.tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        state.tasks.clear()


def _state(request: Request) -> NotificationsState:
    st: NotificationsState = request.app.state.notifications
    return st


# ----------------------------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------------------------
class NotificationChannelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: NotificationChannelKind
    target: str = Field(max_length=512)
    events: list[SubscribableEvent] = Field(min_length=1)


def channel_out(ch: NotificationChannel, hint: str) -> dict[str, Any]:
    return {
        "id": str(ch.id),
        "kind": NotificationChannelKind(ch.kind).value,
        "events": list(ch.events or []),
        "enabled": bool(ch.enabled),
        "target_hint": hint,
        "created_at": iso(ch.created_at),
    }


def _hint(request: Request, ch: NotificationChannel) -> str:
    try:
        return target_hint(
            ch.kind, decrypt_target(services(request).cipher, ch.user_id, ch.id, ch.config_enc)
        )
    except Exception:  # undecryptable (key rotated): never fail the listing
        return "…"


def _invalid(loc: list[str | int], code: str, message: str) -> ProblemError:
    return ProblemError(
        422, ErrorCode.VALIDATION_FAILED, errors=[{"loc": loc, "code": code, "message": message}]
    )


async def _own_channel(db: AsyncSession, principal: Principal, channel_id: uuid.UUID) -> NotificationChannel:
    ch = await db.get(NotificationChannel, channel_id)
    if ch is None or ch.user_id != principal.user_id:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    return ch


# ----------------------------------------------------------------------------------------------
# Channels
# ----------------------------------------------------------------------------------------------
@router.get(
    "/users/me/notification-channels", operation_id="listNotificationChannels", openapi_extra=VALIDATION_400
)
async def list_notification_channels(request: Request, principal: Me, db: DB) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(NotificationChannel)
            .where(NotificationChannel.user_id == principal.user_id)
            .order_by(NotificationChannel.created_at, NotificationChannel.id)
        )
    ).scalars()
    return {"items": [channel_out(ch, _hint(request, ch)) for ch in rows]}


@router.post("/users/me/notification-channels", operation_id="createNotificationChannel", status_code=201)
async def create_notification_channel(
    body: NotificationChannelCreate, request: Request, principal: Me, db: DB
) -> dict[str, Any]:
    st = _state(request)
    user = await db.get(User, principal.user_id)
    if user is None:  # pragma: no cover - principal implies the row
        raise ProblemError(401, ErrorCode.UNAUTHENTICATED)
    count = await db.scalar(
        select(func.count()).select_from(NotificationChannel).where(NotificationChannel.user_id == user.id)
    )
    if int(count or 0) >= st.settings.max_channels_per_user:
        raise _invalid(
            ["body"], "max_channels", f"At most {st.settings.max_channels_per_user} channels per user"
        )
    try:
        target = await validate_target(
            body.kind,
            body.target,
            user_email=user.email,
            user_verified=user.email_verified_at is not None,
            settings=st.settings,
            policy=st.policy,
        )
    except TargetRejectedError as e:
        raise _invalid(["body", "target"], e.reason, e.message) from e
    events = list(dict.fromkeys(body.events))
    ch = NotificationChannel(id=uuid.uuid4(), user_id=user.id, kind=body.kind, events=events, enabled=True)
    ch.config_enc = encrypt_target(services(request).cipher, user.id, ch.id, target)
    db.add(ch)
    await db.flush()
    await record(
        AuditAction.SECRET_UPDATED,
        db=db,
        actor=principal,
        target_type="notification_channel",
        target_id=str(ch.id),
        details={"op": "notification_channel.created", "kind": body.kind.value, "events": events},
    )
    await db.commit()
    await db.refresh(ch)
    return channel_out(ch, target_hint(body.kind, target))


@router.delete(
    "/users/me/notification-channels/{channel_id}",
    operation_id="deleteNotificationChannel",
    status_code=204,
    openapi_extra=VALIDATION_400,
)
async def delete_notification_channel(channel_id: uuid.UUID, principal: Me, db: DB) -> Response:
    ch = await _own_channel(db, principal, channel_id)
    kind = NotificationChannelKind(ch.kind).value
    await db.delete(ch)
    await record(
        AuditAction.SECRET_UPDATED,
        db=db,
        actor=principal,
        target_type="notification_channel",
        target_id=str(channel_id),
        details={"op": "notification_channel.deleted", "kind": kind},
    )
    await db.commit()
    return Response(status_code=204)


@router.post(
    "/users/me/notification-channels/{channel_id}/test",
    operation_id="testNotificationChannel",
    status_code=202,
    openapi_extra=VALIDATION_400,
)
async def test_notification_channel(
    channel_id: uuid.UUID, request: Request, principal: Me, db: DB
) -> Response:
    st = _state(request)
    svc = services(request)
    ident = str(principal.user_id)
    await svc.limiter.hit("notify_test:min", ident, limit=st.settings.test_rate_per_min, window_s=60)
    await svc.limiter.hit("notify_test:hour", ident, limit=st.settings.test_rate_per_hour, window_s=3600)
    ch = await _own_channel(db, principal, channel_id)
    user = await db.get(User, principal.user_id)
    if user is None:  # pragma: no cover
        raise ProblemError(401, ErrorCode.UNAUTHENTICATED)
    now = datetime.now(UTC)
    url = absolute_link(svc.settings.public_base_url, "/settings/notifications", None)
    rendered = render("test", {}, user.locale, url)
    payload: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "workspace_id": None,
        "kind": "test",
        "params": {},
        "link": "/settings/notifications",
        "read": False,
        "created_at": iso(now),
    }
    db.expunge(ch)
    db.expunge(user)
    await db.rollback()  # release the connection while the outbound request runs
    try:
        await st.dispatcher.send_channel(ch, user, rendered, payload)
    except TargetRejectedError as e:
        raise ProblemError(
            503,
            ErrorCode.SERVICE_UNAVAILABLE,
            f"Test delivery refused: {e.message}",
            params={"reason": e.reason},
        ) from e
    except DeliveryError as e:
        raise ProblemError(503, ErrorCode.SERVICE_UNAVAILABLE, f"Test delivery failed: {e.message}") from e
    return Response(status_code=202)


# ----------------------------------------------------------------------------------------------
# In-app notifications
# ----------------------------------------------------------------------------------------------
@router.get("/notifications", operation_id="listNotifications", openapi_extra=VALIDATION_400)
async def list_notifications(
    principal: Me,
    db: DB,
    unread: bool | None = None,
    limit: Limit = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    stmt = select(Notification).where(Notification.user_id == principal.user_id)
    if unread is True:
        stmt = stmt.where(Notification.read_at.is_(None))
    elif unread is False:
        stmt = stmt.where(Notification.read_at.is_not(None))
    if cursor:
        c = decode_cursor(cursor)
        try:
            ts = datetime.fromisoformat(str(c["t"]))
            cid = uuid.UUID(str(c["i"]))
        except (KeyError, ValueError) as e:
            raise ProblemError(400, ErrorCode.BAD_REQUEST, "Invalid cursor") from e
        stmt = stmt.where(
            (Notification.created_at < ts) | ((Notification.created_at == ts) & (Notification.id < cid))
        )
    rows = list(
        (
            await db.execute(
                stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit + 1)
            )
        ).scalars()
    )
    page = rows[:limit]
    nxt = (
        encode_cursor({"t": page[-1].created_at.isoformat(), "i": str(page[-1].id)})
        if len(rows) > limit and page
        else None
    )
    unread_count = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == principal.user_id, Notification.read_at.is_(None))
    )
    return {
        "items": [notification_out(n) for n in page],
        "next_cursor": nxt,
        "unread_count": int(unread_count or 0),
    }


@router.post(
    "/notifications/{notification_id}/read",
    operation_id="markNotificationRead",
    status_code=204,
    openapi_extra=VALIDATION_400,
)
async def mark_notification_read(notification_id: uuid.UUID, principal: Me, db: DB) -> Response:
    n = await db.get(Notification, notification_id)
    if n is None or n.user_id != principal.user_id:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    if n.read_at is None:
        n.read_at = datetime.now(UTC)
        await db.commit()
    return Response(status_code=204)


@router.post(
    "/notifications/read-all",
    operation_id="markAllNotificationsRead",
    status_code=204,
    openapi_extra=VALIDATION_400,
)
async def mark_all_notifications_read(principal: Me, db: DB) -> Response:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == principal.user_id, Notification.read_at.is_(None))
        .values(read_at=func.now())
    )
    await db.commit()
    return Response(status_code=204)


__all__: list[str] = ["NotificationsState", "app_lifespan", "router", "setup_app"]
