"""Notification dispatcher: fan-out to external channels, delivery with retries, in-app SSE.

Producers (the train worker, API code) only ``INSERT INTO notifications``. The dispatcher, running
in the API lifespan and leader-elected with ``pg_try_advisory_lock(7002)`` on a dedicated
connection (multiple API replicas never double-send), loops every ``poll_interval_s``:

1. **fan-out** — rows with ``dispatched_at IS NULL`` (``FOR UPDATE SKIP LOCKED``): one
   ``notification_deliveries`` row per enabled channel of the user subscribed to the kind; the
   in-app ``notification`` event is published on the workspace SSE channel (addressed to the user,
   the stream filters by ``user_id``); ``dispatched_at = now()``. Rows older than ``max_age_s`` are
   marked dispatched without external delivery.
2. **deliver** — due ``pending`` deliveries are *claimed* (``attempts + 1``, ``next_attempt_at =
   now() + claim_ttl_s``, committed) before sending, so even a split-brain second dispatcher cannot
   pick the same row. Success => ``sent``; retryable failure => backoff
   ``min(base * 4**(attempts-1), max)``; permanent failure or ``max_attempts`` reached => ``failed``
   with ``last_error`` (no secrets: messages never contain the target URL / token).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish_workspace_event
from app.core.services import Services
from app.db.models import (
    Notification,
    NotificationChannel,
    NotificationChannelKind,
    NotificationDelivery,
    User,
    Workspace,
)
from app.notifications.channels import ChannelSender, decrypt_target
from app.notifications.egress import DeliveryError, TargetRejectedError
from app.notifications.render import Rendered, absolute_link, render
from app.notifications.settings import NotificationSettings

log = logging.getLogger("hibiscus.notifications")
LOCK_ID = 7002


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def notification_out(n: Notification) -> dict[str, Any]:
    """``Notification`` schema."""
    return {
        "id": str(n.id),
        "workspace_id": str(n.workspace_id) if n.workspace_id else None,
        "kind": n.kind,
        "params": dict(n.params or {}),
        "link": n.link,
        "read": n.read_at is not None,
        "created_at": iso(n.created_at),
    }


@dataclass
class Dispatcher:
    svc: Services
    settings: NotificationSettings
    sender: ChannelSender

    # ------------------------------------------------------------------------------------------
    async def fan_out(self, db: AsyncSession) -> int:
        s = self.settings
        rows = list(
            (
                await db.execute(
                    select(Notification)
                    .where(Notification.dispatched_at.is_(None))
                    .order_by(Notification.created_at)
                    .limit(s.batch_size * 4)
                    .with_for_update(skip_locked=True)
                )
            ).scalars()
        )
        if not rows:
            return 0
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=s.max_age_s)
        users = {n.user_id for n in rows}
        channels = list(
            (
                await db.execute(
                    select(NotificationChannel).where(
                        NotificationChannel.user_id.in_(users), NotificationChannel.enabled.is_(True)
                    )
                )
            ).scalars()
        )
        events: list[tuple[uuid.UUID, uuid.UUID, dict[str, Any]]] = []
        for n in rows:
            if n.created_at >= cutoff:
                for ch in channels:
                    if ch.user_id == n.user_id and n.kind in (ch.events or []):
                        await db.execute(
                            pg_insert(NotificationDelivery)
                            .values(id=uuid.uuid4(), notification_id=n.id, channel_id=ch.id)
                            .on_conflict_do_nothing()
                        )
            n.dispatched_at = now
            if n.workspace_id is not None:
                events.append((n.workspace_id, n.user_id, notification_out(n)))
        await db.commit()
        for ws_id, user_id, data in events:  # in-app SSE, only after the commit
            await publish_workspace_event(ws_id, "notification", data, user_id=user_id)
        return len(rows)

    # ------------------------------------------------------------------------------------------
    async def _claim(self, db: AsyncSession) -> list[uuid.UUID]:
        s = self.settings
        due = (
            select(NotificationDelivery.id)
            .where(
                NotificationDelivery.status == "pending", NotificationDelivery.next_attempt_at <= func.now()
            )
            .order_by(NotificationDelivery.next_attempt_at)
            .limit(s.batch_size)
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )
        ids = list(
            (
                await db.execute(
                    update(NotificationDelivery)
                    .where(NotificationDelivery.id.in_(due))
                    .values(
                        attempts=NotificationDelivery.attempts + 1,
                        next_attempt_at=func.now() + timedelta(seconds=s.claim_ttl_s),
                    )
                    .returning(NotificationDelivery.id)
                )
            ).scalars()
        )
        await db.commit()
        return ids

    def backoff_s(self, attempts: int) -> float:
        s = self.settings
        return float(min(s.backoff_base_s * (4 ** max(attempts - 1, 0)), s.backoff_max_s))

    async def _context(
        self, db: AsyncSession, delivery_id: uuid.UUID
    ) -> tuple[NotificationDelivery, Notification, NotificationChannel, User, str | None] | None:
        row = (
            await db.execute(
                select(NotificationDelivery, Notification, NotificationChannel, User)
                .join(Notification, Notification.id == NotificationDelivery.notification_id)
                .join(NotificationChannel, NotificationChannel.id == NotificationDelivery.channel_id)
                .join(User, User.id == Notification.user_id)
                .where(NotificationDelivery.id == delivery_id)
            )
        ).one_or_none()
        if row is None:
            return None
        d, n, ch, user = row
        slug = None
        if n.workspace_id is not None:
            slug = await db.scalar(select(Workspace.slug).where(Workspace.id == n.workspace_id))
        return d, n, ch, user, slug

    async def _deliver_one(self, delivery_id: uuid.UUID) -> str:
        async with self.svc.db.sessionmaker() as db:
            ctx = await self._context(db, delivery_id)
            if ctx is None:
                return "gone"
            d, n, ch, user, slug = ctx
            error: DeliveryError | None = None
            if not ch.enabled or user.is_active is False:
                error = DeliveryError("channel disabled", retryable=False)
            else:
                url = absolute_link(self.svc.settings.public_base_url, n.link, slug)
                rendered = render(n.kind, dict(n.params or {}), user.locale, url)
                try:
                    await self.send_channel(ch, user, rendered, notification_out(n))
                except DeliveryError as e:
                    error = e
                except TargetRejectedError as e:
                    error = DeliveryError(f"target rejected: {e.reason}", retryable=False)
                except Exception as e:  # never let one bad channel kill the loop
                    log.exception("notification delivery crashed")
                    error = DeliveryError(f"internal error ({type(e).__name__})", retryable=True)
            values: dict[str, Any]
            if error is None:
                values = {"status": "sent", "sent_at": func.now(), "last_error": None}
                outcome = "sent"
            elif error.retryable and d.attempts < self.settings.max_attempts:
                values = {
                    "next_attempt_at": func.now() + timedelta(seconds=self.backoff_s(d.attempts)),
                    "last_error": error.message[:500],
                }
                outcome = "retry"
            else:
                values = {"status": "failed", "last_error": error.message[:500]}
                outcome = "failed"
            await db.execute(
                update(NotificationDelivery).where(NotificationDelivery.id == d.id).values(**values)
            )
            await db.commit()
            if error is not None:
                log.warning(
                    "notification delivery %s",
                    outcome,
                    extra={"delivery_id": str(d.id), "channel_kind": str(ch.kind), "error": error.message},
                )
            return outcome

    async def send_channel(
        self, ch: NotificationChannel, user: User, rendered: Rendered, notification: dict[str, Any]
    ) -> None:
        target = decrypt_target(self.svc.cipher, ch.user_id, ch.id, ch.config_enc)
        await self.sender.send(
            NotificationChannelKind(ch.kind),
            target,
            rendered,
            notification=notification,
            user_email=user.email,
            user_verified=user.email_verified_at is not None,
        )

    async def deliver_due(self) -> dict[str, int]:
        async with self.svc.db.sessionmaker() as db:
            ids = await self._claim(db)
        counts: dict[str, int] = {}
        sem = asyncio.Semaphore(max(1, self.settings.concurrency))

        async def one(i: uuid.UUID) -> None:
            async with sem:
                outcome = await self._deliver_one(i)
            counts[outcome] = counts.get(outcome, 0) + 1

        await asyncio.gather(*(one(i) for i in ids))
        return counts

    async def run_once(self) -> dict[str, int]:
        async with self.svc.db.sessionmaker() as db:
            fanned = await self.fan_out(db)
        counts = await self.deliver_due()
        return {"fanned_out": fanned, **counts}


async def dispatcher_loop(dispatcher: Dispatcher) -> None:
    """Leader election by a session-level advisory lock kept on a dedicated connection."""
    interval = dispatcher.settings.poll_interval_s
    engine = dispatcher.svc.db.engine
    while True:
        try:
            async with engine.connect() as conn:
                got = (await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_ID})).scalar()
                await conn.commit()
                if not got:
                    await asyncio.sleep(interval)
                    continue
                try:
                    while True:
                        try:
                            await dispatcher.run_once()
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            log.exception("notification dispatcher iteration failed")
                        await asyncio.sleep(interval)
                        await conn.execute(text("SELECT 1"))
                        await conn.commit()
                finally:
                    with contextlib.suppress(Exception):
                        await asyncio.shield(
                            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_ID})
                        )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("notification dispatcher connection failed; retrying")
            await asyncio.sleep(interval)
