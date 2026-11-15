"""GPU job handler for ``eval_checkpoint`` (QC-backend-02; ``POST /runs/{id}/checkpoints/{step}/eval``).

Payload ``{checkpoint_id, step}``: download the checkpoint's ``pretrained_model``, run the offline
evaluation on the run's held-out episodes (:func:`eval.offline.evaluate_heldout`, the code the
bundle builder uses), store the metrics in ``checkpoints.eval_metrics`` (read by
``GET .../eval-result``) and publish an ``eval`` event on the run stream.

Entry point (``train.worker._job_handlers``): :func:`handle_job`.
"""

from __future__ import annotations

import logging
import shutil
from typing import TYPE_CHECKING

from sqlalchemy import update

from core.events import iso, utcnow
from core.jobs import ClaimedJob
from core.s3 import StorageError
from core.tables import checkpoints
from export.jobs import (
    JobFailedError,
    _finish,
    _infra,
    ensure_dataset,
    fetch_checkpoint,
    keeper_for,
    load_run_facts,
)

if TYPE_CHECKING:  # pragma: no cover
    from train.runner import WorkerContext

log = logging.getLogger("hibiscus.eval.jobs")


def handle_job(ctx: WorkerContext, job: ClaimedJob) -> str:
    from eval.offline import evaluate_heldout

    if job.run_id is None:
        return _finish(ctx, job, "failed", error_code="bad_request", error_message="job has no run")
    work = ctx.settings.scratch_dir / "jobs" / str(job.id)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        with keeper_for(ctx, job) as keeper:
            try:
                facts = load_run_facts(ctx.engine, job)
                heldout = list(facts.run.heldout_episodes or [])
                if not heldout:
                    raise JobFailedError("bad_request", "run has no held-out episodes")
                pretrained = fetch_checkpoint(ctx.store, facts, work / "pretrained_model")
                root = ensure_dataset(ctx, facts)
                keeper.progress = 0.2
                if keeper.lost:
                    return "lost"
                metrics = evaluate_heldout(
                    pretrained_dir=pretrained,
                    dataset_root=root,
                    repo_id=f"local/{facts.dataset.slug}",
                    heldout_episodes=heldout,
                    run_id=str(facts.run.id),
                    step=int(facts.checkpoint.step),
                    out_dir=None,
                    device="cpu",
                )
            except JobFailedError as exc:
                return _finish(ctx, job, "failed", error_code=exc.code, error_message=exc.message[:2000])
            except StorageError as exc:
                return _infra(ctx, job, exc)
            if keeper.lost:
                return "lost"
            with ctx.engine.begin() as conn:
                conn.execute(
                    update(checkpoints)
                    .where(checkpoints.c.id == facts.checkpoint.id)
                    .values(eval_metrics=metrics)
                )
            overall = metrics.get("overall") or {}
            summary = {
                "action_mae": float(overall.get("mae", 0.0)),
                "action_mse": float(overall.get("mse", 0.0)),
            }
            if ctx.bus is not None:
                ctx.bus.publish_run(
                    str(facts.run.id),
                    "eval",
                    {  # OpenAPI EvalEvent (+ checkpoint_id)
                        "kind": "eval",
                        "step": int(facts.checkpoint.step),
                        "checkpoint_id": str(facts.checkpoint.id),
                        **summary,
                        "ts": iso(utcnow()),
                    },
                )
            return _finish(
                ctx,
                job,
                "succeeded",
                result={
                    "checkpoint_id": str(facts.checkpoint.id),
                    "step": int(facts.checkpoint.step),
                    **summary,
                },
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)
