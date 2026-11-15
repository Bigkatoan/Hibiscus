"""Glue between the train worker's export hook and the bundle builder.

``train.runner`` (A4) calls :func:`run_export` after ``lerobot-train`` finishes (run status
``exporting``, same lease and GPU) — see ``core/export_api.py``. This module:

1. gathers run / dataset / GPU / metric facts from Postgres,
2. calls :func:`export.bundle.build_bundle` (eval, ONNX, parity, verification, zip),
3. uploads the zip to ``s3://<artifacts>/models/<model_id>/<bundle_name>.zip``
   (docs/handoff/A5-export.md "Integration notes"),
4. fills the ``models`` row (status, bundle_*, manifest, verification, onnx_*, eval_metrics).

It never touches ``runs.status``; the caller applies run-lifecycle §5 from the returned outcome.
Storage failures are raised as :class:`core.s3.StorageError` so the caller treats them as infra
errors (retry); everything else that goes wrong inside the bundle is reported, not raised.
"""

from __future__ import annotations

import json
import logging
import math
import shutil
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, select, text

from core.bus import Bus
from core.export_api import ExportAbortedError, ExportContext, ExportOutcome
from core.pretrained_guard import UntrustedPretrainedError
from core.s3 import ObjectStore
from core.settings import WorkerSettings
from core.tables import dataset_versions, datasets, gpu_nodes, run_metrics, runs
from export.bundle import build_bundle
from export.logs import MetricRow
from export.types import BundleRequest, DatasetInfo, ExportOptions, RunInfo, TrainingInfo

log = logging.getLogger("hibiscus.export.pipeline")

_OPTION_KEYS = set(ExportOptions.model_fields)


def _training_info(
    engine: Engine, ctx: ExportContext
) -> tuple[RunInfo, DatasetInfo, TrainingInfo, list[MetricRow]]:
    with engine.connect() as conn:
        r = conn.execute(select(runs).where(runs.c.id == ctx.run_id)).mappings().one()
        dv = (
            conn.execute(select(dataset_versions).where(dataset_versions.c.id == r["dataset_version_id"]))
            .mappings()
            .one()
        )
        ds = conn.execute(select(datasets).where(datasets.c.id == dv["dataset_id"])).mappings().one()
        gpu_name = "unknown"
        if r["gpu_node_id"] is not None:
            gpu_name = (
                conn.execute(
                    select(gpu_nodes.c.name).where(gpu_nodes.c.id == r["gpu_node_id"])
                ).scalar_one_or_none()
                or "unknown"
            )
        rows = conn.execute(
            select(run_metrics.c.step, run_metrics.c.key, run_metrics.c.value, run_metrics.c.ts)
            .where(run_metrics.c.run_id == ctx.run_id)
            .order_by(run_metrics.c.step, run_metrics.c.key)
        ).all()
    metrics = [MetricRow(step=int(s), key=str(k), value=float(v), ts=ts) for s, k, v, ts in rows]
    losses = [m.value for m in metrics if m.key == "loss" and math.isfinite(m.value)]
    config: dict[str, Any] = dict(r["config"] or {})
    mp = r["mixed_precision_effective"] or r["mixed_precision_requested"] or "no"
    run = RunInfo(
        id=str(r["id"]), number=int(r["number"]), name=str(r["name"]), workspace_id=str(r["workspace_id"])
    )
    dataset = DatasetInfo(
        dataset_id=str(ds["id"]),
        version_id=str(dv["id"]),
        version=int(dv["version"]),
        name=str(ds["name"]),
        content_hash=str(dv["content_hash"] or "0" * 64),
        repo_id=ctx.dataset_repo_id,
        root=ctx.dataset_root,
    )
    training = TrainingInfo(
        seed=int(r["seed"]),
        total_steps=int(r["total_steps"]),
        batch_size=int((config.get("train") or {}).get("batch_size") or config.get("batch_size") or 0),
        mixed_precision=str(mp),  # type: ignore[arg-type]  # DB enum == Literal values
        gpu_name=str(gpu_name),
        heldout_episodes=list(ctx.heldout_episodes),
        train_episodes=list(ctx.train_episodes),
        gpu_seconds=float(r["gpu_seconds"] or 0.0),
        final_loss=losses[-1] if losses else None,
    )
    return run, dataset, training, metrics


