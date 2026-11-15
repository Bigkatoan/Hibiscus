"""Generic ``jobs`` queue protocol (run-lifecycle §7.3): claim with SKIP LOCKED, lease, finish.

Public API (stable for A3's CPU worker and A5):
    * :func:`claim_job(conn, *, resource, kinds, worker_id, lease_s)` -> ``ClaimedJob | None``
    * :func:`heartbeat_job(conn, job_id, worker_id, *, progress=None, lease_s=60)` -> bool
    * :func:`finish_job(conn, job_id, worker_id, *, status, result=None, error_code=None, error_message=None)`
    * :func:`oldest_queued_age_s(conn, resource, kinds)` -> float | None
    * :func:`requeue_job(conn, job_id, worker_id, *, error_code, error_message)` -> bool
    * :class:`JobKeeper` - background lease heartbeat while a handler works
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, func, select, update

from core import metrics
from core.liveness import touch
from core.tables import jobs

log = logging.getLogger(__name__)


@dataclass(slots=True)
class ClaimedJob:
    id: uuid.UUID
    workspace_id: uuid.UUID
    kind: str
    payload: dict[str, Any]
    attempts: int
    run_id: uuid.UUID | None
    dataset_version_id: uuid.UUID | None
    model_id: uuid.UUID | None
    created_by: uuid.UUID | None


def claim_job(
    conn: Connection, *, resource: str, kinds: Sequence[str], worker_id: str, lease_s: int = 60
) -> ClaimedJob | None:
    row = conn.execute(
        select(jobs)
        .where(jobs.c.status == "queued", jobs.c.resource == resource, jobs.c.kind.in_(list(kinds)))
        .order_by(jobs.c.priority.desc(), jobs.c.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    ).one_or_none()
    if row is None:
        return None
    conn.execute(
        update(jobs)
        .where(jobs.c.id == row.id)
        .values(
            status="running",
            lease_owner=worker_id,
            lease_expires_at=func.now() + timedelta(seconds=lease_s),
            attempts=jobs.c.attempts + 1,
            started_at=func.coalesce(jobs.c.started_at, func.now()),
            updated_at=func.now(),
        )
    )
    return ClaimedJob(
        id=row.id,
        workspace_id=row.workspace_id,
        kind=row.kind,
        payload=dict(row.payload or {}),
        attempts=int(row.attempts) + 1,
        run_id=row.run_id,
        dataset_version_id=row.dataset_version_id,
        model_id=row.model_id,
        created_by=row.created_by,
    )


def heartbeat_job(
    conn: Connection, job_id: uuid.UUID, worker_id: str, *, progress: float | None = None, lease_s: int = 60
) -> bool:
    values: dict[str, Any] = {
        "lease_expires_at": func.now() + timedelta(seconds=lease_s),
        "updated_at": func.now(),
    }
    if progress is not None:
        values["progress"] = max(0.0, min(1.0, progress))
    res = conn.execute(
        update(jobs)
        .where(jobs.c.id == job_id, jobs.c.lease_owner == worker_id, jobs.c.status == "running")
        .values(**values)
        .returning(jobs.c.id)
    )
    return res.one_or_none() is not None


def finish_job(
    conn: Connection,
    job_id: uuid.UUID,
    worker_id: str,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> bool:
    values: dict[str, Any] = {
        "status": status,
        "lease_owner": None,
        "lease_expires_at": None,
        "finished_at": func.now(),
        "updated_at": func.now(),
        "error_code": error_code,
        "error_message": error_message,
    }
    if status == "succeeded":
        values["progress"] = 1.0
    if result is not None:
        values["result"] = result
    res = conn.execute(
        update(jobs)
        .where(jobs.c.id == job_id, jobs.c.lease_owner == worker_id)
        .values(**values)
        .returning(jobs.c.id)
    )
    return res.one_or_none() is not None


def oldest_queued_age_s(conn: Connection, resource: str, kinds: Sequence[str]) -> float | None:
    val = conn.execute(
        select(func.extract("epoch", func.now() - func.min(jobs.c.created_at))).where(
            jobs.c.status == "queued", jobs.c.resource == resource, jobs.c.kind.in_(list(kinds))
        )
    ).scalar_one_or_none()
    return None if val is None else float(val)


def requeue_job(
    conn: Connection, job_id: uuid.UUID, worker_id: str, *, error_code: str, error_message: str
) -> bool:
    """Give a claimed job back to the queue (infra error with attempts left, worker shutdown)."""
    res = conn.execute(
        update(jobs)
        .where(jobs.c.id == job_id, jobs.c.lease_owner == worker_id)
        .values(
            status="queued",
            lease_owner=None,
            lease_expires_at=None,
            error_code=error_code,
            error_message=error_message[:2000],
            updated_at=func.now(),
        )
        .returning(jobs.c.id)
    )
    return res.one_or_none() is not None


class JobKeeper:
    """Background lease heartbeat for a claimed job (QC-backend-01 for GPU jobs).

    ``lost`` turns True when the lease is gone (reaper re-queued the job, or it was cancelled);
    the handler checks it between stages. ``progress`` (0..1) is reported with each heartbeat.
    """

    def __init__(
        self,
        engine: Engine,
        job_id: uuid.UUID,
        worker_id: str,
        *,
        lease_s: int = 60,
        interval_s: float = 10.0,
        heartbeat_file: Path | None = None,
    ) -> None:
        self.engine = engine
        self.job_id = job_id
        self.worker_id = worker_id
        self.lease_s = lease_s
        self.interval_s = interval_s
        self.heartbeat_file = heartbeat_file
        self.progress: float | None = None
        self.lost = False
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, name=f"job-lease-{job_id}", daemon=True)

    def __enter__(self) -> JobKeeper:
        self._t.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._t.join(timeout=10)

    def beat(self) -> bool:
        with self.engine.begin() as conn:
            ok = heartbeat_job(
                conn, self.job_id, self.worker_id, progress=self.progress, lease_s=self.lease_s
            )
        metrics.lease_heartbeat(ok)
        if ok:
            touch(self.heartbeat_file)
        else:
            self.lost = True
        return ok

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            try:
                if not self.beat():
                    return
            except Exception as exc:  # transient DB trouble: keep trying until the lease runs out
                log.warning("job %s heartbeat failed: %s", self.job_id, type(exc).__name__)
