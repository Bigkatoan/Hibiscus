"""Pre-flight checks (PLAN §3.3, policy-schema.md §4 step 4, OpenAPI ``PreflightReport``)."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, ProblemError
from app.db.models import (
    Checkpoint,
    Dataset,
    DatasetVersion,
    DatasetVersionStatus,
    GpuNode,
    GpuNodeStatus,
    Job,
    JobKind,
    JobResource,
    JobStatus,
    Model,
    ModelStatus,
    Quota,
    ResourceEstimate,
    Run,
    RunStatus,
)
from app.runs.argv import build_argv
from app.runs.catalog import POLICY_META, Catalog, gpu_support_level
from app.runs.config import ResolvedConfig, heldout_split, resolve_config
from app.runs.deps import Principal
from app.runs.schemas import RunCreate
from app.runs.settings import DEFAULT_VLM_MODELS, disallowed_hub_models

ACTIVE = (
    RunStatus.PREPARING,
    RunStatus.RUNNING,
    RunStatus.PAUSING,
    RunStatus.EXPORTING,
    RunStatus.CANCELLING,
)
VRAM_HEADROOM_MB = 512

# Heuristic VRAM (MiB, whole process as NVML sees it) at batch 8, one 640x360 camera, fp32, and
# sec/step on an RTX 3060. Measured by A4 on 2026-11-15 (lerobot 0.7.1, torch 2.15):
#   act      bs8: 2424 MiB NVML (torch peak 1.83 GB), 0.109 s/step (dry-run estimator, golden dataset)
#   smolvla  bs8: 2646 MiB NVML (torch peak 2.34 GB), 0.177 s/step (fine-tune of lerobot/smolvla_base,
#                 freeze_vision_encoder + train_expert_only as in the base config)
# The others are deliberately pessimistic placeholders until the dry-run estimator measures them.
HEURISTIC: dict[str, tuple[int, float]] = {
    "act": (2450, 0.11),
    "diffusion": (6000, 0.30),
    "vqbet": (3500, 0.15),
    "tdmpc": (3000, 0.20),
    "smolvla": (3000, 0.18),
    "pi0": (22000, 3.0),
    "pi05": (22000, 3.0),
}


@dataclass(slots=True)
class Check:
    id: str
    severity: str
    code: str
    message: str
    params: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.params:
            d["params"] = self.params
        return d


@dataclass(slots=True)
class PreflightResult:
    checks: list[Check]
    dataset_version: DatasetVersion | None
    dataset: Dataset | None
    resolved: ResolvedConfig | None
    config_error: ProblemError | None
    heldout: list[int]
    train_eps: list[int]
    requested_gpu_id: str | None
    mixed_precision: str
    argv: list[str]
    estimate: dict[str, Any]
    required_vram_mb: int | None
    estimate_job: dict[str, Any] | None
    seed: int

    @property
    def ok(self) -> bool:
        return not any(c.severity == "error" for c in self.checks)

    def report(self) -> dict[str, Any]:
        cfg = self.resolved.as_dict() if self.resolved else {"policy": {}, "train": {}}
        return {
            "ok": self.ok,
            "checks": [c.as_dict() for c in self.checks],
            "resolved": {
                "gpu_id": self.requested_gpu_id,
                "mixed_precision": self.mixed_precision,
                "config": cfg,
                "heldout_episodes": self.heldout,
                "train_episodes": self.train_eps,
                "lerobot_args": self.argv,
            },
            "estimate": self.estimate,
        }


def camera_keys(features: dict[str, Any]) -> list[str]:
    return sorted(
        k for k, v in features.items() if isinstance(v, dict) and v.get("dtype") in ("video", "image")
    )


def image_shapes(features: dict[str, Any]) -> list[list[int]]:
    """[[C,H,W], ...] in camera-key order (dataset features store HWC)."""
    out = []
    for k in camera_keys(features):
        shape = features[k].get("shape", [])
        if len(shape) == 3:
            h, w, c = shape
            out.append([int(c), int(h), int(w)])
    return out


def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def estimate_cache_key(
    policy_type: str,
    gpu_name: str,
    batch_size: int,
    mixed_precision: str,
    shapes: list[list[int]],
    policy_cfg_hash: str,
    lerobot_version: str,
) -> str:
    return canonical_hash(
        {
            "policy_type": policy_type,
            "gpu_name": gpu_name,
            "batch_size": batch_size,
            "mixed_precision": mixed_precision,
            "image_shapes": shapes,
            "policy_config_hash": policy_cfg_hash,
            "lerobot_version": lerobot_version,
        }
    )


def heuristic_estimate(policy_type: str, batch_size: int, shapes: list[list[int]]) -> tuple[int, float]:
    base, sps = HEURISTIC[policy_type]
    pix = sum(c * h * w for c, h, w in shapes) / (3 * 360 * 640) if shapes else 0.3
    variable = 0.4 * base * (batch_size / 8) * max(pix, 0.3)
    return int(0.6 * base + variable), sps * max(batch_size / 8, 0.25) * max(pix, 0.5)


def resolve_mixed_precision(requested: str, gpu: GpuNode | None) -> tuple[str, bool]:
    """(effective, forced) - run-lifecycle §7.5."""
    if gpu is None or requested == "no":
        return requested, False
    if requested == "bf16" and not gpu.supports_bf16:
        return "no", True
    if requested == "fp16" and not gpu.supports_fast_fp16:
        return "no", True
    return requested, False


async def effective_quota(db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, float]:
    rows = (
        await db.execute(
            select(Quota).where(
                Quota.workspace_id == workspace_id, (Quota.user_id == user_id) | (Quota.user_id.is_(None))
            )
        )
    ).scalars()
    user_q = ws_q = None
    for q in rows:
        if q.user_id is None:
            ws_q = q
        else:
            user_q = q
    chosen = user_q or ws_q
    if chosen is None:
        return {"max_concurrent_runs": 1, "max_queued_runs": 10, "gpu_hours_per_month": 200.0}
    return {
        "max_concurrent_runs": chosen.max_concurrent_runs,
        "max_queued_runs": chosen.max_queued_runs,
        "gpu_hours_per_month": chosen.gpu_hours_per_month,
    }


#: QC-backend-03 / CR-A4-W1: GPU seconds actually used THIS month. Per run:
#: least(gpu_seconds, seconds spent in an active status since the month start, from the run's
#: ``status`` events). Paused / queued runs add nothing while they wait; a run from an earlier
#: month adds only what it ran this month. Same statement as worker/train/quota.py (they must agree).
#: Phase-5 re-verify N6: user-requested ``export_model`` / ``eval_checkpoint`` GPU jobs add their
#: wall time this month too (the automatic end-of-run export is already in the ``exporting`` status).
_GPU_SECONDS_THIS_MONTH = text(
    """
    WITH r AS (
      SELECT id, gpu_seconds FROM runs
      WHERE workspace_id = :w AND (CAST(:u AS uuid) IS NULL OR created_by = CAST(:u AS uuid))
        AND coalesce(finished_at, now()) >= :ms
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
          WHERE j.workspace_id = :w AND (CAST(:u AS uuid) IS NULL OR j.created_by = CAST(:u AS uuid))
            AND j.resource = 'gpu' AND j.kind IN ('export_model', 'eval_checkpoint')
            AND j.payload->>'user_requested' = 'true'
            AND j.started_at IS NOT NULL AND coalesce(j.finished_at, now()) > :ms
        ), 0.0)
    FROM r JOIN act ON act.run_id = r.id
    """
)


async def gpu_hours_this_month(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> float:
    """GPU hours used this month in a workspace (one user's runs, or all when ``user_id`` is None)."""
    start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    val = await db.scalar(_GPU_SECONDS_THIS_MONTH, {"w": workspace_id, "u": user_id, "ms": start})
    return float(val or 0.0) / 3600.0


async def run_preflight(
    db: AsyncSession,
    cat: Catalog,
    principal: Principal,
    body: RunCreate,
    *,
    run_id: str = "{{RUN_ID}}",
    base_config: dict[str, Any] | None = None,
    enqueue_estimate: bool = True,
    hf_init_allowlist: frozenset[str] = frozenset(),
    vlm_allowlist: frozenset[str] = frozenset(DEFAULT_VLM_MODELS),
) -> PreflightResult:
    checks: list[Check] = []
    meta = POLICY_META[body.policy_type]

    # -- dataset --------------------------------------------------------------------------------
    dv = await db.get(DatasetVersion, body.dataset_version_id)
    ds = await db.get(Dataset, dv.dataset_id) if dv is not None else None
    if dv is None or ds is None or ds.workspace_id != body.workspace_id or dv.deleted_at or ds.deleted_at:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "dataset version not found")
    if dv.status != DatasetVersionStatus.READY:
        checks.append(
            Check(
                "dataset_ready", "error", "dataset_version_not_ready", f"dataset version is {dv.status.value}"
            )
        )
    else:
        checks.append(Check("dataset_ready", "info", "ok", "dataset version validated"))
    features: dict[str, Any] = dv.features or {}
    cams = camera_keys(features)
    shapes = image_shapes(features)

    # -- config ---------------------------------------------------------------------------------
    resolved: ResolvedConfig | None = None
    config_error: ProblemError | None = None
    try:
        resolved = resolve_config(
            cat,
            body.policy_type,
            body.config.model_dump(),
            preset=body.preset,
            seed=body.seed,
            base=base_config,
        )
        checks.append(Check("config_schema", "info", "ok", "config valid"))
        checks.append(Check("cross_field", "info", "ok", "cross-field rules satisfied"))
    except ProblemError as exc:
        config_error = exc
        cid = "cross_field" if exc.code == "policy_config_invalid" else "config_schema"
        checks.append(
            Check(cid, "error", exc.code, exc.detail or exc.code, {"errors": exc.ext.get("errors", [])})
        )
    train = resolved.train if resolved else cat.defaults(cat.train_schema)
    policy = resolved.policy if resolved else cat.defaults(cat.policy_schema(body.policy_type))
    raw_seed = train.get("seed")
    seed = int(raw_seed) if isinstance(raw_seed, int) else 1000

    # -- Hub model references (N5) ----------------------------------------------------------------
    for fname, value in disallowed_hub_models(policy, vlm_allowlist).items():
        checks.append(
            Check(
                "config_schema",
                "error",
                "forbidden",
                f"policy.{fname}={value!r} is not on the platform's allow-list of Hugging Face models"
                " (local paths are never accepted)",
                {"field": f"policy.{fname}", "value": str(value), "reason": "hub_model_not_allowed"},
            )
        )

    # -- split ----------------------------------------------------------------------------------
    n_eps = int(dv.total_episodes or 0)
    heldout, train_eps = heldout_split(n_eps, body.heldout_fraction, seed, body.heldout_episodes)
    if n_eps and len(heldout) == 0 and body.heldout_fraction > 0:
        checks.append(Check("feature_dims", "warning", "heldout_too_small", "no held-out episode"))

    # -- camera keys / features ----------------------------------------------------------------
    pt = body.policy_type
    if pt in ("act", "diffusion") and not cams and "observation.environment_state" not in features:
        checks.append(
            Check("camera_keys", "error", "dataset_schema_mismatch", f"{pt} needs at least one camera")
        )
    elif pt == "vqbet" and len(cams) != 1:
        checks.append(
            Check("camera_keys", "error", "dataset_schema_mismatch", "VQ-BeT needs exactly one camera")
        )
    elif pt == "tdmpc" and (len(cams) > 1 or any(s[1] != s[2] for s in shapes)):
        checks.append(
            Check("camera_keys", "error", "dataset_schema_mismatch", "TD-MPC needs at most one square camera")
        )
    elif pt in ("diffusion", "vqbet") and len({tuple(s) for s in shapes}) > 1:
        checks.append(
            Check("camera_keys", "error", "dataset_schema_mismatch", "all cameras must share a shape")
        )
    else:
        checks.append(
            Check("camera_keys", "info", "ok", f"cameras: {', '.join(cams) or 'none'}", {"cameras": cams})
        )
    if "action" not in features:
        checks.append(
            Check("feature_dims", "error", "dataset_schema_mismatch", "dataset has no `action` feature")
        )
    state_dim = int((features.get("observation.state", {}).get("shape") or [0])[0])
    action_dim = int((features.get("action", {}).get("shape") or [0])[0])
    for key, dim in (("max_state_dim", state_dim), ("max_action_dim", action_dim)):
        if key in policy and isinstance(policy[key], int) and dim > policy[key]:
            checks.append(
                Check(
                    "feature_dims",
                    "error",
                    "policy_config_invalid",
                    f"{key}={policy[key]} < dataset dim {dim}",
                )
            )
    crop = policy.get("crop_shape")
    if isinstance(crop, list) and len(crop) == 2 and policy.get("resize_shape") is None:
        for s in shapes:
            if crop[0] > s[1] or crop[1] > s[2]:
                checks.append(
                    Check(
                        "feature_dims",
                        "error",
                        "policy_config_invalid",
                        f"crop_shape {crop} exceeds image {s}",
                    )
                )

    # -- policy requirements ------------------------------------------------------------------
    has_init = body.init_from is not None
    if meta.requires_reward and "next.reward" not in features:
        checks.append(
            Check("policy_requirements", "error", "dataset_schema_mismatch", "TD-MPC requires `next.reward`")
        )
    if meta.requires_peft and not train.get("peft"):
        checks.append(
            Check("policy_requirements", "error", "policy_requires_peft", f"{pt} requires train.peft")
        )
    if meta.requires_peft and not policy.get("gradient_checkpointing", False):
        checks.append(
            Check(
                "policy_requirements",
                "error",
                "policy_config_invalid",
                f"{pt} requires gradient_checkpointing=true",
            )
        )
    if train.get("peft") and not has_init:
        checks.append(Check("init_from", "error", "policy_config_invalid", "PEFT training needs init_from"))
    if body.preset == "finetune" and not has_init:
        checks.append(Check("init_from", "error", "policy_config_invalid", "preset finetune needs init_from"))

    # -- init_from ----------------------------------------------------------------------------
    if body.init_from is not None:
        await _check_init_from(db, body, cams, checks, hf_init_allowlist)

    # -- GPU placement / mixed precision ----------------------------------------------------------
    gpus = list((await db.execute(select(GpuNode).order_by(GpuNode.id))).scalars())
    usable = [g for g in gpus if g.status != GpuNodeStatus.DISABLED]
    eligible = [g for g in usable if gpu_support_level(pt, g.total_vram_mb) != "unsupported"]
    requested_gpu_id: str | None = None
    target: GpuNode | None = None
    if body.gpu != "auto":
        target = next((g for g in gpus if g.id == body.gpu), None)
        if target is None:
            checks.append(Check("gpu_available", "error", "gpu_unknown", f"unknown GPU {body.gpu}"))
        elif target not in eligible:
            checks.append(
                Check(
                    "gpu_available",
                    "error",
                    "gpu_insufficient_vram",
                    f"{pt} is not supported on {target.name}",
                )
            )
        else:
            requested_gpu_id = target.id
    elif not eligible:
        checks.append(Check("gpu_available", "error", "gpu_insufficient_vram", f"no GPU can train {pt}"))
    elif len(eligible) == 1 and len(usable) > 1:
        target = eligible[0]
        requested_gpu_id = target.id
    if target is not None and gpu_support_level(pt, target.total_vram_mb) == "limited":
        checks.append(Check("gpu_available", "warning", "gpu_limited", f"{pt} is limited on {target.name}"))
    if (
        pt == "smolvla"
        and target is not None
        and target.total_vram_mb < 16000
        and int(train["batch_size"]) > 8
    ):
        checks.append(Check("vram", "warning", "batch_size_large", "SmolVLA on 12 GB: keep batch_size <= 8"))
    online = [g for g in eligible if g.status == GpuNodeStatus.ONLINE]
    if eligible and not online:
        checks.append(
            Check("gpu_available", "warning", "gpu_offline", "no eligible GPU is online; run will wait")
        )

    requested_mp = str(train.get("mixed_precision", "no"))
    effective_mp, forced = resolve_mixed_precision(requested_mp, target)
    if forced:
        checks.append(
            Check(
                "mixed_precision",
                "warning",
                "mixed_precision_forced_no",
                f"{target.name if target else 'GPU'} has no {requested_mp}; training runs in fp32",
            )
        )
    elif target is None and requested_mp != "no" and any(not g.supports_bf16 for g in eligible):
        checks.append(
            Check(
                "mixed_precision",
                "warning",
                "mixed_precision_forced_no",
                f"{requested_mp} is forced to fp32 if the run lands on a GPU without it",
            )
        )

    # -- estimate / VRAM ----------------------------------------------------------------------
    bs = int(train["batch_size"])
    est_gpus = [target] if target is not None else eligible
    cfg_hash = canonical_hash(policy)
    estimate: dict[str, Any] = {"source": "heuristic", "gpu_id": target.id if target else None}
    required_vram: int | None = None
    estimate_job: dict[str, Any] | None = None
    cached: ResourceEstimate | None = None
    cached_gpu: GpuNode | None = None
    for g in est_gpus:
        mp_g, _ = resolve_mixed_precision(requested_mp, g)
        key = estimate_cache_key(pt, g.name, bs, mp_g, shapes, cfg_hash, cat.lerobot_version)
        cached = await db.scalar(select(ResourceEstimate).where(ResourceEstimate.cache_key == key))
        if cached is not None:
            cached_gpu = g
            break
    total_steps = int(train["steps"])
    if cached is not None and cached_gpu is not None:
        required_vram = cached.peak_vram_mb
        estimate = {
            "source": "cached",
            "gpu_id": cached_gpu.id,
            "peak_vram_mb": cached.peak_vram_mb,
            "sec_per_step": cached.sec_per_step,
            "total_duration_s": cached.sec_per_step * total_steps,
            "measured_at": cached.updated_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        }
    else:
        vram, sps = heuristic_estimate(pt, bs, shapes)
        estimate.update(
            peak_vram_mb=vram, sec_per_step=sps, total_duration_s=sps * total_steps, measured_at=None
        )
        if est_gpus and resolved is not None and dv.status == DatasetVersionStatus.READY:
            g = est_gpus[0]
            mp_g, _ = resolve_mixed_precision(requested_mp, g)
            estimate_job = {
                "cache_key": estimate_cache_key(pt, g.name, bs, mp_g, shapes, cfg_hash, cat.lerobot_version),
                "policy_type": pt,
                "gpu_name": g.name if target is not None or len(est_gpus) == 1 else None,
                "batch_size": bs,
                "mixed_precision": requested_mp,
                "image_shapes": shapes,
                "policy_config_hash": cfg_hash,
                "lerobot_version": cat.lerobot_version,
                "dataset_version_id": str(dv.id),
                "dataset_repo_id": f"local/{ds.slug}",
                "argv": build_argv(
                    cat,
                    pt,
                    policy,
                    train,
                    run_id="estimate",
                    dataset_repo_id=f"local/{ds.slug}",
                    train_episodes=train_eps,
                    has_init_from=False,
                ),
            }
            if enqueue_estimate and await _ensure_estimate_job(
                db, body.workspace_id, principal, estimate_job
            ):
                estimate["source"] = "pending"
    if estimate.get("peak_vram_mb") is not None and est_gpus:
        need = int(estimate["peak_vram_mb"])
        fits = [g for g in est_gpus if need <= g.total_vram_mb - VRAM_HEADROOM_MB]
        if not fits:
            sev = "error" if estimate["source"] == "cached" else "warning"
            checks.append(
                Check(
                    "vram",
                    sev,
                    "gpu_insufficient_vram",
                    f"estimated {need} MiB exceeds GPU memory",
                    {"peak_vram_mb": need, "gpu_vram_mb": max(g.total_vram_mb for g in est_gpus)},
                )
            )
        else:
            checks.append(Check("vram", "info", "ok", f"estimated {need} MiB", {"peak_vram_mb": need}))

    # -- quota ------------------------------------------------------------------------------------
    q = await effective_quota(db, body.workspace_id, principal.user_id)
    queued = await db.scalar(
        select(func.count())
        .select_from(Run)
        .where(
            Run.workspace_id == body.workspace_id,
            Run.created_by == principal.user_id,
            Run.status.in_([RunStatus.QUEUED, *ACTIVE]),
        )
    )
    used_h = await gpu_hours_this_month(db, body.workspace_id, principal.user_id)
    if int(queued or 0) >= int(q["max_queued_runs"]):
        checks.append(
            Check("quota", "error", "quota_exceeded", "too many queued runs", {"limit": q["max_queued_runs"]})
        )
    elif used_h >= float(q["gpu_hours_per_month"]):
        checks.append(
            Check(
                "quota",
                "error",
                "quota_exceeded",
                "monthly GPU hours exhausted",
                {"limit_h": q["gpu_hours_per_month"], "used_h": round(used_h, 2)},
            )
        )
    else:
        checks.append(Check("quota", "info", "ok", "within quota"))

    argv = (
        build_argv(
            cat,
            pt,
            policy,
            train,
            run_id=run_id,
            dataset_repo_id=f"local/{ds.slug}",
            train_episodes=train_eps,
            has_init_from=has_init,
        )
        if resolved is not None
        else []
    )
    return PreflightResult(
        checks=checks,
        dataset_version=dv,
        dataset=ds,
        resolved=resolved,
        config_error=config_error,
        heldout=heldout,
        train_eps=train_eps,
        requested_gpu_id=requested_gpu_id,
        mixed_precision=effective_mp,
        argv=argv,
        estimate=estimate,
        required_vram_mb=required_vram,
        estimate_job=estimate_job,
        seed=seed,
    )


