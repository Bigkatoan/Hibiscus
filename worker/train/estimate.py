"""``estimate_resources`` GPU job: 20-step dry run of ``lerobot-train`` (PLAN §3.3).

Measures peak VRAM (max of torch ``mem_gb`` and NVML used-minus-idle) and seconds/step (``step_s``
meter of the last metrics record), then upserts ``resource_estimates`` (cache key computed by the
API) and publishes ``estimate.ready`` on the workspace stream.
"""

from __future__ import annotations

import codecs
import logging
import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.child_env import child_env
from core.events import iso, utcnow
from core.jobs import ClaimedJob, JobKeeper, finish_job, heartbeat_job
from core.liveness import touch
from core.tables import dataset_versions, resource_estimates
from train import argv as argvmod
from train.dataset_cache import DatasetUnavailableError
from train.parser import LiveParser, Metrics, Signature
from train.runner import WorkerContext

log = logging.getLogger(__name__)
DRY_RUN_STEPS = 20


def run_estimate(ctx: WorkerContext, job: ClaimedJob) -> str:
    s = ctx.settings
    p: dict[str, Any] = job.payload
    work = s.scratch_dir / "estimates" / str(job.id)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        with ctx.engine.connect() as conn:
            dv = conn.execute(
                select(dataset_versions).where(dataset_versions.c.id == uuid.UUID(p["dataset_version_id"]))
            ).one()
        keeper = JobKeeper(
            ctx.engine,
            job.id,
            ctx.worker_id,
            lease_s=s.lease_ttl_s,
            interval_s=s.heartbeat_interval_s,
            heartbeat_file=s.heartbeat_file,
        )
        with keeper:  # QC-backend-01: the dataset download can outlast the job lease
            root = ctx.datasets.ensure(str(dv.id), dv.storage_prefix, dv.content_hash)
        if keeper.lost:
            return "lost"
        mp = str(p.get("mixed_precision", "no"))
        if (mp == "bf16" and not ctx.gpu.supports_bf16) or (mp == "fp16" and not ctx.gpu.supports_fast_fp16):
            mp = "no"
        argv = argvmod.finalize_fresh(
            list(p["argv"]),
            bin_path=s.lerobot_train_bin,
            dataset_root=root,
            output_dir=work / "output",
            init_path=None,
            mixed_precision=mp,
            max_num_workers=s.max_num_workers,
        )
        argv = argvmod.override(
            argv, steps=str(DRY_RUN_STEPS), log_freq="10", save_checkpoint="false", num_workers="2"
        )
        idle = ctx.nvml.mem_used_mb() or 0
        peak_nvml = idle
        # SEC-input-2: allow-listed env, never a copy of the worker's (secret-bearing) environment.
        overrides = {
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "HF_HOME": str(s.cache_dir / "hf"),
            "HF_HUB_OFFLINE": "0" if p.get("policy_type") in ("smolvla", "pi0", "pi05") else "1",
        }
        if s.child_cuda_visible_devices is not None:
            overrides["CUDA_VISIBLE_DEVICES"] = s.child_cuda_visible_devices
        env = child_env(extra_prefixes=s.child_env_passthrough, overrides=overrides)
        proc = subprocess.Popen(  # noqa: S603 - argv list from validated config
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            cwd=str(work),
            start_new_session=True,
        )
        out: list[str] = []
        if proc.stdout is None:  # pragma: no cover - stdout=PIPE
            raise RuntimeError("no stdout pipe")
        fd = proc.stdout.fileno()

        def reader() -> None:
            dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                out.append(dec.decode(chunk))

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        deadline = time.monotonic() + 1800
        last_hb = 0.0
        while proc.poll() is None:
            peak_nvml = max(peak_nvml, ctx.nvml.mem_used_mb() or 0)
            if time.monotonic() - last_hb > s.heartbeat_interval_s:
                last_hb = time.monotonic()
                with ctx.engine.begin() as conn:
                    if not heartbeat_job(conn, job.id, ctx.worker_id, lease_s=s.lease_ttl_s):
                        os.killpg(proc.pid, signal.SIGKILL)
                        return "lost"
                touch(s.heartbeat_file)
            if time.monotonic() > deadline or ctx.shutdown.is_set():
                os.killpg(proc.pid, signal.SIGKILL)
                break
            time.sleep(0.5)
        t.join(timeout=10)
        parser = LiveParser(log_freq=10)
        events = parser.feed("".join(out)) + parser.close()
        metrics = [e for e in events if isinstance(e, Metrics)]
        oom = any(isinstance(e, Signature) and e.kind == "oom" for e in events)
        if proc.returncode != 0 or not metrics:
            code = "oom" if oom else "estimate_failed"
            tail = "".join(out)[-2000:]
            with ctx.engine.begin() as conn:
                finish_job(
                    conn,
                    job.id,
                    ctx.worker_id,
                    status="failed",
                    error_code=code,
                    error_message=tail,
                    result={"oom": oom, "gpu_id": ctx.gpu_id},
                )
            _publish(ctx, job, "failed", code)
            return "failed"
        torch_peak = max(int(m.values.get("gpu_mem_gb", 0.0) * 1024) for m in metrics)
        peak = max(torch_peak, peak_nvml - idle)
        sec = float(metrics[-1].values.get("step_s", metrics[-1].values.get("update_s", 0.0)))
        with ctx.engine.begin() as conn:
            stmt = pg_insert(resource_estimates).values(
                id=uuid.uuid4(),
                cache_key=p["cache_key"],
                policy_type=p["policy_type"],
                gpu_name=ctx.gpu.name,
                batch_size=int(p["batch_size"]),
                mixed_precision=mp,
                image_shapes=p.get("image_shapes", []),
                policy_config_hash=p["policy_config_hash"],
                peak_vram_mb=peak,
                sec_per_step=sec,
                lerobot_version=str(p.get("lerobot_version", "0.7.1")),
            )
            conn.execute(
                stmt.on_conflict_do_update(
                    index_elements=[resource_estimates.c.cache_key],
                    set_={"peak_vram_mb": peak, "sec_per_step": sec, "updated_at": func.now()},
                )
            )
            finish_job(
                conn,
                job.id,
                ctx.worker_id,
                status="succeeded",
                result={
                    "peak_vram_mb": peak,
                    "torch_peak_mb": torch_peak,
                    "nvml_peak_mb": peak_nvml - idle,
                    "sec_per_step": sec,
                    "gpu_id": ctx.gpu_id,
                    "gpu_name": ctx.gpu.name,
                    "measured_at": iso(utcnow()),
                },
            )
        _publish(ctx, job, "succeeded", None)
        return "succeeded"
    except DatasetUnavailableError as exc:
        with ctx.engine.begin() as conn:
            finish_job(
                conn,
                job.id,
                ctx.worker_id,
                status="failed",
                error_code="dataset_unavailable",
                error_message=str(exc),
            )
        return "failed"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _publish(ctx: WorkerContext, job: ClaimedJob, status: str, code: str | None) -> None:
    if ctx.bus is None:
        return
    ctx.bus.publish_workspace(
        str(job.workspace_id),
        "estimate.ready",
        {
            "resource": "estimate",
            "id": str(job.id),
            "status": status,
            "error_code": code,
            "ts": iso(utcnow()),
        },
    )
