"""Quota resolution and usage (ADR-0009; defaults CONTRACT_NOTES §4.8).

Effective limits: per-user row (workspace_id, user_id) overrides the workspace row
(workspace_id, NULL), which overrides the built-in defaults. A3/A4 enforce quotas with
:func:`effective_limits` (``quota_exceeded`` 403 is theirs to raise).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Float, and_, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Dataset, DatasetVersion, Model, Quota, Run, RunStatus

DEFAULT_LIMITS: dict[str, Any] = {
    "max_concurrent_runs": 1,
    "max_queued_runs": 10,
    "gpu_hours_per_month": 200.0,
    "storage_bytes": 200 * 1024**3,
    "max_upload_bytes": 50 * 1024**3,
}
LIMIT_KEYS = tuple(DEFAULT_LIMITS)
ACTIVE_STATUSES = (
    RunStatus.PREPARING,
    RunStatus.RUNNING,
    RunStatus.PAUSING,
    RunStatus.EXPORTING,
    RunStatus.CANCELLING,
)
FAIR_SHARE_HALF_LIFE_H = 24.0


def limits_of(q: Quota) -> dict[str, Any]:
    return {
        "max_concurrent_runs": int(q.max_concurrent_runs),
        "max_queued_runs": int(q.max_queued_runs),
        "gpu_hours_per_month": float(q.gpu_hours_per_month),
        "storage_bytes": int(q.storage_bytes),
        "max_upload_bytes": int(q.max_upload_bytes),
    }


def quota_out(q: Quota) -> dict[str, Any]:
    return {
        "id": str(q.id),
        "workspace_id": str(q.workspace_id),
        "user_id": str(q.user_id) if q.user_id else None,
        **limits_of(q),
    }


async def effective_limits(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> dict[str, Any]:
    rows = (await db.execute(select(Quota).where(Quota.workspace_id == workspace_id))).scalars().all()
    ws_row = next((q for q in rows if q.user_id is None), None)
    limits = dict(DEFAULT_LIMITS) if ws_row is None else limits_of(ws_row)
    if user_id is not None:
        user_row = next((q for q in rows if q.user_id == user_id), None)
        if user_row is not None:
            limits = limits_of(user_row)
    return limits


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def run_counts(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> tuple[int, int, float]:
    """(active_runs, queued_runs, gpu_hours_this_month)."""
    conds = [Run.workspace_id == workspace_id]
    if user_id is not None:
        conds.append(Run.created_by == user_id)
    row = (
        await db.execute(
            select(
                func.count().filter(Run.status.in_(ACTIVE_STATUSES)),
                func.count().filter(Run.status == RunStatus.QUEUED),
            ).where(and_(*conds))
        )
    ).one()
    # QC-backend-03: same "actually ran this month" accounting as preflight and the worker quota.
    from app.runs.preflight import gpu_hours_this_month  # avoid import cycle

    hours = await gpu_hours_this_month(db, workspace_id, user_id)
    return int(row[0]), int(row[1]), hours


async def storage_used(db: AsyncSession, workspace_id: uuid.UUID) -> int:
    ds = (
        await db.execute(
            select(func.coalesce(func.sum(DatasetVersion.size_bytes), 0))
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(
                Dataset.workspace_id == workspace_id,
                Dataset.deleted_at.is_(None),
                DatasetVersion.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    models = (
        await db.execute(
            select(func.coalesce(func.sum(Model.bundle_size_bytes), 0)).where(
                Model.workspace_id == workspace_id, Model.deleted_at.is_(None)
            )
        )
    ).scalar_one()
    return int(ds or 0) + int(models or 0)


async def fair_share_hours_7d(db: AsyncSession, user_id: uuid.UUID) -> float:
    """Decayed GPU-hours of the user's runs in the trailing 7 days (half-life 24 h).

    Approximation for display; the scheduler's canonical SQL is A4's (run-lifecycle.md §7.1)."""
    now = datetime.now(UTC)
    ref = func.coalesce(Run.finished_at, now)
    age_h = func.extract("epoch", now - ref) / 3600.0
    decay = func.power(0.5, cast(age_h, Float) / FAIR_SHARE_HALF_LIFE_H)
    total = (
        await db.execute(
            select(
                func.coalesce(func.sum(Run.gpu_seconds * case((Run.gpu_seconds > 0, decay), else_=0.0)), 0.0)
            ).where(
                Run.created_by == user_id,
                or_(Run.finished_at.is_(None), Run.finished_at >= now - timedelta(days=7)),
            )
        )
    ).scalar_one()
    return float(total) / 3600.0