async def _check_init_from(
    db: AsyncSession,
    body: RunCreate,
    cams: list[str],
    checks: list[Check],
    hf_allowlist: frozenset[str] = frozenset(),
) -> None:
    init = body.init_from
    if init is None:
        return
    ckpt: Checkpoint | None = None
    if init.model_id is not None:
        model = await db.get(Model, init.model_id)
        if model is None or model.workspace_id != body.workspace_id or model.deleted_at is not None:
            checks.append(Check("init_from", "error", "not_found", "init_from model not found"))
            return
        if model.status != ModelStatus.READY:
            checks.append(Check("init_from", "error", "model_not_ready", "init_from model is not ready"))
        ckpt = await db.get(Checkpoint, model.checkpoint_id)
    elif init.checkpoint_id is not None:
        ckpt = await db.get(Checkpoint, init.checkpoint_id)
        if ckpt is None:
            checks.append(
                Check("init_from", "error", "checkpoint_not_found", "init_from checkpoint not found")
            )
            return
    if ckpt is not None:
        src = await db.get(Run, ckpt.run_id)
        if src is None or src.workspace_id != body.workspace_id:
            checks.append(
                Check("init_from", "error", "checkpoint_not_found", "init_from checkpoint not found")
            )
            return
        if src.policy_type != body.policy_type:
            checks.append(
                Check(
                    "init_from", "error", "policy_config_invalid", f"init_from is a {src.policy_type} policy"
                )
            )
        src_dv = await db.get(DatasetVersion, src.dataset_version_id)
        src_cams = camera_keys((src_dv.features or {}) if src_dv else {})
        if src_cams != cams:
            checks.append(
                Check(
                    "camera_keys",
                    "error",
                    "dataset_schema_mismatch",
                    "camera keys differ from the init_from policy",
                    {"expected": src_cams, "got": cams},
                )
            )
        else:
            checks.append(Check("init_from", "info", "ok", f"fine-tune from step {ckpt.step}"))
    if init.hf_repo_id is not None:
        # SEC-input-1: loading a Hub repo makes LeRobot import the processor classes the repo
        # names (arbitrary code on the GPU worker). Only platform-approved repos are accepted.
        if init.hf_repo_id.strip().lower() not in hf_allowlist:
            checks.append(
                Check(
                    "init_from",
                    "error",
                    "forbidden",
                    f"{init.hf_repo_id} is not on the platform's allow-list of Hugging Face repos; "
                    "start from one of your models or checkpoints instead",
                    {"hf_repo_id": init.hf_repo_id, "reason": "hf_repo_not_allowed"},
                )
            )
            return
        checks.append(
            Check("init_from", "warning", "hub_download", f"weights downloaded from {init.hf_repo_id}")
        )


async def _ensure_estimate_job(
    db: AsyncSession, workspace_id: uuid.UUID, principal: Principal, payload: dict[str, Any]
) -> bool:
    """Queue one ``estimate_resources`` GPU job per cache key (dedup on queued/running)."""
    existing = await db.scalar(
        select(Job.id).where(
            Job.kind == JobKind.ESTIMATE_RESOURCES,
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            Job.payload["cache_key"].astext == payload["cache_key"],
        )
    )
    if existing is not None:
        return True
    db.add(
        Job(
            workspace_id=workspace_id,
            kind=JobKind.ESTIMATE_RESOURCES,
            resource=JobResource.GPU,
            payload=payload,
            dataset_version_id=uuid.UUID(payload["dataset_version_id"]),
            created_by=principal.user_id,
            max_attempts=1,
        )
    )
    await db.flush()
    return True
