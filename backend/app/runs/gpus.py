"""``listGpus`` and ``getQueue``."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import func, select, text

from app.db.models import GpuNode, GpuTelemetry, Run, RunStatus
from app.runs.deps import DB, CurrentPrincipal, require_scope
from app.runs.serialize import gpu_to_dict, iso

router = APIRouter(tags=["gpus"])

# Same ordering as the worker claim (run-lifecycle §7.1): priority DESC, decayed 7-day GPU usage
# of the creator ASC, queued_at ASC.
QUEUE_SQL = text(
    """
    WITH usage AS (
      SELECT r.created_by AS user_id,
             sum(r.gpu_seconds * power(0.5,
                 extract(epoch FROM now() - coalesce(r.finished_at, now())) / 86400.0)) AS score
      FROM runs r
      WHERE coalesce(r.finished_at, now()) > now() - interval '7 days'
      GROUP BY r.created_by
    )
    SELECT r.id FROM runs r LEFT JOIN usage u ON u.user_id = r.created_by
    WHERE r.status = 'queued'
    ORDER BY r.priority DESC, coalesce(u.score, 0) ASC, r.queued_at ASC
    """
)


async def _latest_samples(db: DB) -> dict[str, GpuTelemetry]:
    since = datetime.now(UTC) - timedelta(minutes=2)
    sub = (
        select(GpuTelemetry.gpu_node_id, func.max(GpuTelemetry.ts).label("ts"))
        .where(GpuTelemetry.ts > since)
        .group_by(GpuTelemetry.gpu_node_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(GpuTelemetry).join(
                sub, (sub.c.gpu_node_id == GpuTelemetry.gpu_node_id) & (sub.c.ts == GpuTelemetry.ts)
            )
        )
    ).scalars()
    return {r.gpu_node_id: r for r in rows}


def sample_dict(s: GpuTelemetry) -> dict[str, Any]:
    return {
        "gpu_id": s.gpu_node_id,
        "ts": iso(s.ts),
        "util_pct": s.util_pct,
        "mem_used_mb": s.mem_used_mb,
        "mem_total_mb": s.mem_total_mb,
        "temperature_c": s.temperature_c,
        "power_w": s.power_w,
    }


@router.get("/gpus", operation_id="listGpus")
async def list_gpus(request: Request, db: DB, principal: CurrentPrincipal) -> dict[str, Any]:
    require_scope(principal, "runs:read")
    nodes = list((await db.execute(select(GpuNode).order_by(GpuNode.id))).scalars())
    samples = await _latest_samples(db)
    offline_after = request.app.state.runs.settings.gpu_offline_after_s
    items = []
    for g in nodes:
        run = await db.get(Run, g.current_run_id) if g.current_run_id else None
        visible = run is not None and run.workspace_id in principal.workspace_ids_roles
        s = samples.get(g.id)
        items.append(
            gpu_to_dict(
                g,
                offline_after_s=offline_after,
                run=run,
                visible=visible,
                telemetry=sample_dict(s) if s else None,
            )
        )
    return {"items": items}


@router.get("/queue", operation_id="getQueue")
async def get_queue(db: DB, principal: CurrentPrincipal) -> dict[str, Any]:
    require_scope(principal, "runs:read")
    ids = [uuid.UUID(str(r[0])) for r in (await db.execute(QUEUE_SQL)).all()]
    runs = {r.id: r for r in (await db.execute(select(Run).where(Run.id.in_(ids)))).scalars()} if ids else {}
    items = []
    for pos, rid in enumerate(ids, start=1):
        r = runs.get(rid)
        if r is None or r.status != RunStatus.QUEUED:
            continue
        visible = r.workspace_id in principal.workspace_ids_roles
        items.append(
            {
                "position": pos,
                "run_id": str(r.id) if visible else None,
                "run_name": r.name if visible else None,
                "workspace_id": str(r.workspace_id) if visible else None,
                "policy_type": r.policy_type,
                "requested_gpu": r.requested_gpu_id or "auto",
                "required_vram_mb": r.required_vram_mb,
                "queued_at": iso(r.queued_at),
                "estimated_start_at": None,
            }
        )
    return {"items": items}
