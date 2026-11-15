"""GPU worker main loop: one process per GPU (ADR-2, run-lifecycle §7-§8).

    python -m train            # env HIBISCUS_GPU_INDEX=0, HIBISCUS_DATABASE_URL=..., ...

* registers ``gpu_nodes`` (NVML name / VRAM / compute capability),
* deletes stale ``/scratch/runs/*`` of runs no live worker holds,
* claims runs (SKIP LOCKED, fair-share) and GPU jobs (estimate / user export + eval, §7.3),
* SIGTERM => graceful: stop claiming, stop the child, upload newest checkpoint, re-queue (§8).
"""

from __future__ import annotations

import importlib
import logging
import os
import shutil
import signal
import socket
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

import redis
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core import metrics
from core.bus import QUEUE_CHANNEL, Bus, control_channel
from core.db import make_engine, with_retry
from core.events import ACTIVE_STATUSES, Outbox
from core.hardening import scrub_secret_env, set_non_dumpable
from core.jobs import ClaimedJob, claim_job, finish_job, oldest_queued_age_s
from core.liveness import touch
from core.s3 import ObjectStore
from core.settings import WorkerSettings, get_settings
from core.tables import gpu_nodes, runs
from train.dataset_cache import DatasetCache
from train.queue import claim_run
from train.runner import RunAttempt, WorkerContext
from train.telemetry import GpuInfo, Nvml, TelemetrySampler, torch_supports

log = logging.getLogger("hibiscus.worker")
PI_VRAM_MB = 20000


def unsupported_policies(total_vram_mb: int) -> list[str]:
    """Mirror of ``app.runs.catalog.gpu_support_level`` (run-lifecycle §7.4)."""
    return ["pi0", "pi05"] if total_vram_mb < PI_VRAM_MB else []


JobHandler = Callable[[WorkerContext, ClaimedJob], str]


def _job_handlers() -> dict[str, JobHandler]:
    from train.estimate import run_estimate

    handlers: dict[str, JobHandler] = {"estimate_resources": run_estimate}
    # QC-backend-02: user export / re-verify (export.jobs) and checkpoint eval (eval.jobs).
    for kind, mod in (("export_model", "export.jobs"), ("eval_checkpoint", "eval.jobs")):
        try:
            fn = getattr(importlib.import_module(mod), "handle_job", None)
        except ImportError:
            fn = None
        if callable(fn):
            handlers[kind] = fn
    return handlers


