"""API-side run events and guarded transitions (async twin of ``worker/core/events.py``).

``publish_run_event`` here matches the OWNERSHIP note-1 signature
(``publish_run_event(run_id, event, data, persist)``) on top of an explicit session/redis pair.
Rules (run-lifecycle §2, §9): the ``run_events`` row and the status update share one transaction;
Redis publishes happen after commit and are best effort.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GpuNode, Run, RunEvent, RunStatus

log = logging.getLogger(__name__)

QUEUE_CHANNEL = "hibiscus:queue"


def run_channel(run_id: uuid.UUID | str) -> str:
    return f"hibiscus:run:{run_id}"


def workspace_channel(workspace_id: uuid.UUID | str) -> str:
    return f"hibiscus:ws:{workspace_id}"


def control_channel(gpu_id: str) -> str:
    return f"hibiscus:control:{gpu_id}"


def sanitize(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [sanitize(v) for v in value]
    return value


def iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class Outbox:
    items: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def add(self, channel: str, payload: dict[str, Any]) -> None:
        self.items.append((channel, payload))

    async def flush(self, redis: aioredis.Redis | None) -> None:
        items, self.items = self.items, []
        if redis is None:
            return
        for ch, payload in items:
            try:
                await redis.publish(ch, json.dumps(sanitize(payload), separators=(",", ":"), default=str))
            except Exception as exc:  # best effort (Redis loss degrades live SSE only)
                log.warning("redis publish %s failed: %s", ch, type(exc).__name__)


async def append_run_event(
    db: AsyncSession,
    run_id: uuid.UUID,
    event_type: str,
    data: dict[str, Any],
    outbox: Outbox,
    *,
    level: str = "info",
) -> int:
    row = (
        await db.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(last_event_seq=Run.last_event_seq + 1)
            .returning(Run.last_event_seq, Run.attempt)
        )
    ).one()
    seq = int(row[0])
    clean = sanitize(data)
    db.add(RunEvent(run_id=run_id, seq=seq, type=event_type, level=level, attempt=int(row[1]), data=clean))
    await db.flush()
    outbox.add(run_channel(run_id), {"event": event_type, "id": seq, "data": clean})
    return seq


async def transition(
    db: AsyncSession,
    run: Run,
    *,
    from_statuses: Iterable[RunStatus],
    to: RunStatus,
    outbox: Outbox,
    reason: str | None,
    error_code: str | None = None,
    extra: dict[str, Any] | None = None,
    release_gpu: bool = False,
) -> bool:
    froms = list(from_statuses)
    values: dict[str, Any] = {"status": to, "status_changed_at": func.now()}
    if to in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED):
        values["finished_at"] = func.now()
    if to in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.QUEUED, RunStatus.PAUSED):
        values.update(lease_owner=None, lease_expires_at=None)
    if extra:
        values.update(extra)
    prev = run.status
    res = (
        await db.execute(
            update(Run)
            .where(Run.id == run.id, Run.status.in_(froms))
            .values(**values)
            .returning(Run.gpu_node_id, Run.attempt)
            .execution_options(synchronize_session=False)
        )
    ).one_or_none()
    if res is None:
        return False
    gpu_id = res[0]
    if release_gpu and gpu_id is not None:
        await db.execute(
            update(GpuNode)
            .where(GpuNode.id == gpu_id, GpuNode.current_run_id == run.id)
            .values(current_run_id=None)
        )
    data = {
        "kind": "status",
        "run_id": str(run.id),
        "from": prev.value if prev is not None else None,
        "to": to.value,
        "reason": reason,
        "error_code": error_code,
        "attempt": int(res[1]),
        "gpu_id": gpu_id,
        "ts": iso_now(),
    }
    await append_run_event(
        db, run.id, "status", data, outbox, level="error" if to == RunStatus.FAILED else "info"
    )
    outbox.add(workspace_channel(run.workspace_id), {"event": "run.status", "data": data})
    await db.refresh(run)
    return True


async def last_seq(db: AsyncSession, run_id: uuid.UUID) -> int:
    v = await db.scalar(select(func.coalesce(func.max(RunEvent.seq), 0)).where(RunEvent.run_id == run_id))
    return int(v or 0)
