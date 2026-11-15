"""GPU job handler for ``export_model`` (QC-backend-02; run-lifecycle §5 D3/T15 recovery path).

Enqueued by the API for

* ``POST /runs/{id}/checkpoints/{step}/export`` - payload ``{checkpoint_id, step, options}``, the
  ``models`` row exists in ``pending``: build the bundle with :func:`export.pipeline.run_export`
  (the same code as the end-of-training export) and fill the row;
* ``POST /models/{id}/verify`` - payload ``{verify_only: true, ...}`` on a ``ready`` model:
  re-run the checks on the delivered zip (:func:`export.verify.reverify_bundle`).

The job lease is kept alive by :class:`core.jobs.JobKeeper` for the whole job. Storage errors are
infra errors: the job goes back to the queue while it has attempts left.

Entry point (``train.worker._job_handlers``): :func:`handle_job`.
"""

from __future__ import annotations

import contextlib
import logging
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import Engine, select, update

from core.events import Outbox, append_run_event, iso, utcnow
from core.export_api import ExportAbortedError, ExportContext, ExportOutcome
from core.jobs import ClaimedJob, JobKeeper, finish_job, requeue_job
from core.pretrained_guard import UntrustedPretrainedError, validate_pretrained_dir
from core.s3 import ObjectStore, StorageError, parse_s3_uri
from core.tables import checkpoints, dataset_versions, datasets, jobs, models, runs

if TYPE_CHECKING:  # pragma: no cover
    from train.runner import WorkerContext

log = logging.getLogger("hibiscus.export.jobs")
DEFAULT_OPTIONS: dict[str, Any] = {"onnx": True, "onnx_fp16": False, "eval": True}


class JobFailedError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class RunFacts:
    run: Any
    checkpoint: Any
    dataset_version: Any
    dataset: Any


def load_run_facts(engine: Engine, job: ClaimedJob) -> RunFacts:
    ck_id = job.payload.get("checkpoint_id")
    with engine.connect() as conn:
        run = conn.execute(select(runs).where(runs.c.id == job.run_id)).one_or_none()
        ck = (
            conn.execute(select(checkpoints).where(checkpoints.c.id == uuid.UUID(str(ck_id)))).one_or_none()
            if ck_id
            else None
        )
        if run is None or ck is None or ck.run_id != run.id:
            raise JobFailedError("checkpoint_not_found", "run or checkpoint not found")
        dv = conn.execute(
            select(dataset_versions).where(dataset_versions.c.id == run.dataset_version_id)
        ).one()
        ds = conn.execute(select(datasets).where(datasets.c.id == dv.dataset_id)).one()
    return RunFacts(run=run, checkpoint=ck, dataset_version=dv, dataset=ds)


def ensure_dataset(ctx: WorkerContext, facts: RunFacts) -> Path:
    from train.dataset_cache import DatasetUnavailableError

    dv = facts.dataset_version
    if not dv.storage_prefix:
        raise JobFailedError("dataset_unavailable", "dataset version has no storage prefix")
    try:
        return ctx.datasets.ensure(str(dv.id), dv.storage_prefix, dv.content_hash)
    except DatasetUnavailableError as exc:
        raise StorageError(str(exc)) from exc


def fetch_checkpoint(store: ObjectStore, facts: RunFacts, dest: Path) -> Path:
    """``<checkpoint>/pretrained_model`` -> ``dest``, checked by the processor allow-list."""
    from train.checkpoints import CheckpointCorruptError, download_pretrained

    try:
        path = download_pretrained(store, facts.checkpoint.storage_prefix, dest)
    except CheckpointCorruptError as exc:
        raise JobFailedError("checkpoint_corrupt", str(exc)) from exc
    try:
        validate_pretrained_dir(path, require_processors=False)
    except UntrustedPretrainedError as exc:
        raise JobFailedError("config_invalid", f"checkpoint rejected: {exc}") from exc
    return path


def run_logs(store: ObjectStore, bucket: str, run_id: uuid.UUID, dest: Path) -> list[Path]:
    out: list[tuple[int, Path]] = []
    with contextlib.suppress(StorageError):
        for o in store.list_prefix(bucket, f"runs/{run_id}/logs/"):
            name = o.key.rsplit("/", 1)[-1]
            if not (name.startswith("attempt-") and name.endswith(".log")):
                continue
            p = dest / name
            store.download_file(bucket, o.key, p)
            mid = name[len("attempt-") : -len(".log")]
            out.append((int(mid) if mid.isdigit() else 0, p))
    return [p for _, p in sorted(out)]


