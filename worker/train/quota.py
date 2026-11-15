"""Monthly GPU-hour quota as seen by the worker (PLAN §3.3, run-lifecycle §6 ``quota_exceeded``).

Mirrors the API exactly (``backend/app/runs/preflight.py`` ``effective_quota`` +
``gpu_hours_this_month``, used by ``POST /runs`` and ``POST /runs/{id}/resume``) so a run paused
here is also refused on resume, and vice versa:

* limit = per-user quota row of the run's workspace, else the workspace row, else 200 h;
* used = GPU time the creator's runs in that workspace actually used since the start of the current
  UTC month (QC-backend-03, CR-A4-W1 in docs/CONTRACT_NOTES.md). Per run that is
  ``least(runs.gpu_seconds, seconds the run spent in an active status this month)``; the active
  intervals come from the run's ``status`` events (``run_events``, ``data.to``) clipped to the
  month. A paused or queued run therefore adds nothing while it waits, and a run from an earlier
  month adds only the part it ran this month (the old formula added every unfinished run's whole
  lifetime ``gpu_seconds`` to every month, so a quota-paused run locked its owner out for good).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection, select, text

from core.tables import quotas

DEFAULT_GPU_HOURS_PER_MONTH = 200.0

#: GPU seconds used this month (``:ms`` = month start, UTC) by ``:u``'s runs in workspace ``:w``.
#: The backend's ``gpu_hours_this_month`` runs the same statement. User-requested export/eval GPU
#: jobs add their wall time this month (phase-5 re-verify N6).
USED_SECONDS_SQL = text(
    """
    WITH r AS (
      SELECT id, gpu_seconds FROM runs
      WHERE workspace_id = :w AND created_by = :u AND coalesce(finished_at, now()) >= :ms
    ), ev AS (
      SELECT e.run_id, e.created_at AS ts, e.data->>'to' AS st,
             lead(e.created_at) OVER (PARTITION BY e.run_id ORDER BY e.seq) AS next_ts
      FROM run_events e JOIN r ON r.id = e.run_id
      WHERE e.type = 'status'
    ), act AS (
      SELECT run_id,
             sum(extract(epoch FROM coalesce(next_ts, now()) - greatest(ts, :ms))) AS active_s
      FROM ev
      WHERE st IN ('preparing', 'running', 'pausing', 'exporting', 'cancelling')
        AND coalesce(next_ts, now()) > :ms
      GROUP BY run_id
    )
    SELECT coalesce(sum(least(r.gpu_seconds, act.active_s)), 0.0)
      + coalesce((
          SELECT sum(extract(epoch FROM coalesce(j.finished_at, now()) - greatest(j.started_at, :ms)))
          FROM jobs j
          WHERE j.workspace_id = :w AND j.created_by = :u
            AND j.resource = 'gpu' AND j.kind IN ('export_model', 'eval_checkpoint')
            AND j.payload->>'user_requested' = 'true'
            AND j.started_at IS NOT NULL AND coalesce(j.finished_at, now()) > :ms
        ), 0.0)
    FROM r JOIN act ON act.run_id = r.id
    """
)


@dataclass(frozen=True)
class GpuHours:
    used_h: float
    limit_h: float

    @property
    def exhausted(self) -> bool:
        return self.used_h >= self.limit_h

    @property
    def percent(self) -> int:
        return int(100 * self.used_h / self.limit_h) if self.limit_h > 0 else 100


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def gpu_hours(conn: Connection, workspace_id: uuid.UUID, user_id: uuid.UUID) -> GpuHours:
    rows = conn.execute(
        select(quotas.c.user_id, quotas.c.gpu_hours_per_month).where(
            quotas.c.workspace_id == workspace_id,
            (quotas.c.user_id == user_id) | (quotas.c.user_id.is_(None)),
        )
    ).all()
    user_q = next((float(r.gpu_hours_per_month) for r in rows if r.user_id is not None), None)
    ws_q = next((float(r.gpu_hours_per_month) for r in rows if r.user_id is None), None)
    limit = user_q if user_q is not None else ws_q if ws_q is not None else DEFAULT_GPU_HOURS_PER_MONTH
    used_s = conn.execute(
        USED_SECONDS_SQL, {"w": workspace_id, "u": user_id, "ms": month_start()}
    ).scalar_one()
    return GpuHours(used_h=float(used_s or 0.0) / 3600.0, limit_h=limit)