def run_export(
    ctx: ExportContext, *, engine: Engine, store: ObjectStore, bus: Bus | None, settings: WorkerSettings
) -> ExportOutcome:
    run, dataset, training, metrics = _training_info(engine, ctx)
    options = ExportOptions(**{k: v for k, v in ctx.options.items() if k in _OPTION_KEYS})
    if ctx.work_dir.exists():
        shutil.rmtree(ctx.work_dir)
    ctx.work_dir.mkdir(parents=True)
    req = BundleRequest(
        model_id=str(ctx.model_id),
        run=run,
        dataset=dataset,
        training=training,
        pretrained_dir=ctx.pretrained_model_dir,
        checkpoint_step=ctx.step,
        work_dir=ctx.work_dir,
        options=options,
        train_logs=list(ctx.log_files),
        metrics=metrics,
        image_digest=settings.image_digest or ("sha256:" + "0" * 64),
        hibiscus_version=settings.worker_version,
        # parity + ONNX always run on CPU; eval on CPU too (deterministic, avoids sm_60/P40 torch issues)
        eval_device="cpu",
        load_check_python=ctx.load_check_python,
        abort_check=ctx.check_abort,
    )
    try:
        res = build_bundle(req)
    except FileNotFoundError as exc:
        log.exception("bundle input missing")
        _mark(engine, ctx, status="failed", onnx_status="failed", onnx_detail=f"bundle input missing: {exc}")
        return ExportOutcome(model_status="failed", onnx_status="failed", error_message=str(exc))
    except ExportAbortedError:
        shutil.rmtree(ctx.work_dir, ignore_errors=True)
        raise
    except UntrustedPretrainedError as exc:
        log.error("checkpoint rejected before export: %s", exc)
        why = f"checkpoint rejected: {exc}"[:2000]
        _mark(engine, ctx, status="failed", onnx_status="failed", onnx_detail=why)
        return ExportOutcome(model_status="failed", onnx_status="failed", error_message=why)

    ctx.check_abort()  # cancelled while zipping: publish nothing (QC-backend-05)
    key = f"models/{ctx.model_id}/{res.bundle_name}.zip"
    store.upload_file(res.zip_path, settings.bucket_artifacts, key)  # StorageError -> caller retries
    status = "ready" if res.verified else "failed"
    _mark(
        engine,
        ctx,
        status=status,
        bundle_uri=f"s3://{settings.bucket_artifacts}/{key}",
        bundle_sha256=res.zip_sha256,
        bundle_size_bytes=res.zip_size,
        manifest=res.manifest,
        verified=res.verified,
        verification=res.verification.to_json(),
        onnx_status=res.api_onnx_status,
        onnx_detail=res.onnx_detail,
        eval_metrics=res.eval_metrics,
    )
    if res.eval_metrics and bus is not None:
        summary = res.eval_summary or {}
        bus.publish_run(
            str(ctx.run_id),
            "eval",
            {  # OpenAPI EvalEvent (kind, step, action_mae, action_mse, ts) + ids and summary
                "kind": "eval",
                "model_id": str(ctx.model_id),
                "checkpoint_id": str(ctx.checkpoint_id),
                "step": ctx.step,
                **summary,
                "summary": res.eval_summary,
                "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
    # keep only the zip's sibling bundle dir out of scratch; the zip is in object storage now
    shutil.rmtree(ctx.work_dir, ignore_errors=True)
    detail = None if res.verified else (res.verification.details or res.onnx_detail or "verification failed")
    return ExportOutcome(
        model_status=status, verified=res.verified, onnx_status=res.api_onnx_status, error_message=detail
    )


_JSON_COLS = {"manifest", "verification", "eval_metrics"}
_ALLOWED = {
    "status",
    "bundle_uri",
    "bundle_sha256",
    "bundle_size_bytes",
    "manifest",
    "verified",
    "verification",
    "onnx_status",
    "onnx_detail",
    "eval_metrics",
}


def _mark(engine: Engine, ctx: ExportContext, **values: Any) -> None:
    cols = [c for c in values if c in _ALLOWED]
    sets = ", ".join(f"{c} = CAST(:{c} AS jsonb)" if c in _JSON_COLS else f"{c} = :{c}" for c in cols)
    params = {
        c: (json.dumps(values[c]) if c in _JSON_COLS and values[c] is not None else values[c]) for c in cols
    }
    params["id"] = ctx.model_id
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE models SET {sets}, updated_at = now() WHERE id = :id"), params)  # noqa: S608 - column names from _ALLOWED