def model_event(ctx: WorkerContext, run_id: uuid.UUID, model_id: uuid.UUID, outcome: ExportOutcome) -> None:
    outbox = Outbox()
    with contextlib.suppress(Exception):
        with ctx.engine.begin() as conn:
            append_run_event(
                conn,
                run_id,
                "model",
                {
                    "kind": "model",
                    "model_id": str(model_id),
                    "status": outcome.model_status,
                    "verified": outcome.verified,
                    "onnx_status": outcome.onnx_status,
                    "ts": iso(utcnow()),
                },
                outbox=outbox,
            )
        outbox.flush(ctx.bus)


def _finish(ctx: WorkerContext, job: ClaimedJob, status: str, **kw: Any) -> str:
    with ctx.engine.begin() as conn:
        finish_job(conn, job.id, ctx.worker_id, status=status, **kw)
    return status


def _infra(ctx: WorkerContext, job: ClaimedJob, exc: Exception, on_final: Any = None) -> str:
    msg = f"{type(exc).__name__}: {exc}"
    max_attempts = 2
    with contextlib.suppress(Exception), ctx.engine.connect() as conn:
        max_attempts = int(
            conn.execute(select(jobs.c.max_attempts).where(jobs.c.id == job.id)).scalar_one() or 2
        )
    if job.attempts < max_attempts:
        with ctx.engine.begin() as conn:
            requeue_job(conn, job.id, ctx.worker_id, error_code="storage_error", error_message=msg)
        return "queued"
    if on_final is not None:
        on_final(msg)
    return _finish(ctx, job, "failed", error_code="storage_error", error_message=msg[:2000])


def keeper_for(ctx: WorkerContext, job: ClaimedJob) -> JobKeeper:
    s = ctx.settings
    return JobKeeper(
        ctx.engine,
        job.id,
        ctx.worker_id,
        lease_s=s.lease_ttl_s,
        interval_s=s.heartbeat_interval_s,
        heartbeat_file=s.heartbeat_file,
    )


