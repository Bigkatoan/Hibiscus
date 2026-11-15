"""ORM rows -> OpenAPI response dicts (Run, Checkpoint, Model, GpuNode, Job, events)."""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Checkpoint,
    Dataset,
    DatasetVersion,
    GpuNode,
    Job,
    Model,
    Run,
    RunEvent,
    RunStatus,
    User,
)
from app.runs.deps import Principal, has_scope, role_at_least


def iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


def finite_or_none(v: Any) -> float | None:
    if v is None:
        return None
    f = float(v)
    return f if math.isfinite(f) else None


EXPORT_DEFAULTS = {"onnx": True, "onnx_fp16": False, "eval": True}
ACTIVE = {"preparing", "running", "pausing", "exporting", "cancelling"}


def allowed_actions(run: Run, principal: Principal, role: str, *, has_checkpoint: bool) -> list[str]:
    """Derived from the run-lifecycle transition table and the caller's role (§2)."""
    if role == "viewer" or not has_scope(principal, "runs:write"):
        return []
    own = run.created_by == principal.user_id
    if not own and not role_at_least(role, "admin"):
        return ["clone"] if role_at_least(role, "member") else []
    st = run.status.value
    out: list[str] = []
    if st in {"queued", "paused", *ACTIVE} and st != "cancelling":
        out.append("cancel")
    if st in {"preparing", "running"} or (st == "pausing" and run.desired_state == "pause"):
        out.append("pause")
    if st == "paused" or (st == "failed" and has_checkpoint):
        out.append("resume")
    out.append("clone")
    if st == "queued":
        out.append("edit")
    else:
        out.append("edit")  # rename stays allowed
    if has_checkpoint:
        out += ["export", "eval"]
    return out