class GpuWorker:
    def __init__(self, settings: WorkerSettings | None = None) -> None:
        self.s = settings or get_settings()
        self.engine = make_engine(self.s.database_url)
        self.store = ObjectStore(
            endpoint_url=self.s.s3_endpoint_url,
            access_key=self.s.s3_access_key,
            secret_key=self.s.s3_secret_key,
            region=self.s.s3_region,
            max_retries=self.s.s3_max_retries,
        )
        self.bus = Bus(self.s.redis_url) if self.s.redis_url else None
        self.nvml = Nvml(self.s.nvml_device_index, disabled=self.s.disable_nvml)
        info = self.nvml.info()
        self.gpu: GpuInfo = info or GpuInfo(
            self.s.fake_gpu_name, None, self.s.fake_gpu_vram_mb, self.s.fake_gpu_cc, None
        )
        self.gpu_id = self.s.gpu_id
        host = self.s.host_name or socket.gethostname()
        self.host = host[:64]
        self.worker_id = f"{host}:{os.getpid()}:{uuid.uuid4().hex[:12]}"[:128]
        self.shutdown = threading.Event()
        self.wake = threading.Event()
        self.telemetry: TelemetrySampler | None = None
        self.handlers = _job_handlers()
        self.ctx = WorkerContext(
            settings=self.s,
            engine=self.engine,
            store=self.store,
            bus=self.bus,
            nvml=self.nvml,
            gpu=self.gpu,
            gpu_id=self.gpu_id,
            worker_id=self.worker_id,
            telemetry=None,
            shutdown=self.shutdown,
            wake=self.wake,
            datasets=DatasetCache(self.s.cache_dir, self.store, self.s.dataset_cache_max_bytes),
        )

    # -- lifecycle -----------------------------------------------------------------------------
    def register(self) -> None:
        g = self.gpu
        values: dict[str, Any] = {
            "id": self.gpu_id,
            "host": self.host,
            "device_index": self.s.gpu_index,
            "gpu_uuid": g.uuid,
            "name": g.name[:64],
            "total_vram_mb": g.total_vram_mb,
            "compute_capability": g.compute_capability,
            "supports_bf16": g.supports_bf16,
            "supports_fast_fp16": g.supports_fast_fp16,
            "status": "online",
            "worker_id": self.worker_id,
            "worker_version": self.s.worker_version,
            "image_digest": self.s.image_digest,
            "last_heartbeat_at": func.now(),
        }
        supported = torch_supports(g.compute_capability) if self.nvml.available else None
        if supported is False:
            log.error(
                "installed torch has no kernels for %s (cc %s): registering %s as disabled (CR-A4-7)",
                g.name,
                g.compute_capability,
                self.gpu_id,
            )
            values["status"] = "disabled"
        stmt = pg_insert(gpu_nodes).values(**values)
        upd: dict[str, Any] = {k: stmt.excluded[k] for k in values if k not in ("id", "status")}
        # an admin's draining/disabled survives worker restarts
        upd["status"] = (
            stmt.excluded.status
            if supported is False
            else func.coalesce(
                func.nullif(func.nullif(gpu_nodes.c.status, "offline"), "online"), stmt.excluded.status
            )
        )
        with self.engine.begin() as conn:
            conn.execute(stmt.on_conflict_do_update(index_elements=[gpu_nodes.c.id], set_=upd))
        log.info(
            "registered %s as %s (%s, %d MiB, cc %s)",
            self.worker_id,
            self.gpu_id,
            g.name,
            g.total_vram_mb,
            g.compute_capability,
        )

    def boot_cleanup(self) -> None:
        root = self.s.scratch_dir / "runs"
        if not root.exists():
            return
        with self.engine.connect() as conn:
            live = {
                str(r)
                for r in conn.execute(
                    select(runs.c.id).where(
                        runs.c.status.in_(ACTIVE_STATUSES), runs.c.lease_expires_at > func.now()
                    )
                ).scalars()
            }
        for d in root.iterdir():
            if d.is_dir() and d.name not in live:
                shutil.rmtree(d, ignore_errors=True)
                log.info("removed stale scratch %s", d)

    def _listen(self) -> None:
        if self.bus is None:
            return
        while not self.shutdown.is_set():
            try:
                ps = self.bus.client.pubsub(ignore_subscribe_messages=True)  # type: ignore[no-untyped-call]  # redis-py stub
                ps.subscribe(QUEUE_CHANNEL, control_channel(self.gpu_id))
                while not self.shutdown.is_set():
                    msg = ps.get_message(timeout=1.0)
                    if msg is not None:
                        self.wake.set()
                ps.close()
            except (redis.RedisError, OSError, ValueError):
                if self.shutdown.is_set():
                    return
                time.sleep(2.0)

    def gpu_status(self) -> str:
        with self.engine.connect() as conn:
            st = conn.execute(
                select(gpu_nodes.c.status).where(gpu_nodes.c.id == self.gpu_id)
            ).scalar_one_or_none()
        return str(st or "offline")

    def try_claim_run(self) -> uuid.UUID | None:
        outbox = Outbox()

        def _do() -> uuid.UUID | None:
            with self.engine.begin() as conn:
                return claim_run(
                    conn,
                    gpu_id=self.gpu_id,
                    gpu_total_vram_mb=self.gpu.total_vram_mb,
                    unsupported=unsupported_policies(self.gpu.total_vram_mb),
                    worker_id=self.worker_id,
                    lease_ttl_s=self.s.lease_ttl_s,
                    outbox=outbox,
                )

        rid = with_retry(_do, budget_s=self.s.db_retry_budget_s)
        outbox.flush(self.bus)
        return rid

    def try_claim_job(self, *, only_user_waited: bool) -> ClaimedJob | None:
        kinds = list(self.handlers)
        if not kinds:
            return None
        with self.engine.begin() as conn:
            if only_user_waited:
                user_kinds = [k for k in kinds if k in ("export_model", "eval_checkpoint")]
                age = oldest_queued_age_s(conn, "gpu", user_kinds) if user_kinds else None
                if age is None or age < self.s.gpu_job_max_wait_s:
                    return None
                kinds = user_kinds
            return claim_job(
                conn, resource="gpu", kinds=kinds, worker_id=self.worker_id, lease_s=self.s.lease_ttl_s
            )

    def run_job(self, job: ClaimedJob) -> None:
        handler = self.handlers.get(job.kind)
        metrics.job_claimed(job.kind)
        try:
            if handler is None:  # pragma: no cover - claimed only for known kinds
                raise RuntimeError(f"no handler for {job.kind}")
            metrics.job_ended(job.kind, str(handler(self.ctx, job)))
        except Exception as exc:
            metrics.job_ended(job.kind, "failed")
            log.exception("job %s failed", job.id)
            with self.engine.begin() as conn:
                finish_job(
                    conn,
                    job.id,
                    self.worker_id,
                    status="failed",
                    error_code="internal_error",
                    error_message=f"{type(exc).__name__}: {exc}"[:2000],
                )

    def step(self) -> bool:
        """One scheduling decision. Returns True when work was done."""
        if self.gpu_status() != "online":
            return False
        job = self.try_claim_job(only_user_waited=True)
        if job is not None:
            self.run_job(job)
            return True
        rid = self.try_claim_run()
        if rid is not None:
            log.info("claimed run %s", rid)
            metrics.job_claimed(metrics.TRAIN_RUN_KIND)
            result = RunAttempt(self.ctx, rid).execute()
            metrics.job_ended(metrics.TRAIN_RUN_KIND, result)
            log.info("run %s attempt ended: %s", rid, result)
            return True
        job = self.try_claim_job(only_user_waited=False)
        if job is not None:
            self.run_job(job)
            return True
        return False

    def serve(self) -> None:
        metrics.set_info("gpu", self.gpu_id, self.s.worker_version)
        if self.nvml.available:
            metrics.register_gpu(self.nvml, self.gpu_id)
        self.register()
        self.boot_cleanup()
        if self.nvml.available:
            self.telemetry = TelemetrySampler(
                engine=self.engine,
                bus=self.bus,
                nvml=self.nvml,
                gpu_id=self.gpu_id,
                interval_s=self.s.telemetry_interval_s,
            )
            self.ctx.telemetry = self.telemetry
            self.telemetry.start()
        listener = threading.Thread(target=self._listen, name="redis-listen", daemon=True)
        listener.start()
        try:
            while not self.shutdown.is_set():
                touch(self.s.heartbeat_file)  # QC-e2e-08: liveness for the image HEALTHCHECK
                try:
                    did = self.step()
                except Exception:
                    log.exception("scheduler step failed")
                    did = False
                if not did:
                    self.wake.wait(self.s.poll_interval_s)
                    self.wake.clear()
                    if self.telemetry is None:
                        with self.engine.begin() as conn:
                            conn.execute(
                                update(gpu_nodes)
                                .where(gpu_nodes.c.id == self.gpu_id)
                                .values(last_heartbeat_at=func.now())
                            )
        finally:
            if self.telemetry is not None:
                self.telemetry.stop()
            with self.engine.begin() as conn:
                conn.execute(
                    update(gpu_nodes)
                    .where(gpu_nodes.c.id == self.gpu_id, gpu_nodes.c.worker_id == self.worker_id)
                    .values(
                        status=func.coalesce(func.nullif(gpu_nodes.c.status, "online"), "offline"),
                        worker_id=None,
                    )
                )
            listener.join(timeout=5)
            if self.bus is not None:
                self.bus.close()
            self.engine.dispose()


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("HIBISCUS_LOG_LEVEL", "INFO"),
        format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    )
    set_non_dumpable()  # SEC-input-2: children cannot read /proc/<ppid>/environ or ptrace us
    w = GpuWorker()
    scrub_secret_env()  # settings are built; nothing re-reads the secrets from the environment
    metrics.start_metrics_server(w.s.metrics_port)

    def _graceful(signum: int, _frame: object) -> None:
        log.info("signal %d: graceful shutdown", signum)
        w.shutdown.set()
        w.wake.set()

    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)
    w.serve()