# --------------------------------------------------------------------------------------------
# export_model
# --------------------------------------------------------------------------------------------
def handle_job(ctx: WorkerContext, job: ClaimedJob) -> str:
    if job.model_id is None or job.run_id is None:
        return _finish(ctx, job, "failed", error_code="bad_request", error_message="job has no model/run")
    work = ctx.settings.scratch_dir / "jobs" / str(job.id)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        with keeper_for(ctx, job) as keeper:
            if job.payload.get("verify_only"):
                return _reverify(ctx, job, keeper, work)
            return _export(ctx, job, keeper, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _set_model(engine: Engine, model_id: uuid.UUID, **values: Any) -> None:
    with engine.begin() as conn:
        conn.execute(update(models).where(models.c.id == model_id).values(**values))


def _export(ctx: WorkerContext, job: ClaimedJob, keeper: JobKeeper, work: Path) -> str:
    from export.pipeline import run_export

    s = ctx.settings
    model_id = job.model_id
    assert model_id is not None and job.run_id is not None  # noqa: S101 - checked by handle_job
    with ctx.engine.connect() as conn:
        model = conn.execute(select(models).where(models.c.id == model_id)).one_or_none()
    if model is None or model.deleted_at is not None:
        return _finish(ctx, job, "failed", error_code="not_found", error_message="model deleted")

    def fail_model(msg: str) -> None:
        _set_model(ctx.engine, model_id, status="failed", onnx_detail=msg[:2000])

    try:
        facts = load_run_facts(ctx.engine, job)
        _set_model(ctx.engine, model_id, status="building")
        keeper.progress = 0.05
        pretrained = fetch_checkpoint(ctx.store, facts, work / "checkpoint" / "pretrained_model")
        root = ensure_dataset(ctx, facts)
        keeper.progress = 0.2
        if keeper.lost:
            return "lost"
        opts = {**DEFAULT_OPTIONS, **(job.payload.get("options") or {})}
        slug = str(facts.dataset.slug)
        model_name = str(opts.get("model_name") or f"{slug}_{facts.run.policy_type}")
        ectx = ExportContext(
            run_id=facts.run.id,
            workspace_id=facts.run.workspace_id,
            run_number=int(facts.run.number),
            model_id=model_id,
            checkpoint_id=facts.checkpoint.id,
            step=int(facts.checkpoint.step),
            policy_type=str(facts.run.policy_type),
            pretrained_model_dir=pretrained,
            dataset_root=root,
            dataset_repo_id=f"local/{slug}",
            heldout_episodes=list(facts.run.heldout_episodes or []),
            train_episodes=list(facts.run.train_episodes or []),
            options=opts,
            run_manifest=dict(facts.run.manifest or {}),
            work_dir=s.scratch_dir / "exports" / str(model_id),
            log_files=run_logs(ctx.store, s.bucket_artifacts, facts.run.id, work / "logs"),
            model_name=model_name,
            should_abort=lambda: keeper.lost or bool(ctx.shutdown.is_set()),
            load_check_python=s.export_load_check_python,
        )
        outcome = run_export(ectx, engine=ctx.engine, store=ctx.store, bus=ctx.bus, settings=s)
    except JobFailedError as exc:
        fail_model(exc.message)
        model_event(ctx, job.run_id, model_id, ExportOutcome(model_status="failed", onnx_status="failed"))
        return _finish(ctx, job, "failed", error_code=exc.code, error_message=exc.message[:2000])
    except ExportAbortedError:
        if keeper.lost:
            return "lost"
        _set_model(ctx.engine, model_id, status="pending")  # worker shutdown: another worker redoes it
        with ctx.engine.begin() as conn:
            requeue_job(conn, job.id, ctx.worker_id, error_code="worker_shutdown", error_message="shutdown")
        return "queued"
    except StorageError as exc:
        return _infra(ctx, job, exc, on_final=fail_model)
    except Exception as exc:
        log.exception("export job %s crashed", job.id)
        fail_model(f"{type(exc).__name__}: {exc}")
        model_event(ctx, job.run_id, model_id, ExportOutcome(model_status="failed", onnx_status="failed"))
        return _finish(
            ctx,
            job,
            "failed",
            error_code="internal_error",
            error_message=f"{type(exc).__name__}: {exc}"[:2000],
        )
    if keeper.lost:
        return "lost"
    model_event(ctx, job.run_id, model_id, outcome)
    ok = outcome.model_status == "ready"
    return _finish(
        ctx,
        job,
        "succeeded" if ok else "failed",
        result={
            "model_id": str(model_id),
            "model_status": outcome.model_status,
            "verified": outcome.verified,
            "onnx_status": outcome.onnx_status,
        },
        error_code=None if ok else "export_failed",
        error_message=None if ok else (outcome.error_message or "export failed")[:2000],
    )


# --------------------------------------------------------------------------------------------
# export_model verify_only (POST /models/{id}/verify)
# --------------------------------------------------------------------------------------------
def _reverify(ctx: WorkerContext, job: ClaimedJob, keeper: JobKeeper, work: Path) -> str:
    from export.verify import reverify_bundle

    model_id = job.model_id
    assert model_id is not None  # noqa: S101 - checked by handle_job
    with ctx.engine.connect() as conn:
        model = conn.execute(select(models).where(models.c.id == model_id)).one_or_none()
    if model is None or model.deleted_at is not None or not model.bundle_uri:
        return _finish(ctx, job, "failed", error_code="model_not_ready", error_message="model has no bundle")
    try:
        facts = load_run_facts(ctx.engine, job)
        bucket, key = parse_s3_uri(str(model.bundle_uri))
        zip_path = work / key.rsplit("/", 1)[-1]
        ctx.store.download_file(bucket, key, zip_path)
        root = ensure_dataset(ctx, facts)
        keeper.progress = 0.3
        manifest = dict(model.manifest or {})
        onnx_requested = (manifest.get("checks") or {}).get("onnx_status") != "skipped"
        verification, verified = reverify_bundle(
            zip_path,
            dataset_root=root,
            repo_id=f"local/{facts.dataset.slug}",
            heldout_episodes=list(facts.run.heldout_episodes or []),
            onnx_requested=onnx_requested,
            load_check_python=ctx.settings.export_load_check_python,
        )
    except JobFailedError as exc:
        return _finish(ctx, job, "failed", error_code=exc.code, error_message=exc.message[:2000])
    except StorageError as exc:
        return _infra(ctx, job, exc)
    if keeper.lost:
        return "lost"
    _set_model(ctx.engine, model_id, verified=verified, verification=verification.to_json())
    return _finish(
        ctx,
        job,
        "succeeded",
        result={"model_id": str(model_id), "verified": verified, "verification": verification.to_json()},
    )