def run_to_dict(
    run: Run,
    *,
    dataset: Dataset,
    version: DatasetVersion,
    creator: User | None,
    principal: Principal,
    role: str,
    last_checkpoint_step: int | None,
    model_id: uuid.UUID | None,
    queue_position: int | None,
) -> dict[str, Any]:
    cfg = run.config or {}
    train = cfg.get("train", {})
    save_freq = int(train.get("save_freq", 10000) or 0)
    total = run.total_steps
    cur = run.current_step
    nxt: int | None = None
    if run.status.value not in {"succeeded", "failed", "cancelled"}:
        nxt = min(((cur // save_freq) + 1) * save_freq, total) if save_freq > 0 else total
    lm = run.latest_metrics or {}
    sps = lm.get("_steps_per_s")
    progress = {
        "current_step": cur,
        "total_steps": total,
        "steps_per_s": finite_or_none(sps),
        "eta_s": (total - cur) / float(sps) if isinstance(sps, int | float) and sps and sps > 0 else None,
        "next_checkpoint_step": nxt,
        "last_checkpoint_step": last_checkpoint_step,
    }
    estimate = run.estimate
    manifest_init = (run.manifest or {}).get("_init_from") if run.manifest else None
    init_from: dict[str, Any] | None = None
    if run.init_from_model_id:
        init_from = {"model_id": str(run.init_from_model_id)}
    elif run.init_from_checkpoint_id:
        init_from = {"checkpoint_id": str(run.init_from_checkpoint_id)}
    elif isinstance(manifest_init, dict):
        init_from = manifest_init
    elif isinstance(cfg.get("_init_from"), dict):
        init_from = cfg["_init_from"]
    export = {**EXPORT_DEFAULTS, **(cfg.get("_export") or {})}
    return {
        "id": str(run.id),
        "workspace_id": str(run.workspace_id),
        "number": run.number,
        "name": run.name,
        "status": run.status.value,
        "status_changed_at": iso(run.status_changed_at),
        "desired_state": run.desired_state,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "policy_type": run.policy_type,
        "preset": run.preset,
        "dataset_version_id": str(run.dataset_version_id),
        "dataset": {"id": str(dataset.id), "name": dataset.name, "version": version.version},
        "config": {"policy": cfg.get("policy", {}), "train": train},
        "heldout_episodes": list(run.heldout_episodes or []),
        "seed": int(run.seed),
        "progress": progress,
        "latest_metrics": {k: finite_or_none(v) for k, v in lm.items() if not k.startswith("_")},
        "gpu_id": run.gpu_node_id,
        "requested_gpu": run.requested_gpu_id or "auto",
        "mixed_precision_requested": run.mixed_precision_requested.value,
        "mixed_precision_effective": run.mixed_precision_effective.value
        if run.mixed_precision_effective
        else None,
        "priority": run.priority,
        "queue_position": queue_position,
        "attempt": run.attempt,
        "infra_retries_used": run.infra_retries_used,
        "estimate": estimate,
        "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
        "init_from": init_from,
        "export": export,
        "model_id": str(model_id) if model_id else None,
        "gpu_seconds": float(run.gpu_seconds),
        "created_by": {"id": str(run.created_by), "display_name": creator.display_name if creator else ""},
        "created_at": iso(run.created_at),
        "updated_at": iso(run.updated_at),
        "queued_at": iso(run.queued_at),
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
        "allowed_actions": allowed_actions(
            run, principal, role, has_checkpoint=last_checkpoint_step is not None
        ),
    }


async def runs_to_dicts(
    db: AsyncSession, runs: list[Run], principal: Principal, roles: Mapping[uuid.UUID, str]
) -> list[dict[str, Any]]:
    if not runs:
        return []
    ids = [r.id for r in runs]
    dv_ids = {r.dataset_version_id for r in runs}
    versions = {
        v.id: v
        for v in (await db.execute(select(DatasetVersion).where(DatasetVersion.id.in_(dv_ids)))).scalars()
    }
    ds_ids = {v.dataset_id for v in versions.values()}
    datasets = {d.id: d for d in (await db.execute(select(Dataset).where(Dataset.id.in_(ds_ids)))).scalars()}
    users = {
        u.id: u
        for u in (await db.execute(select(User).where(User.id.in_({r.created_by for r in runs})))).scalars()
    }
    ckpt_rows = await db.execute(
        select(Checkpoint.run_id, func.max(Checkpoint.step))
        .where(Checkpoint.run_id.in_(ids))
        .group_by(Checkpoint.run_id)
    )
    last_ckpt: dict[uuid.UUID, int] = {row[0]: int(row[1]) for row in ckpt_rows.all()}
    final_models: dict[uuid.UUID, uuid.UUID] = {}
    for m in (
        await db.execute(
            select(Model).where(Model.run_id.in_(ids), Model.deleted_at.is_(None)).order_by(Model.step)
        )
    ).scalars():
        final_models[m.run_id] = m.id
    positions = await queue_positions(db)
    out = []
    for r in runs:
        v = versions[r.dataset_version_id]
        out.append(
            run_to_dict(
                r,
                dataset=datasets[v.dataset_id],
                version=v,
                creator=users.get(r.created_by),
                principal=principal,
                role=roles.get(r.workspace_id, "viewer"),
                last_checkpoint_step=last_ckpt.get(r.id),
                model_id=final_models.get(r.id),
                queue_position=positions.get(r.id),
            )
        )
    return out


async def queue_positions(db: AsyncSession) -> dict[uuid.UUID, int]:
    """1-based positions in a priority/fair-share-agnostic approximation (priority DESC, queued_at)."""
    rows = (
        await db.execute(
            select(Run.id)
            .where(Run.status == RunStatus.QUEUED)
            .order_by(Run.priority.desc(), Run.queued_at.asc())
        )
    ).scalars()
    return {rid: i + 1 for i, rid in enumerate(rows)}


def checkpoint_to_dict(c: Checkpoint, model_id: uuid.UUID | None) -> dict[str, Any]:
    ev = c.eval_metrics or None
    summary = None
    if isinstance(ev, dict) and isinstance(ev.get("overall"), dict):
        summary = {"action_mae": ev["overall"].get("mae"), "action_mse": ev["overall"].get("mse")}
    return {
        "id": str(c.id),
        "run_id": str(c.run_id),
        "step": c.step,
        "size_bytes": int(c.size_bytes),
        "is_last": c.is_last,
        "has_training_state": c.has_training_state,
        "model_id": str(model_id) if model_id else None,
        "eval_summary": summary,
        "created_at": iso(c.created_at),
    }


def model_to_dict(
    m: Model, *, run: Run, dataset: Dataset | None, version: DatasetVersion | None, creator: User | None
) -> dict[str, Any]:
    ev = m.eval_metrics or None
    summary = None
    if isinstance(ev, dict) and isinstance(ev.get("overall"), dict):
        summary = {"action_mae": ev["overall"].get("mae"), "action_mse": ev["overall"].get("mse")}
    verification = (
        m.verification if isinstance(m.verification, dict) and "checked_at" in m.verification else None
    )
    d: dict[str, Any] = {
        "id": str(m.id),
        "workspace_id": str(m.workspace_id),
        "name": m.name,
        "policy_type": m.policy_type,
        "run_id": str(m.run_id),
        "run_number": run.number,
        "checkpoint_id": str(m.checkpoint_id),
        "step": m.step,
        "status": m.status.value,
        "error_message": (m.verification or {}).get("error_message")
        if isinstance(m.verification, dict)
        else None,
        "verified": m.verified,
        "verification": verification,
        "onnx_status": m.onnx_status.value,
        "onnx_detail": m.onnx_detail,
        "bundle_size_bytes": m.bundle_size_bytes,
        "bundle_sha256": m.bundle_sha256,
        "eval_summary": summary,
        "hub_repo_id": m.hub_repo_id,
        "hub_pushed_at": iso(m.hub_pushed_at),
        "created_by": {
            "id": str(m.created_by or run.created_by),
            "display_name": creator.display_name if creator else "",
        },
        "created_at": iso(m.created_at),
    }
    if dataset is not None and version is not None:
        d["dataset"] = {"id": str(dataset.id), "name": dataset.name, "version": version.version}
    return d


def job_to_dict(j: Job) -> dict[str, Any]:
    return {
        "id": str(j.id),
        "workspace_id": str(j.workspace_id),
        "kind": j.kind.value,
        "status": j.status.value,
        "progress": float(j.progress),
        "stage": (j.result or {}).get("stage") if isinstance(j.result, dict) else None,
        "error_code": j.error_code,
        "error_message": j.error_message,
        "result": j.result,
        "run_id": str(j.run_id) if j.run_id else None,
        "dataset_version_id": str(j.dataset_version_id) if j.dataset_version_id else None,
        "model_id": str(j.model_id) if j.model_id else None,
        "created_at": iso(j.created_at),
        "started_at": iso(j.started_at),
        "finished_at": iso(j.finished_at),
    }


def gpu_to_dict(
    g: GpuNode,
    *,
    offline_after_s: float,
    run: Run | None,
    visible: bool,
    telemetry: dict[str, Any] | None,
) -> dict[str, Any]:
    status = g.status.value
    if status == "online" and (
        g.last_heartbeat_at is None
        or (datetime.now(UTC) - g.last_heartbeat_at).total_seconds() > offline_after_s
    ):
        status = "offline"
    current = None
    if run is not None:
        current = {
            "id": str(run.id) if visible else None,
            "name": run.name if visible else None,
            "workspace_id": str(run.workspace_id) if visible else None,
            "step": run.current_step,
            "total_steps": run.total_steps,
        }
    return {
        "id": g.id,
        "name": g.name,
        "total_vram_mb": g.total_vram_mb,
        "compute_capability": g.compute_capability,
        "supports_bf16": g.supports_bf16,
        "supports_fast_fp16": g.supports_fast_fp16,
        "status": status,
        "last_heartbeat_at": iso(g.last_heartbeat_at),
        "current_run": current,
        "telemetry": telemetry,
    }


def event_record(e: RunEvent) -> dict[str, Any]:
    return {
        "seq": int(e.seq),
        "type": e.type,
        "ts": iso(e.created_at),
        "attempt": int(e.attempt),
        "level": e.level,
        "data": e.data,
    }
