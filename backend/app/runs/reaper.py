"""Lease reaper (run-lifecycle §7.2, §8): re-queues or fails runs/jobs whose worker vanished.

Runs inside the API process, leader-elected with ``pg_try_advisory_lock(7001)`` on a dedicated
connection, every ``reaper_interval_s`` (15 s). Also runnable once from the CLI::

    HIBISCUS_DATABASE_URL=postgresql+asyncpg://... python -m app.runs.reaper --once
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Checkpoint, GpuNode, Job, JobStatus, Run, RunStatus
from app.runs.events import Outbox, append_run_event, iso_now, transition

log = logging.getLogger(__name__)
LOCK_ID = 7001
ACTIVE = [
    RunStatus.PREPARING,
    RunStatus.RUNNING,
    RunStatus.PAUSING,
    RunStatus.EXPORTING,
    RunStatus.CANCELLING,
]


async def _last_uploaded_step(db: AsyncSession, run_id: Any) -> int | None:
    step: int | None = await db.scalar(
        select(Checkpoint.step).where(Checkpoint.run_id == run_id, Checkpoint.is_last.is_(True))
    )
    return step


async def reap_runs(db: AsyncSession, outbox: Outbox) -> list[str]:
    """Handle every active run with an expired lease. Returns ``["<run_id>:<new status>", ...]``."""
    expired = list(
        (
            await db.execute(
                select(Run)
                .where(Run.status.in_(ACTIVE), Run.lease_expires_at < func.now())
                .with_for_update(skip_locked=True)
            )
        ).scalars()
    )
    done: list[str] = []
    for run in expired:
        st = run.status
        last = await _last_uploaded_step(db, run.id)
        extra: dict[str, Any] = {"gpu_node_id": None}
        if st == RunStatus.CANCELLING:
            ok = await transition(
                db,
                run,
                from_statuses=[st],
                to=RunStatus.CANCELLED,
                outbox=outbox,
                reason="lease_expired",
                extra=extra,
                release_gpu=True,
            )
        elif st == RunStatus.PAUSING:
            extra["resume_checkpoint_step"] = last
            ok = await transition(
                db,
                run,
                from_statuses=[st],
                to=RunStatus.PAUSED,
                outbox=outbox,
                reason="lease_expired",
                extra=extra,
                release_gpu=True,
            )
        elif run.infra_retries_used == 0:
            extra.update(
                infra_retries_used=1, resume_checkpoint_step=last, error_code=None, error_message=None
            )
            await append_run_event(
                db,
                run.id,
                "error",
                {
                    "kind": "error",
                    "code": "worker_lost",
                    "message": "worker lease expired",
                    "log_excerpt": None,
                    "will_retry": True,
                    "ts": iso_now(),
                },
                outbox,
                level="error",
            )
            await append_run_event(
                db,
                run.id,
                "warning",
                {
                    "kind": "warning",
                    "code": "retrying_after_infra_error",
                    "message": "re-queued after worker loss",
                    "params": {"error_code": "worker_lost", "resume_checkpoint_step": last},
                    "ts": iso_now(),
                },
                outbox,
                level="warning",
            )
            ok = await transition(
                db,
                run,
                from_statuses=[st],
                to=RunStatus.QUEUED,
                outbox=outbox,
                reason="infra_retry",
                error_code="worker_lost",
                extra=extra,
                release_gpu=True,
            )
        else:
            code = "export_failed" if st == RunStatus.EXPORTING else "worker_lost"
            extra.update(
                error_code=code,
                error_message="worker lease expired; retry budget exhausted",
                resume_checkpoint_step=last,
            )
            await append_run_event(
                db,
                run.id,
                "error",
                {
                    "kind": "error",
                    "code": code,
                    "message": "worker lease expired",
                    "log_excerpt": None,
                    "will_retry": False,
                    "ts": iso_now(),
                },
                outbox,
                level="error",
            )
            ok = await transition(
                db,
                run,
                from_statuses=[st],
                to=RunStatus.FAILED,
                outbox=outbox,
                reason="lease_expired",
                error_code=code,
                extra=extra,
                release_gpu=True,
            )
        if ok:
            done.append(f"{run.id}:{run.status.value}")
            await db.execute(
                update(GpuNode).where(GpuNode.current_run_id == run.id).values(current_run_id=None)
            )
    return done


async def reap_jobs(db: AsyncSession) -> int:
    jobs = list(
        (
            await db.execute(
                select(Job)
                .where(Job.status == JobStatus.RUNNING, Job.lease_expires_at < func.now())
                .with_for_update(skip_locked=True)
            )
        ).scalars()
    )
    for j in jobs:
        if j.attempts < j.max_attempts:
            j.status = JobStatus.QUEUED
        else:
            j.status = JobStatus.FAILED
            j.error_code = "worker_lost"
            j.error_message = "worker lease expired"
            j.finished_at = datetime.now(UTC)
        j.lease_owner = None
        j.lease_expires_at = None
    return len(jobs)


async def reap_once(maker: async_sessionmaker[AsyncSession], redis: aioredis.Redis | None) -> list[str]:
    outbox = Outbox()
    async with maker() as db, db.begin():
        done = await reap_runs(db, outbox)
        await reap_jobs(db)
    await outbox.flush(redis)
    if done:
        log.info("reaper handled %s", done)
        if redis is not None:
            with contextlib.suppress(Exception):
                await redis.publish("hibiscus:queue", "reaper")
    return done


async def reaper_loop(
    engine: AsyncEngine,
    maker: async_sessionmaker[AsyncSession],
    redis: aioredis.Redis | None,
    interval_s: float,
) -> None:
    """Leader election by a session-level advisory lock kept on a dedicated connection.

    The lock connection comes from its own single-connection ``NullPool`` engine, NOT from the
    app's request pool: the leader holds it for the life of the process, which used to take one
    of the API pool's slots permanently (and a non-leader held one while it slept between tries).
    """
    from sqlalchemy.pool import NullPool

    lock_engine = create_async_engine(engine.url, poolclass=NullPool)
    try:
        while True:
            try:
                got = False
                async with lock_engine.connect() as conn:
                    got = bool(
                        (await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_ID})).scalar()
                    )
                    await conn.commit()
                    while got:
                        try:
                            await reap_once(maker, redis)
                        except Exception:
                            log.exception("reaper iteration failed")
                        await asyncio.sleep(interval_s)
                        await conn.execute(text("SELECT 1"))  # lock connection still alive?
                        await conn.commit()  # never sit "idle in transaction"
                await asyncio.sleep(interval_s)  # not the leader: no connection held while waiting
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("reaper connection failed; retrying")
                await asyncio.sleep(interval_s)
    finally:
        await lock_engine.dispose()


def _main() -> None:  # pragma: no cover - thin CLI, exercised by the GPU e2e test
    from app.core.settings import get_settings
    from app.runs.settings import get_runs_settings

    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    core = get_settings()
    s = get_runs_settings()

    async def run() -> None:
        engine = create_async_engine(core.database_url)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        redis = aioredis.Redis.from_url(core.redis_url)
        try:
            if args.once:
                print("\n".join(await reap_once(maker, redis)))
            else:
                await reaper_loop(engine, maker, redis, s.reaper_interval_s)
        finally:
            await redis.aclose()
            await engine.dispose()

    asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    _main()
