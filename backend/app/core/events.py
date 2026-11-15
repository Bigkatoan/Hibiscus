"""Run / workspace event publication (docs/spec/run-lifecycle.md §9).

``await publish_run_event(run_id, "status", {...}, persist=True, db=session)``

* ``persist=True``: allocates ``seq`` (``UPDATE runs SET last_event_seq = last_event_seq + 1``),
  inserts a ``run_events`` row in the caller's transaction and publishes to Redis
  ``hibiscus:run:<run_id>`` **after that transaction commits** (envelope
  ``{"event", "id", "data"}``). Without ``db`` an own session is opened and committed.
  Status events are also published to ``hibiscus:ws:<workspace_id>``.
* ``persist=False``: ephemeral (``progress``, ``log``, ``telemetry``), Redis only, no id.

Returns the allocated ``seq`` (or None for ephemeral events). Redis failures are logged, never
raised (persisted events are still served from ``run_events``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import event as sa_event
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as SyncSession

from app.core.db import Database
from app.db.models import Run, RunEvent

log = logging.getLogger("hibiscus.events")


class _State:
    redis: Redis | None = None
    db: Database | None = None


_state = _State()


def configure_events(redis: Redis | None, db: Database | None) -> None:
    _state.redis = redis
    _state.db = db


def run_channel(run_id: uuid.UUID | str) -> str:
    return f"hibiscus:run:{run_id}"


def workspace_channel(workspace_id: uuid.UUID | str) -> str:
    return f"hibiscus:ws:{workspace_id}"


async def _publish(channel: str, message: dict[str, Any]) -> None:
    if _state.redis is None:
        return
    try:
        await _state.redis.publish(channel, json.dumps(message, default=str))
    except (RedisError, OSError):
        log.warning("redis publish failed", extra={"channel": channel})


async def publish_workspace_event(
    workspace_id: uuid.UUID, event: str, data: dict[str, Any], *, user_id: uuid.UUID | None = None
) -> None:
    """Ephemeral workspace stream event (``WorkspaceStreamEvent``).

    ``user_id`` addresses the event to one member (e.g. ``notification``): the workspace stream
    delivers it only to that user's connections."""
    envelope: dict[str, Any] = {"event": event, "data": data}
    if user_id is not None:
        envelope["user_id"] = str(user_id)
    await _publish(workspace_channel(workspace_id), envelope)


async def publish_run_event(
    run_id: uuid.UUID,
    event: str,
    data: dict[str, Any],
    persist: bool,
    *,
    db: AsyncSession | None = None,
    level: str = "info",
    attempt: int | None = None,
) -> int | None:
    if not persist:
        await _publish(run_channel(run_id), {"event": event, "data": data})
        return None
    if db is None:
        if _state.db is None:
            raise RuntimeError("events not configured: pass db= or call configure_events()")
        async with _state.db.session() as own:
            seq = await publish_run_event(run_id, event, data, True, db=own, level=level, attempt=attempt)
            await own.commit()
            return seq
    row = (
        await db.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(last_event_seq=Run.last_event_seq + 1)
            .returning(Run.last_event_seq, Run.workspace_id, Run.attempt)
        )
    ).one()
    seq, workspace_id, run_attempt = int(row[0]), row[1], int(row[2])
    db.add(
        RunEvent(
            run_id=run_id,
            seq=seq,
            type=event,
            level=level,
            attempt=attempt if attempt is not None else run_attempt,
            data=data,
        )
    )
    await db.flush()
    envelope = {"event": event, "id": seq, "data": data}
    _after_commit(db, run_channel(run_id), envelope)
    if event == "status":
        _after_commit(db, workspace_channel(workspace_id), {"event": "run.status", "data": data})
    return seq


_PENDING_KEY = "hibiscus_pending_publishes"
_background: set[asyncio.Task[None]] = set()


def _after_commit(db: AsyncSession, channel: str, message: dict[str, Any]) -> None:
    """Queue a publish that fires only if the session's transaction commits."""
    sync: SyncSession = db.sync_session
    pending: list[tuple[str, dict[str, Any]]] | None = sync.info.get(_PENDING_KEY)
    if pending is None:
        pending = []
        sync.info[_PENDING_KEY] = pending
        loop = asyncio.get_running_loop()

        def _fire(session: SyncSession) -> None:
            items = session.info.pop(_PENDING_KEY, [])
            for ch, msg in items:
                task = loop.create_task(_publish(ch, msg))
                _background.add(task)
                task.add_done_callback(_background.discard)

        def _drop(session: SyncSession, _previous: Any = None) -> None:
            session.info.pop(_PENDING_KEY, None)

        sa_event.listen(sync, "after_commit", _fire, once=True)
        sa_event.listen(sync, "after_rollback", _drop, once=True)
    pending.append((channel, message))


async def drain_pending_publishes() -> None:
    """Await queued publishes (tests / graceful shutdown)."""
    while _background:
        await asyncio.gather(*list(_background), return_exceptions=True)
