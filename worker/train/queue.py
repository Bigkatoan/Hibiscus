"""Run claim (run-lifecycle §7.1): one statement under ``FOR UPDATE OF r SKIP LOCKED`` with fair-share."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import ARRAY, Connection, String, bindparam, func, text, update

from core.events import Outbox, transition
from core.tables import gpu_nodes, runs

#: Fair-share: decayed (half-life 1 day) GPU seconds of the creator over the last 7 days.
#: ``effective_max_concurrent_runs`` = per-user quota row, else workspace row, else 1.
CLAIM_SQL = text(
    """
    WITH usage AS (
      SELECT r.created_by AS user_id,
             sum(r.gpu_seconds * power(0.5,
                 extract(epoch FROM now() - coalesce(r.finished_at, now())) / 86400.0)) AS score
      FROM runs r
      WHERE coalesce(r.finished_at, now()) > now() - interval '7 days'
      GROUP BY r.created_by
    ), active AS (
      SELECT created_by, workspace_id, count(*) AS n FROM runs
      WHERE status IN ('preparing','running','pausing','exporting','cancelling')
      GROUP BY created_by, workspace_id
    )
    SELECT r.id FROM runs r
    LEFT JOIN usage u ON u.user_id = r.created_by
    LEFT JOIN active a ON a.created_by = r.created_by AND a.workspace_id = r.workspace_id
    LEFT JOIN quotas qu ON qu.workspace_id = r.workspace_id AND qu.user_id = r.created_by
    LEFT JOIN quotas qw ON qw.workspace_id = r.workspace_id AND qw.user_id IS NULL
    WHERE r.status = 'queued'
      AND (r.requested_gpu_id IS NULL OR r.requested_gpu_id = :gpu_id)
      AND coalesce(r.required_vram_mb, 0) <= :gpu_total_vram_mb - 512
      AND r.policy_type <> ALL(:unsupported)
      AND coalesce(a.n, 0) < coalesce(qu.max_concurrent_runs, qw.max_concurrent_runs, 1)
      AND (r.created_by::text || ':' || r.workspace_id::text) <> ALL(:skip)
    ORDER BY r.priority DESC, coalesce(u.score, 0) ASC, r.queued_at ASC
    LIMIT 1
    FOR UPDATE OF r SKIP LOCKED
    """
).bindparams(bindparam("unsupported", type_=ARRAY(String(32))), bindparam("skip", type_=ARRAY(String(80))))


#: QC-backend-04: the ``active`` CTE counts runs in the statement's snapshot, so two workers claiming
#: at the same moment both saw ``n = 0`` and started two runs for a user whose limit is 1. Now the
#: claim takes a per-(user, workspace) transaction lock for its candidate and re-counts that user's
#: active runs in a NEW statement (READ COMMITTED: fresh snapshot, taken after the lock, i.e. after
#: the other claim committed). Over the limit => that user is skipped and the next candidate tried.
#: Claims for different users still run in parallel (SKIP LOCKED). Two-key advisory lock space,
#: class 7003 (the API uses class 7002 for run creation; single-key 7001/7002 are leader locks).
CLAIM_LOCK_CLASS = 7003
_USER_LOCK_SQL = text("SELECT pg_advisory_xact_lock(:c, hashtext(:k))")
_RECHECK_SQL = text(
    """
    SELECT (SELECT count(*) FROM runs
            WHERE created_by = :u AND workspace_id = :w
              AND status IN ('preparing','running','pausing','exporting','cancelling'))
         < coalesce((SELECT max_concurrent_runs FROM quotas WHERE workspace_id = :w AND user_id = :u),
                    (SELECT max_concurrent_runs FROM quotas WHERE workspace_id = :w AND user_id IS NULL),
                    1)
    """
)
_OWNER_SQL = text("SELECT created_by, workspace_id FROM runs WHERE id = :r")
MAX_CANDIDATES = 5


def claim_run(
    conn: Connection,
    *,
    gpu_id: str,
    gpu_total_vram_mb: int,
    unsupported: list[str],
    worker_id: str,
    lease_ttl_s: int,
    outbox: Outbox,
) -> uuid.UUID | None:
    skip: list[str] = []
    run_id: uuid.UUID | None = None
    for _ in range(MAX_CANDIDATES):
        row = conn.execute(
            CLAIM_SQL,
            {
                "gpu_id": gpu_id,
                "gpu_total_vram_mb": gpu_total_vram_mb,
                "unsupported": unsupported,
                "skip": skip,
            },
        ).one_or_none()
        if row is None:
            return None
        owner = conn.execute(_OWNER_SQL, {"r": row.id}).one()
        key = f"{owner.created_by}:{owner.workspace_id}"
        conn.execute(_USER_LOCK_SQL, {"c": CLAIM_LOCK_CLASS, "k": key})
        if conn.execute(_RECHECK_SQL, {"u": owner.created_by, "w": owner.workspace_id}).scalar_one():
            run_id = row.id
            break
        skip.append(key)  # a concurrent claim filled this user's slots meanwhile
    if run_id is None:
        return None
    ok = transition(
        conn,
        run_id,
        from_statuses=["queued"],
        to="preparing",
        outbox=outbox,
        reason="claimed",
        extra={
            "gpu_node_id": gpu_id,
            "lease_owner": worker_id,
            "lease_expires_at": func.now() + timedelta(seconds=lease_ttl_s),
            "heartbeat_at": func.now(),
            "attempt": runs.c.attempt + 1,
            "started_at": func.coalesce(runs.c.started_at, func.now()),
            "desired_state": "run",
        },
    )
    if not ok:  # pragma: no cover - row is locked by us
        return None
    conn.execute(update(gpu_nodes).where(gpu_nodes.c.id == gpu_id).values(current_run_id=run_id))
    return run_id
