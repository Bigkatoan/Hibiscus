"""One attempt of one run on this GPU: preparing -> running -> (pausing) -> exporting -> terminal.

Implements run-lifecycle §2-§6, §8-§11 on the worker side. Owned by the GPU worker loop
(``train.worker``), which claimed the run (status ``preparing``, lease held).
"""

from __future__ import annotations

import codecs
import collections
import contextlib
import importlib
import logging
import math
import os
import platform
import selectors
import shutil
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, func, insert, select, text, update

from core import metrics
from core.bus import Bus
from core.child_env import child_env
from core.db import with_retry
from core.events import Outbox, append_run_event, iso, metrics_event, transition, upsert_metrics, utcnow
from core.export_api import ExportAbortedError, ExportContext, ExportOutcome
from core.liveness import touch
from core.pretrained_guard import UntrustedPretrainedError, validate_pretrained_dir
from core.s3 import ObjectStore, StorageError
from core.settings import WorkerSettings
from core.tables import checkpoints, dataset_versions, datasets, gpu_nodes, models, notifications, runs
from train import argv as argvmod
from train.checkpoints import CheckpointCorruptError, CheckpointManager, download_pretrained, is_complete
from train.classify import ExitFacts, classify, is_infra
from train.dataset_cache import DatasetCache, DatasetUnavailableError
from train.init_from import InitFromError, fetch_hf_init
from train.parser import (
    CheckpointStarted,
    EndOfTraining,
    LiveParser,
    LogCollapser,
    Metrics,
    Progress,
    Signature,
    TrainingStart,
)
from train.quota import GpuHours, gpu_hours
from train.telemetry import GpuInfo, Nvml, TelemetrySampler

log = logging.getLogger(__name__)

ACTIVE = ("preparing", "running", "pausing", "exporting", "cancelling")
ONNX_NONE = {"tdmpc", "smolvla", "pi0", "pi05"}
HUB_POLICIES = ("smolvla", "pi0", "pi05")
#: Statuses after which this worker no longer holds the run lease.
LEASE_RELEASED = ("queued", "paused", "succeeded", "failed", "cancelled")


@dataclass
class WorkerContext:
    settings: WorkerSettings
    engine: Engine
    store: ObjectStore
    bus: Bus | None
    nvml: Nvml
    gpu: GpuInfo
    gpu_id: str
    worker_id: str
    telemetry: TelemetrySampler | None
    shutdown: Any  # threading.Event
    wake: Any  # threading.Event
    datasets: DatasetCache


@dataclass
class RunRow:
    id: uuid.UUID
    workspace_id: uuid.UUID
    number: int
    created_by: uuid.UUID
    dataset_version_id: uuid.UUID
    policy_type: str
    config: dict[str, Any]
    resolved_args: list[str]
    total_steps: int
    current_step: int
    attempt: int
    infra_retries_used: int
    resume_checkpoint_step: int | None
    mixed_precision_requested: str
    mixed_precision_effective: str | None
    heldout_episodes: list[int]
    train_episodes: list[int]
    seed: int
    init_from_model_id: uuid.UUID | None
    init_from_checkpoint_id: uuid.UUID | None
    manifest: dict[str, Any] | None


class LeaseLostError(RuntimeError):
    pass


class AttemptError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class _State:
    status: str = "preparing"
    desired: str = "run"
    initial_step: int = 0
    tqdm_step: int = 0
    last_steps_per_s: float | None = None
    training_started: bool = False
    end_of_training: bool = False
    oom: bool = False
    cuda_fatal: bool = False
    kill_reason: str | None = None
    pause_at_step: int | None = None
    quota_pause: bool = False
    last_quota_check: float = field(default_factory=time.monotonic)
    nan_streak: int = 0
    nan_warned: bool = False
    vram_warned: bool = False
    silent_warned: bool = False
    last_mismatch_warn: float = 0.0
    last_output: float = field(default_factory=time.monotonic)
    last_hb: float = 0.0
    last_progress_pub: float = 0.0
    last_log_flush: float = field(default_factory=time.monotonic)
    last_log_upload: float = field(default_factory=time.monotonic)
    gpu_seconds_mark: float = field(default_factory=time.monotonic)


class LeaseKeeper:
    """Background lease heartbeat for the WHOLE attempt (QC-backend-01, QC-e2e-05).

    ``_supervise`` heartbeats from its loop while lerobot-train runs; every other phase (dataset
    download, init_from fetch, final checkpoint upload wait, export, eval, bundle upload) blocks
    the main thread for minutes. This thread renews the lease whenever the last heartbeat is
    older than ``heartbeat_interval_s``, records a cancel request (desired_state=cancel or status
    cancelling, QC-backend-05) and a lost lease, and the main thread acts on both between steps.
    """

    def __init__(self, attempt: RunAttempt) -> None:
        self.a = attempt
        self.stop = threading.Event()
        self.t = threading.Thread(target=self._loop, name=f"lease-{attempt.run.id}", daemon=True)

    def __enter__(self) -> LeaseKeeper:
        self.t.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop.set()
        self.t.join(timeout=self.a.s.db_retry_budget_s + 5)

    def _loop(self) -> None:
        tick = max(0.05, min(1.0, self.a.s.heartbeat_interval_s / 4))
        while not self.stop.wait(tick):
            a = self.a
            if a.lease_released or a.lease_lost:
                return
            if time.monotonic() - a.st.last_hb < a.s.heartbeat_interval_s:
                continue
            try:
                a.heartbeat()
            except LeaseLostError:
                if not a.lease_released:
                    log.error("run %s: lease lost (background heartbeat)", a.run.id)
                    a.lease_lost = True
                return
            except Exception as exc:  # transient DB trouble beyond the retry budget: try again
                log.warning("run %s: background heartbeat failed: %s", a.run.id, type(exc).__name__)


def load_run(engine: Engine, run_id: uuid.UUID) -> RunRow:
    with engine.connect() as conn:
        r = conn.execute(select(runs).where(runs.c.id == run_id)).one()
    return RunRow(
        id=r.id,
        workspace_id=r.workspace_id,
        number=int(r.number),
        created_by=r.created_by,
        dataset_version_id=r.dataset_version_id,
        policy_type=r.policy_type,
        config=dict(r.config or {}),
        resolved_args=list(r.resolved_args or []),
        total_steps=int(r.total_steps),
        current_step=int(r.current_step),
        attempt=int(r.attempt),
        infra_retries_used=int(r.infra_retries_used),
        resume_checkpoint_step=r.resume_checkpoint_step,
        mixed_precision_requested=str(r.mixed_precision_requested),
        mixed_precision_effective=r.mixed_precision_effective,
        heldout_episodes=list(r.heldout_episodes or []),
        train_episodes=list(r.train_episodes or []),
        seed=int(r.seed),
        init_from_model_id=r.init_from_model_id,
        init_from_checkpoint_id=r.init_from_checkpoint_id,
        manifest=r.manifest,
    )


def _pkg_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "unknown"


class RunAttempt:
    def __init__(self, ctx: WorkerContext, run_id: uuid.UUID) -> None:
        self.ctx = ctx
        self.s = ctx.settings
        self.run = load_run(ctx.engine, run_id)
        self.st = _State()
        self.run_dir = self.s.scratch_dir / "runs" / str(run_id)
        self.output_dir = self.run_dir / "output"
        self.log_path = self.run_dir / f"attempt-{self.run.attempt}.log"
        self.log_key = f"runs/{run_id}/logs/attempt-{self.run.attempt}.log"
        self.tail: collections.deque[str] = collections.deque(maxlen=200)
        self.pending_lines: list[str] = []
        self.pending_offset = 0
        self.log_base_offset = 0
        self.log_written = 0
        self.proc: subprocess.Popen[bytes] | None = None
        self.ckpts = CheckpointManager(
            engine=ctx.engine,
            store=ctx.store,
            bus=ctx.bus,
            bucket=self.s.bucket_artifacts,
            run_id=run_id,
            output_dir=self.output_dir,
            complete_timeout_s=self.s.checkpoint_complete_timeout_s,
        )
        self.dataset_root: Path | None = None
        self.dataset_repo_id = "local/dataset"
        self.mp_effective = self.run.mixed_precision_requested
        train_cfg = self.run.config.get("train", {})
        self.log_freq = int(train_cfg.get("log_freq", 200))
        self.save_freq = int(train_cfg.get("save_freq", 10000))
        self.logf: Any = None
        self._hb_lock = threading.Lock()
        #: Set by a heartbeat that found the lease taken (reaper / other worker).
        self.lease_lost = False
        #: Set once this attempt moved the run to a status that gives the lease up.
        self.lease_released = False

    # ------------------------------------------------------------------------------------------
    # small DB helpers
    # ------------------------------------------------------------------------------------------
    def _tx_transition(self, frm: list[str], to: str, **kw: Any) -> bool:
        outbox = Outbox()

        def _do() -> bool:
            with self.ctx.engine.begin() as conn:
                return transition(
                    conn,
                    self.run.id,
                    from_statuses=frm,
                    to=to,
                    outbox=outbox,
                    lease_owner=self.ctx.worker_id,
                    **kw,
                )

        ok = with_retry(_do, budget_s=self.s.db_retry_budget_s)
        outbox.flush(self.ctx.bus)
        if ok:
            self.st.status = to
            if to in LEASE_RELEASED:
                self.lease_released = True
        return ok

    def _event(self, event_type: str, data: dict[str, Any], level: str = "info") -> None:
        outbox = Outbox()

        def _do() -> None:
            with self.ctx.engine.begin() as conn:
                append_run_event(conn, self.run.id, event_type, data, outbox=outbox, level=level)

        with_retry(_do, budget_s=self.s.db_retry_budget_s)
        outbox.flush(self.ctx.bus)

    def warning(self, code: str, message: str, **params: Any) -> None:
        self._event(
            "warning",
            {"kind": "warning", "code": code, "message": message, "params": params, "ts": iso(utcnow())},
            level="warning",
        )

    def _notify(self, kind: str, params: dict[str, Any]) -> None:
        try:
            with self.ctx.engine.begin() as conn:
                conn.execute(
                    insert(notifications).values(
                        id=uuid.uuid4(),
                        user_id=self.run.created_by,
                        workspace_id=self.run.workspace_id,
                        kind=kind,
                        params={"run_id": str(self.run.id), "run_number": self.run.number, **params},
                        link=f"/runs/{self.run.id}",
                    )
                )
        except Exception as exc:
            log.warning("notification insert failed: %s", type(exc).__name__)

    def heartbeat(self) -> tuple[str, str]:
        with self._hb_lock:
            return self._heartbeat_locked()

    def _heartbeat_locked(self) -> tuple[str, str]:
        if self.lease_lost:
            raise LeaseLostError("lease lost")
        now = time.monotonic()
        dt = now - self.st.gpu_seconds_mark
        self.st.gpu_seconds_mark = now
        step = min(max(self.st.tqdm_step, self.run.current_step), self.run.total_steps)

        def _do() -> Any:
            with self.ctx.engine.begin() as conn:
                return conn.execute(
                    update(runs)
                    .where(runs.c.id == self.run.id, runs.c.lease_owner == self.ctx.worker_id)
                    .values(
                        lease_expires_at=func.now()
                        + func.make_interval(0, 0, 0, 0, 0, 0, self.s.lease_ttl_s),
                        heartbeat_at=func.now(),
                        current_step=func.greatest(runs.c.current_step, step),
                        gpu_seconds=runs.c.gpu_seconds + dt,
                        last_log_at=func.now()
                        - func.make_interval(0, 0, 0, 0, 0, 0, now - self.st.last_output),
                    )
                    .returning(runs.c.desired_state, runs.c.status)
                ).one_or_none()

        row = with_retry(_do, budget_s=self.s.db_retry_budget_s)
        self.st.last_hb = now
        if row is None:
            if not self.lease_released:
                self.lease_lost = True
            metrics.lease_heartbeat(False)
            raise LeaseLostError("lease lost")
        self.st.desired, self.st.status = str(row.desired_state), str(row.status)
        metrics.lease_heartbeat(True)
        metrics.run_step(step)
        touch(self.s.heartbeat_file)
        return self.st.desired, self.st.status

    def check_lease(self) -> None:
        """Raise :class:`LeaseLostError` when the background keeper saw the lease go."""
        if self.lease_lost:
            raise LeaseLostError("lease lost")

    @property
    def cancel_requested(self) -> bool:
        return self.st.desired == "cancel" or self.st.status == "cancelling"

    def _should_abort_export(self) -> bool:
        return self.lease_lost or self.cancel_requested or bool(self.ctx.shutdown.is_set())

    # ------------------------------------------------------------------------------------------
    # entry point
    # ------------------------------------------------------------------------------------------
    def execute(self) -> str:
        """Run the attempt to its end; returns the run status this attempt left."""
        tel = self.ctx.telemetry
        if tel is not None:
            tel.run_id = self.run.id
        keeper = LeaseKeeper(self)
        self.st.last_hb = time.monotonic()  # the claim just set the lease
        metrics.run_started(self.run.current_step, self.run.total_steps)
        try:
            try:
                keeper.__enter__()
                export_only = (
                    self.run.resume_checkpoint_step is not None
                    and self.run.resume_checkpoint_step >= self.run.total_steps
                )
                if not export_only:
                    hours = self._quota()
                    if hours is not None and hours.exhausted:
                        return self._quota_pause_before_start(hours)
                self._prepare()
                if self.cancel_requested:  # QC-backend-05: cancel while preparing => never spawn
                    return self._cancel_now()
                if export_only:
                    return self._export_only()
                self._spawn()
                self._supervise()
                return self._finish()
            except LeaseLostError:
                log.error("run %s: lease lost - killing process group", self.run.id)
                self._kill(hard=True)
                return "lease_lost"
            except AttemptError as exc:
                self._kill(hard=False)
                return self._fail(exc.code, exc.message)
            except Exception as exc:
                log.exception("run %s: worker bug", self.run.id)
                self._kill(hard=False)
                return self._fail("internal_error", f"{type(exc).__name__}: {exc}")
        finally:
            keeper.__exit__(None, None, None)
            metrics.run_ended()
            if tel is not None:
                tel.run_id = None
            self._close_log()
            self.ckpts.shutdown()
            with contextlib.suppress(Exception), self.ctx.engine.begin() as conn:
                conn.execute(
                    update(gpu_nodes)
                    .where(gpu_nodes.c.id == self.ctx.gpu_id, gpu_nodes.c.current_run_id == self.run.id)
                    .values(current_run_id=None)
                )
            # /scratch is shared between GPU workers: after a lost lease another worker may already
            # be using this run dir, so only the lease holder deletes it (boot_cleanup does the rest).
            if not self.lease_lost or self.lease_released:
                shutil.rmtree(self.run_dir, ignore_errors=True)

    def _cancel_now(self) -> str:
        self._tx_transition(list(ACTIVE), "cancelled", reason="user_cancel", release_gpu=True)
        return "cancelled"

    # ------------------------------------------------------------------------------------------
    # preparing
    # ------------------------------------------------------------------------------------------
    def _prepare(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._open_log()
        req = self.run.mixed_precision_requested
        eff = req
        if (req == "bf16" and not self.ctx.gpu.supports_bf16) or (
            req == "fp16" and not self.ctx.gpu.supports_fast_fp16
        ):
            eff = "no"
        prev_eff = self.run.mixed_precision_effective
        self.mp_effective = eff
        if eff != req or (prev_eff is not None and prev_eff != eff):
            self.warning(
                "mixed_precision_forced_no",
                f"{self.ctx.gpu.name} does not support {req}; training in fp32"
                if eff != req
                else f"mixed precision changed from {prev_eff} to {eff} on {self.ctx.gpu.name}",
                requested=req,
                effective=eff,
                gpu_id=self.ctx.gpu_id,
            )
        with self.ctx.engine.connect() as conn:
            dv = conn.execute(
                select(dataset_versions).where(dataset_versions.c.id == self.run.dataset_version_id)
            ).one()
            ds = conn.execute(select(datasets).where(datasets.c.id == dv.dataset_id)).one()
        self.dataset_repo_id = f"local/{ds.slug}"
        if not dv.storage_prefix:
            raise AttemptError("dataset_unavailable", "dataset version has no storage prefix")
        try:
            self.dataset_root = self.ctx.datasets.ensure(str(dv.id), dv.storage_prefix, dv.content_hash)
        except DatasetUnavailableError as exc:
            raise AttemptError("dataset_unavailable", str(exc)) from exc
        self.check_lease()
        self._write_manifest(ds, dv)
        self.heartbeat()

    def _write_manifest(self, ds: Any, dv: Any) -> None:
        m = dict(self.run.manifest or {})
        attempts = list(m.get("attempts", []))
        attempts.append(
            {
                "attempt": self.run.attempt,
                "started_at": iso(utcnow()),
                "finished_at": None,
                "gpu_id": self.ctx.gpu_id,
                "resumed_from_step": self.run.resume_checkpoint_step,
                "exit_code": None,
                "error_code": None,
            }
        )
        digest = self.s.image_digest or ("sha256:" + "0" * 64)
        try:
            import torch

            torch_v, cuda_v = str(torch.__version__), str(torch.version.cuda or "none")
        except Exception:
            torch_v, cuda_v = _pkg_version("torch"), "unknown"
        m.update(
            schema_version="1",
            run_id=str(self.run.id),
            attempts=attempts,
            lerobot_version=_pkg_version("lerobot"),
            torch_version=torch_v,
            cuda_version=cuda_v,
            python_version=platform.python_version(),
            image_digest=digest,
            hibiscus_version=self.s.worker_version,
            gpu={
                "id": self.ctx.gpu_id,
                "name": self.ctx.gpu.name,
                "compute_capability": self.ctx.gpu.compute_capability,
                **({"driver_version": self.ctx.gpu.driver_version} if self.ctx.gpu.driver_version else {}),
            },
            dataset={
                "dataset_id": str(ds.id),
                "version_id": str(dv.id),
                "version": int(dv.version),
                "content_hash": dv.content_hash or "",
                "repo_id": self.dataset_repo_id,
            },
            seed=self.run.seed,
            heldout_episodes=self.run.heldout_episodes,
            train_episodes=self.run.train_episodes,
            mixed_precision=self.mp_effective,
            lerobot_args=self.run.resolved_args,
            config={"policy": self.run.config.get("policy", {}), "train": self.run.config.get("train", {})},
        )
        self.run.manifest = m
        with self.ctx.engine.begin() as conn:
            conn.execute(
                update(runs)
                .where(runs.c.id == self.run.id, runs.c.lease_owner == self.ctx.worker_id)
                .values(
                    manifest=m,
                    mixed_precision_effective=self.mp_effective,
                    output_prefix=f"s3://{self.s.bucket_artifacts}/runs/{self.run.id}/",
                    log_uri=f"s3://{self.s.bucket_artifacts}/runs/{self.run.id}/logs/",
                )
            )

    def _finish_manifest_attempt(self, exit_code: int | None, error_code: str | None) -> None:
        m = dict(self.run.manifest or {})
        atts = list(m.get("attempts", []))
        if atts:
            atts[-1] = {
                **atts[-1],
                "finished_at": iso(utcnow()),
                "exit_code": exit_code,
                "error_code": error_code,
            }
            m["attempts"] = atts
        with contextlib.suppress(Exception), self.ctx.engine.begin() as conn:
            conn.execute(update(runs).where(runs.c.id == self.run.id).values(manifest=m))

    def _init_path(self) -> Path | str | None:
        init = self.run.config.get("_init_from") or {}
        if isinstance(init, dict) and init.get("hf_repo_id"):
            return self._fetch_hf_init(str(init["hf_repo_id"]))
        ck_id = self.run.init_from_checkpoint_id
        if self.run.init_from_model_id is not None:
            with self.ctx.engine.connect() as conn:
                ck_id = conn.execute(
                    select(models.c.checkpoint_id).where(models.c.id == self.run.init_from_model_id)
                ).scalar_one_or_none()
        if ck_id is None:
            return None
        with self.ctx.engine.connect() as conn:
            prefix = conn.execute(
                select(checkpoints.c.storage_prefix).where(checkpoints.c.id == ck_id)
            ).scalar_one()
        try:
            path = download_pretrained(self.ctx.store, prefix, self.run_dir / "init" / "pretrained_model")
        except (CheckpointCorruptError, StorageError) as exc:
            raise AttemptError("checkpoint_corrupt", f"init_from checkpoint unavailable: {exc}") from exc
        self._guard_pretrained(path, "init_from checkpoint")
        return path

    def _guard_pretrained(self, path: Path, what: str) -> None:
        """SEC-input-1: no processor JSON outside the allow-list reaches LeRobot."""
        try:
            validate_pretrained_dir(path, require_processors=False)
        except UntrustedPretrainedError as exc:
            raise AttemptError("config_invalid", f"{what} rejected: {exc}") from exc

    def _fetch_hf_init(self, repo_id: str) -> Path:
        if self.dataset_root is None:  # pragma: no cover - _prepare always sets it
            raise AttemptError("internal_error", "dataset not prepared")
        self._log_line(f"[hibiscus] init_from {repo_id}: fetching config.json + model.safetensors only")
        try:
            return fetch_hf_init(
                repo_id,
                self.run_dir / "init" / "pretrained_model",
                policy_type=self.run.policy_type,
                dataset_root=self.dataset_root,
                dataset_repo_id=self.dataset_repo_id,
                cache_dir=self.s.cache_dir / "hf" / "hub",
                env=self._env(self.run.policy_type in HUB_POLICIES),
                max_bytes=self.s.init_from_max_bytes,
            )
        except InitFromError as exc:
            raise AttemptError(exc.code, str(exc)) from exc

    def _build_argv(self) -> list[str]:
        if self.dataset_root is None:  # pragma: no cover - _prepare always sets it
            raise AttemptError("internal_error", "dataset not prepared")
        resume = self.run.resume_checkpoint_step
        if resume is not None:
            try:
                restored = self.ckpts.restore(resume)
            except (CheckpointCorruptError, StorageError) as exc:
                raise AttemptError("checkpoint_corrupt", str(exc)) from exc
            self._guard_pretrained(restored / "pretrained_model", f"checkpoint {resume}")
            self.st.initial_step = resume
            return argvmod.finalize_resume(
                bin_path=self.s.lerobot_train_bin,
                output_dir=self.output_dir,
                step=resume,
                total_steps=self.run.total_steps,
                mixed_precision=self.mp_effective,
            )
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        return argvmod.finalize_fresh(
            self.run.resolved_args,
            bin_path=self.s.lerobot_train_bin,
            dataset_root=self.dataset_root,
            output_dir=self.output_dir,
            init_path=self._init_path(),
            mixed_precision=self.mp_effective,
            max_num_workers=self.s.max_num_workers,
        )

    def _env(self, needs_hub: bool) -> dict[str, str]:
        """Allow-listed child env (SEC-input-2): no ``HIBISCUS_*`` value, token or key ever reaches it."""
        overrides = {
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "HF_HOME": str(self.s.cache_dir / "hf"),
            "HF_HUB_OFFLINE": "0" if needs_hub else "1",
            "TQDM_DISABLE": "0",
        }
        if self.s.child_cuda_visible_devices is not None:
            overrides["CUDA_VISIBLE_DEVICES"] = self.s.child_cuda_visible_devices
        return child_env(extra_prefixes=self.s.child_env_passthrough, overrides=overrides)

    def _spawn(self) -> None:
        argv = self._build_argv()
        self.check_lease()
        # init_from.hf_repo_id is fetched by the worker (SEC-input-1): the child only needs the hub
        # for the policies that download a base model / tokenizer.
        needs_hub = self.run.policy_type in HUB_POLICIES
        with self.ctx.engine.begin() as conn:
            conn.execute(
                update(runs)
                .where(runs.c.id == self.run.id, runs.c.lease_owner == self.ctx.worker_id)
                .values(resolved_args=argv)
            )
        self._log_line(
            f"[hibiscus] attempt {self.run.attempt} on {self.ctx.gpu_id} ({self.ctx.gpu.name}): "
            + " ".join(argv)
        )
        self.proc = subprocess.Popen(  # noqa: S603 - argv list built from validated config, no shell
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=self._env(needs_hub),
            cwd=str(self.run_dir),
            start_new_session=True,
        )
        self.st.last_output = time.monotonic()

    # ------------------------------------------------------------------------------------------
    # log plumbing
    # ------------------------------------------------------------------------------------------
    def _open_log(self) -> None:
        # Offsets of the SSE ``log`` events are relative to all attempts concatenated (GET /logs).
        base = 0
        try:
            for o in self.ctx.store.list_prefix(self.s.bucket_artifacts, f"runs/{self.run.id}/logs/"):
                if not o.key.endswith(f"attempt-{self.run.attempt}.log"):
                    base += o.size
        except Exception as exc:
            log.warning("could not size previous logs: %s", type(exc).__name__)
        self.log_base_offset = base
        self.logf = self.log_path.open("ab")
        self.log_written = self.log_path.stat().st_size

    def _log_line(self, line: str) -> None:
        data = (line + "\n").encode("utf-8", errors="replace")
        if not self.pending_lines:
            self.pending_offset = self.log_base_offset + self.log_written
        self.pending_lines.append(line)
        self.tail.append(line)
        if self.logf is not None:
            self.logf.write(data)
        self.log_written += len(data)

    def _flush_log_events(self, force: bool = False) -> None:
        now = time.monotonic()
        if not self.pending_lines or (
            not force and now - self.st.last_log_flush < self.s.log_batch_interval_s
        ):
            return
        lines, self.pending_lines = self.pending_lines, []
        offset = self.pending_offset
        if self.ctx.bus is not None:
            for i in range(0, len(lines), 500):
                chunk = lines[i : i + 500]
                self.ctx.bus.publish_run(
                    str(self.run.id), "log", {"kind": "log", "byte_offset": offset, "lines": chunk}
                )
                offset += sum(len((ln + "\n").encode("utf-8", errors="replace")) for ln in chunk)
        self.st.last_log_flush = now

    def _upload_log(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self.st.last_log_upload < self.s.log_upload_interval_s:
            return
        self.st.last_log_upload = now
        if self.logf is not None:
            self.logf.flush()
        try:
            self.ctx.store.upload_file(self.log_path, self.s.bucket_artifacts, self.log_key)
        except StorageError as exc:
            log.warning("log upload failed: %s", exc)
            if force:
                raise AttemptError("storage_error", f"log upload failed: {exc}") from exc

    def _close_log(self) -> None:
        if self.logf is not None:
            with contextlib.suppress(Exception):
                self.logf.close()
            self.logf = None

    # ------------------------------------------------------------------------------------------
    # supervising the process
    # ------------------------------------------------------------------------------------------
    def _supervise(self) -> None:
        if self.proc is None or self.proc.stdout is None:  # pragma: no cover
            raise AttemptError("internal_error", "process not started")
        parser = LiveParser(log_freq=self.log_freq, initial_step=self.st.initial_step)
        collapser = LogCollapser()
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        fd = self.proc.stdout.fileno()
        os.set_blocking(fd, False)
        sel = selectors.DefaultSelector()
        sel.register(fd, selectors.EVENT_READ)
        eof = False
        try:
            while not eof:
                for _key, _ in sel.select(timeout=0.5):
                    try:
                        data = os.read(fd, 65536)
                    except BlockingIOError:
                        continue
                    if not data:
                        eof = True
                        break
                    self.st.last_output = time.monotonic()
                    text = decoder.decode(data)
                    for line in collapser.feed(text):
                        self._log_line(line)
                    for ev in parser.feed(text):
                        self._handle(ev)
                self._periodic()
            text = decoder.decode(b"", final=True)
            for line in [*collapser.feed(text), *collapser.close()]:
                self._log_line(line)
            for ev in [*parser.feed(text), *parser.close()]:
                self._handle(ev)
        finally:
            sel.close()
        self.proc.wait()

    def _periodic(self) -> None:
        now = time.monotonic()
        if (
            self._escalate_at is not None
            and now > self._escalate_at
            and self.proc
            and self.proc.poll() is None
        ):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(self.proc.pid, signal.SIGKILL)
            self._escalate_at = None
        self._flush_log_events()
        self._upload_log()
        if self.ckpts.error is not None and self.st.kill_reason is None:
            err = self.ckpts.error
            code = "checkpoint_corrupt" if isinstance(err, CheckpointCorruptError) else "storage_error"
            self.st.kill_reason = f"error:{code}:{err}"
            self._kill(hard=False, wait=False)
        self.check_lease()
        if now - self.st.last_hb >= self.s.heartbeat_interval_s or self.ctx.wake.is_set():
            self.ctx.wake.clear()
            self.heartbeat()
        if self.st.last_hb != self._reacted_hb:  # also covers heartbeats of the LeaseKeeper thread
            self._reacted_hb = self.st.last_hb
            self._react(self.st.desired, self.st.status)
        if now - self.st.last_quota_check >= self.s.quota_check_interval_s:
            self.st.last_quota_check = now
            self._check_quota_mid_run()
        if self.ctx.shutdown.is_set() and self.st.kill_reason is None:
            self.st.kill_reason = "shutdown"
            self._kill(hard=False, wait=False)
        silent = now - self.st.last_output
        if silent >= self.s.log_silent_warn_s and not self.st.silent_warned and self.st.kill_reason is None:
            self.st.silent_warned = True
            self.warning("log_silent", f"no output for {int(silent)} s", silent_s=int(silent))
            self._notify("run.stalled", {"silent_s": int(silent)})
        if silent >= self.s.log_silent_kill_s and self.st.kill_reason is None:
            self.st.kill_reason = "stalled"
            self._kill(hard=False, wait=False)
        if silent < self.s.log_silent_warn_s:
            self.st.silent_warned = False
        # pause: once the target checkpoint is uploaded, stop the process
        if (
            self.st.pause_at_step is not None
            and self.st.kill_reason is None
            and self.ckpts.last_uploaded is not None
            and self.ckpts.last_uploaded.step >= self.st.pause_at_step
            and not self.ckpts.in_flight()
        ):
            self.st.kill_reason = "pause"
            self._kill(hard=False, wait=False)

    def _react(self, desired: str, status: str) -> None:
        if self.st.kill_reason is not None:
            if desired == "cancel" and self.st.kill_reason in ("pause", "pause_now"):
                self.st.kill_reason = "cancel"
            return
        if desired == "cancel" or status == "cancelling":
            self.st.kill_reason = "cancel"
            self._kill(hard=False, wait=False)
        elif desired == "pause_now":
            self.st.kill_reason = "pause_now"
            self._kill(hard=False, wait=False)
        elif desired == "pause" and self.st.pause_at_step is None:
            nxt = ((max(self.st.tqdm_step, self.st.initial_step) // self.save_freq) + 1) * self.save_freq
            self.st.pause_at_step = min(nxt, self.run.total_steps)
            log.info("run %s: pausing at checkpoint %d", self.run.id, self.st.pause_at_step)

    def _handle(self, ev: object) -> None:
        if isinstance(ev, Progress):
            self.st.tqdm_step = max(self.st.tqdm_step, ev.step)
            if ev.steps_per_s:
                self.st.last_steps_per_s = ev.steps_per_s
            self._mark_running()
            now = time.monotonic()
            if self.ctx.bus is not None and now - self.st.last_progress_pub >= self.s.progress_throttle_s:
                self.st.last_progress_pub = now
                rate = ev.steps_per_s
                remaining = self.run.total_steps - ev.step
                self.ctx.bus.publish_run(
                    str(self.run.id),
                    "progress",
                    {
                        "kind": "progress",
                        "step": ev.step,
                        "total_steps": self.run.total_steps,
                        "steps_per_s": rate,
                        "eta_s": (remaining / rate) if rate else None,
                        "ts": iso(utcnow()),
                    },
                )
        elif isinstance(ev, TrainingStart):
            self.st.training_started = True
            self._mark_running()
        elif isinstance(ev, Metrics):
            self._on_metrics(ev)
        elif isinstance(ev, CheckpointStarted):
            self.ckpts.submit(ev.step)
        elif isinstance(ev, EndOfTraining):
            self.st.end_of_training = True
        elif isinstance(ev, Signature):
            if ev.kind == "oom":
                self.st.oom = True
            elif ev.kind == "cuda_fatal":
                self.st.cuda_fatal = True

    def _mark_running(self) -> None:
        if self.st.status == "preparing":
            self.st.training_started = True
            self._tx_transition(["preparing"], "running", reason="training_started")

    def _on_metrics(self, ev: Metrics) -> None:
        ts = utcnow()
        values = ev.values
        loss = values.get("loss")
        latest = {k: (v if math.isfinite(v) else None) for k, v in values.items()}
        if self.st.last_steps_per_s:
            latest["_steps_per_s"] = self.st.last_steps_per_s
        outbox = Outbox()

        def _do() -> None:
            with self.ctx.engine.begin() as conn:
                upsert_metrics(conn, self.run.id, ev.step, values, ts)
                append_run_event(
                    conn, self.run.id, "metrics", metrics_event(ev.step, values, ts), outbox=outbox
                )
                conn.execute(
                    update(runs)
                    .where(runs.c.id == self.run.id)
                    .values(
                        latest_metrics=latest,
                        current_step=func.greatest(runs.c.current_step, min(ev.step, self.run.total_steps)),
                    )
                )

        with_retry(_do, budget_s=self.s.db_retry_budget_s)
        outbox.flush(self.ctx.bus)
        if not ev.consistent and time.monotonic() - self.st.last_mismatch_warn > 600:
            self.st.last_mismatch_warn = time.monotonic()
            self.warning(
                "parser_mismatch",
                "step label / progress bar disagree with the resolved step",
                label=ev.step_label,
                tqdm_step=ev.tqdm_step,
                resolved=ev.step,
            )
        if loss is not None and not math.isfinite(loss):
            self.st.nan_streak += 1
            if not self.st.nan_warned:
                self.st.nan_warned = True
                self.warning("nan_detected", f"non-finite loss at step {ev.step}", step=ev.step)
            if self.st.nan_streak >= 3 and self.st.kill_reason is None:
                self.st.kill_reason = "nan"
                self._kill(hard=False, wait=False)
        else:
            self.st.nan_streak = 0
        mem = values.get("gpu_mem_gb")
        if mem is not None and not self.st.vram_warned and mem * 1024 > 0.95 * self.ctx.gpu.total_vram_mb:
            self.st.vram_warned = True
            self.warning(
                "vram_near_limit", f"peak {mem:.2f} GB of {self.ctx.gpu.total_vram_mb} MiB", gpu_mem_gb=mem
            )

    def _kill(self, *, hard: bool, wait: bool = True) -> None:
        p = self.proc
        if p is None or p.poll() is not None:
            return
        try:
            pgid = os.getpgid(p.pid)
        except ProcessLookupError:
            return
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pgid, signal.SIGKILL if hard else signal.SIGTERM)
        if hard or not wait:
            if not hard:
                self._escalate_at = time.monotonic() + self.s.kill_grace_s
            return
        try:
            p.wait(timeout=self.s.kill_grace_s)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(pgid, signal.SIGKILL)
            p.wait()

    _escalate_at: float | None = None
    _reacted_hb: float = -1.0

    def _reap_children(self) -> None:
        """After the main process exited, make sure no dataloader worker survives."""
        p = self.proc
        if p is None:
            return
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(p.pid, signal.SIGKILL)

    # ------------------------------------------------------------------------------------------
    # end of attempt
    # ------------------------------------------------------------------------------------------
    def _wait_uploads(self) -> None:
        self.ckpts.wait_all(timeout=self.s.checkpoint_complete_timeout_s + 600)

    def _newest_local_complete(self) -> int | None:
        root = self.output_dir / "checkpoints"
        if not root.exists():
            return None
        steps = sorted((int(d.name) for d in root.iterdir() if d.name.isdigit()), reverse=True)
        for s in steps:
            if is_complete(self.output_dir, s):
                return s
        return None

    def _last_step(self) -> int | None:
        up = self.ckpts.last_uploaded
        return up.step if up else self.run.resume_checkpoint_step

    def _finish(self) -> str:
        p = self.proc
        if p is None:  # pragma: no cover
            raise AttemptError("internal_error", "process not started")
        rc = int(p.returncode if p.returncode is not None else p.wait())
        self._reap_children()
        self._flush_log_events(force=True)
        reason = self.st.kill_reason
        self._log_line(f"[hibiscus] lerobot-train exited with code {rc} (reason={reason or 'exit'})")
        self._flush_log_events(force=True)
        self._wait_uploads()
        self._upload_log(force=True)
        self._finish_manifest_attempt(rc, None)
        if reason == "cancel":
            self._tx_transition(list(ACTIVE), "cancelled", reason="user_cancel", release_gpu=True)
            return "cancelled"
        if reason in ("pause", "pause_now"):
            return self._to_paused(self._pause_reason())
        if reason == "shutdown":
            newest = self._newest_local_complete()
            up = self.ckpts.last_uploaded
            if newest is not None and (up is None or newest > up.step):
                try:
                    self.ckpts.submit(newest).result()
                except Exception as exc:
                    log.warning("shutdown upload failed: %s", exc)
            ok = self._tx_transition(
                list(ACTIVE),
                "queued",
                reason="worker_shutdown",
                extra={"resume_checkpoint_step": self._last_step(), "gpu_node_id": None},
                release_gpu=True,
            )
            return "queued" if ok else self.st.status
        if reason == "nan":
            return self._fail("nan_loss", "loss was NaN/Inf for 3 consecutive log records")
        if reason == "stalled":
            return self._fail("stalled", f"no output for {int(self.s.log_silent_kill_s)} s")
        if reason is not None and reason.startswith("error:"):
            _, code, msg = reason.split(":", 2)
            return self._fail(code, msg)
        if rc == 0 and self.st.end_of_training:
            if self.ckpts.error is not None:
                return self._fail("storage_error", str(self.ckpts.error))
            up = self.ckpts.last_uploaded
            if up is None or up.step < self.run.total_steps:
                if is_complete(self.output_dir, self.run.total_steps):
                    self.ckpts.submit(self.run.total_steps).result()
                else:
                    return self._fail("checkpoint_corrupt", "final checkpoint missing after End of training")
            # refresh status: a pause requested in the last moments => paused at the final step
            _, status = self.heartbeat()
            if status == "pausing":
                return self._to_paused(self._pause_reason())
            if status == "cancelling":
                self._tx_transition(["cancelling"], "cancelled", reason="user_cancel", release_gpu=True)
                return "cancelled"
            return self._export(from_status=status)
        facts = ExitFacts(rc, self.st.training_started, self.st.oom, self.st.cuda_fatal, "\n".join(self.tail))
        code, msg = classify(facts)
        return self._fail(code, msg)

    def _pause_reason(self) -> str:
        return "quota_exceeded" if self.st.quota_pause else "user_pause"

    def _to_paused(self, reason: str) -> str:
        extra: dict[str, Any] = {
            "resume_checkpoint_step": self._last_step(),
            "desired_state": "run",
            "gpu_node_id": None,
        }
        code = None
        if reason == "quota_exceeded":
            code = extra["error_code"] = "quota_exceeded"
        ok = self._tx_transition(
            ["pausing", "running", "preparing"],
            "paused",
            reason=reason,
            error_code=code,
            extra=extra,
            release_gpu=True,
        )
        return "paused" if ok else self.st.status

    # ------------------------------------------------------------------------------------------
    # monthly GPU-hour quota (run-lifecycle §6 ``quota_exceeded``: pause at next checkpoint)
    # ------------------------------------------------------------------------------------------
    def _quota(self) -> GpuHours | None:
        try:
            with self.ctx.engine.connect() as conn:
                return gpu_hours(conn, self.run.workspace_id, self.run.created_by)
        except Exception as exc:  # a quota lookup must never kill training
            log.warning("run %s: quota check failed: %s", self.run.id, type(exc).__name__)
            return None

    def _quota_notify(self, hours: GpuHours) -> None:
        name = None
        with contextlib.suppress(Exception), self.ctx.engine.connect() as conn:
            name = conn.execute(
                text("SELECT name FROM workspaces WHERE id = :w"), {"w": self.run.workspace_id}
            ).scalar_one_or_none()
        self._notify(
            "quota.warning",
            {
                "percent": max(100, hours.percent),
                "workspace_name": name,
                "reason": "quota_exceeded",
                "used_h": round(hours.used_h, 2),
                "limit_h": hours.limit_h,
            },
        )

    def _quota_pause_before_start(self, hours: GpuHours) -> str:
        """Quota already exhausted when the attempt starts: nothing trained, nothing lost."""
        log.info("run %s: GPU-hour quota exhausted before start - pausing", self.run.id)
        self.st.quota_pause = True
        if not self._tx_transition(
            ["preparing"], "pausing", reason="quota_exceeded", error_code="quota_exceeded"
        ):
            return self.st.status
        status = self._to_paused("quota_exceeded")
        if status == "paused":
            self._quota_notify(hours)
        return status

    def _check_quota_mid_run(self) -> None:
        if (
            self.st.kill_reason is not None
            or self.st.pause_at_step is not None
            or self.st.status not in ("running", "preparing")
        ):
            return
        hours = self._quota()
        if hours is None or not hours.exhausted:
            return
        if not self._tx_transition(
            ["running", "preparing"], "pausing", reason="quota_exceeded", error_code="quota_exceeded"
        ):
            return  # lost a race with the API (pause/cancel): its intent wins
        self.st.quota_pause = True
        nxt = ((max(self.st.tqdm_step, self.st.initial_step) // self.save_freq) + 1) * self.save_freq
        self.st.pause_at_step = min(nxt, self.run.total_steps)
        log.info(
            "run %s: GPU-hour quota exhausted (%.2f/%.2f h) - pausing at checkpoint %d",
            self.run.id,
            hours.used_h,
            hours.limit_h,
            self.st.pause_at_step,
        )
        self._quota_notify(hours)

    def _fail(self, code: str, message: str) -> str:
        with contextlib.suppress(Exception):
            self._wait_uploads()
        with contextlib.suppress(Exception):
            self._upload_log(force=True)
        retry = is_infra(code) and self.run.infra_retries_used == 0
        excerpt = "\n".join(list(self.tail)[-50:]) or None
        try:
            self._event(
                "error",
                {
                    "kind": "error",
                    "code": code,
                    "message": message[:2000],
                    "log_excerpt": excerpt,
                    "will_retry": retry,
                    "ts": iso(utcnow()),
                },
                level="error",
            )
        except Exception:
            log.exception("could not write error event")
        self._finish_manifest_attempt(self.proc.returncode if self.proc else None, code)
        last = self._last_step()
        if retry:
            self.warning(
                "retrying_after_infra_error",
                f"retrying after {code}",
                error_code=code,
                resume_checkpoint_step=last,
            )
            ok = self._tx_transition(
                list(ACTIVE),
                "queued",
                reason="infra_retry",
                error_code=code,
                extra={"infra_retries_used": 1, "resume_checkpoint_step": last, "gpu_node_id": None},
                release_gpu=True,
            )
            return "queued" if ok else self.st.status
        ok = self._tx_transition(
            list(ACTIVE),
            "failed",
            reason="error",
            error_code=code,
            extra={"error_code": code, "error_message": message[:4000], "resume_checkpoint_step": last},
            release_gpu=True,
        )
        if ok:
            self._notify("run.failed", {"error_code": code})
        return "failed" if ok else self.st.status

    # ------------------------------------------------------------------------------------------
    # export (run-lifecycle §5)
    # ------------------------------------------------------------------------------------------
    def _export_only(self) -> str:
        step = int(self.run.resume_checkpoint_step or self.run.total_steps)
        d = self.output_dir / "checkpoints" / f"{step:06d}"
        try:
            download_pretrained(
                self.ctx.store,
                f"s3://{self.s.bucket_artifacts}/{self.ckpts.prefix(step)}/",
                d / "pretrained_model",
            )
        except (CheckpointCorruptError, StorageError) as exc:
            return self._fail("checkpoint_corrupt", str(exc))
        return self._export(from_status=self.st.status, step=step)

    def _export(self, *, from_status: str, step: int | None = None) -> str:
        step = step or self.run.total_steps
        if from_status != "exporting" and not self._tx_transition(
            ["running", "preparing"],
            "exporting",
            reason="training_finished",
            extra={"current_step": min(step, self.run.total_steps)},
        ):
            return self.st.status
        with self.ctx.engine.connect() as conn:
            ck_id = conn.execute(
                select(checkpoints.c.id).where(
                    checkpoints.c.run_id == self.run.id, checkpoints.c.step == step
                )
            ).scalar_one_or_none()
            existing = None
            if ck_id is not None:
                existing = conn.execute(
                    select(models.c.id).where(models.c.checkpoint_id == ck_id, models.c.deleted_at.is_(None))
                ).scalar_one_or_none()
            slug = conn.execute(
                select(datasets.c.slug)
                .select_from(datasets.join(dataset_versions, dataset_versions.c.dataset_id == datasets.c.id))
                .where(dataset_versions.c.id == self.run.dataset_version_id)
            ).scalar_one()
        if ck_id is None:
            return self._fail("checkpoint_corrupt", f"no checkpoint row for final step {step}")
        opts = {"onnx": True, "onnx_fp16": False, "eval": True, **(self.run.config.get("_export") or {})}
        model_name = str(opts.get("model_name") or f"{slug}_{self.run.policy_type}")
        name = f"{model_name}-r{self.run.number}-step{step}"
        onnx = (
            "not_supported" if self.run.policy_type in ONNX_NONE or not opts.get("onnx", True) else "pending"
        )
        model_id = existing or uuid.uuid4()
        if existing is None:
            with self.ctx.engine.begin() as conn:
                conn.execute(
                    insert(models).values(
                        id=model_id,
                        workspace_id=self.run.workspace_id,
                        run_id=self.run.id,
                        checkpoint_id=ck_id,
                        name=name,
                        policy_type=self.run.policy_type,
                        step=step,
                        status="building",
                        onnx_status=onnx,
                        created_by=self.run.created_by,
                    )
                )
        self._model_event(model_id, "building", False, onnx)
        try:
            outcome = self._call_exporter(model_id, ck_id, step, opts, name)
        except ExportAbortedError:
            return self._export_aborted(model_id)
        self.check_lease()
        if outcome.infra_error:
            return self._fail("export_failed", outcome.error_message or "export infrastructure failure")
        with self.ctx.engine.begin() as conn:
            if outcome.model_status == "failed":
                conn.execute(update(models).where(models.c.id == model_id).values(status="failed"))
        self._model_event(model_id, outcome.model_status, outcome.verified, outcome.onnx_status)
        if outcome.model_status != "ready":
            # D3: export failure leaves the run succeeded; the ``model`` event carries status=failed.
            self._notify("model.failed", {"model_id": str(model_id), "detail": outcome.error_message})
        ok = self._tx_transition(["exporting"], "succeeded", reason="completed", release_gpu=True)
        if ok:
            self._notify("run.succeeded", {"model_id": str(model_id)})
            return "succeeded"
        # Lost the guard: a cancel arrived after the last export stage. The bundle is complete and
        # stays as it is; the run still ends cancelled (T11) instead of hanging in ``cancelling``.
        self.heartbeat()
        if self.cancel_requested:
            return self._cancel_now()
        return self.st.status

    def _export_aborted(self, model_id: uuid.UUID) -> str:
        """QC-backend-05: cancel (or lease loss / shutdown) during ``exporting``."""
        self.check_lease()
        if self.ctx.shutdown.is_set() and not self.cancel_requested:
            # graceful shutdown (§8): the next worker redoes the export (export-only attempt)
            ok = self._tx_transition(
                list(ACTIVE),
                "queued",
                reason="worker_shutdown",
                extra={"resume_checkpoint_step": self._last_step(), "gpu_node_id": None},
                release_gpu=True,
            )
            return "queued" if ok else self.st.status
        with contextlib.suppress(Exception), self.ctx.engine.begin() as conn:
            conn.execute(
                update(models)
                .where(models.c.id == model_id, models.c.status.in_(["pending", "building"]))
                .values(status="failed", onnx_detail="export stopped: run cancelled during export")
            )
        with contextlib.suppress(Exception):
            self._model_event(model_id, "failed", False, "failed")
        return self._cancel_now()

    def _model_event(self, model_id: uuid.UUID, status: str, verified: bool, onnx: str) -> None:
        self._event(
            "model",
            {
                "kind": "model",
                "model_id": str(model_id),
                "status": status,
                "verified": verified,
                "onnx_status": onnx,
                "ts": iso(utcnow()),
            },
        )

    def _attempt_logs(self) -> list[Path]:
        """Logs of every attempt for the bundle's ``logs/train.log``: earlier attempts come from
        object storage (an export-only retry has only its own log locally, QC-e2e-05)."""
        local = {p.name: p for p in self.run_dir.glob("attempt-*.log")}
        with contextlib.suppress(Exception):
            if self.logf is not None:
                self.logf.flush()
            for o in self.ctx.store.list_prefix(self.s.bucket_artifacts, f"runs/{self.run.id}/logs/"):
                fname = o.key.rsplit("/", 1)[-1]
                if fname.startswith("attempt-") and fname.endswith(".log") and fname not in local:
                    dest = self.run_dir / "prev-logs" / fname
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    self.ctx.store.download_file(self.s.bucket_artifacts, o.key, dest)
                    local[fname] = dest

        def _n(name: str) -> int:
            mid = name[len("attempt-") : -len(".log")]
            return int(mid) if mid.isdigit() else 0

        return [local[k] for k in sorted(local, key=_n)]

    def _call_exporter(
        self, model_id: uuid.UUID, ck_id: uuid.UUID, step: int, opts: dict[str, Any], name: str
    ) -> ExportOutcome:
        try:
            mod = importlib.import_module("export.pipeline")
            fn = getattr(mod, "run_export", None)
        except ImportError:
            fn = None
        if fn is None:
            with self.ctx.engine.begin() as conn:
                conn.execute(
                    update(models)
                    .where(models.c.id == model_id)
                    .values(
                        status="failed",
                        onnx_status="not_supported" if self.run.policy_type in ONNX_NONE else "failed",
                        onnx_detail="exporter not installed (worker/export.pipeline.run_export missing)",
                    )
                )
            return ExportOutcome(model_status="failed", error_message="exporter not installed")
        ctx = ExportContext(
            run_id=self.run.id,
            workspace_id=self.run.workspace_id,
            run_number=self.run.number,
            model_id=model_id,
            checkpoint_id=ck_id,
            step=step,
            policy_type=self.run.policy_type,
            pretrained_model_dir=self.output_dir / "checkpoints" / f"{step:06d}" / "pretrained_model",
            dataset_root=self.dataset_root or Path(),
            dataset_repo_id=self.dataset_repo_id,
            heldout_episodes=self.run.heldout_episodes,
            train_episodes=self.run.train_episodes,
            options=opts,
            run_manifest=dict(self.run.manifest or {}),
            work_dir=self.s.scratch_dir / "exports" / str(model_id),
            log_files=self._attempt_logs(),
            model_name=name,
            should_abort=self._should_abort_export,
            load_check_python=self.s.export_load_check_python,
        )
        try:
            self._guard_pretrained(ctx.pretrained_model_dir, f"checkpoint {step}")
        except AttemptError as exc:
            with self.ctx.engine.begin() as conn:
                conn.execute(
                    update(models)
                    .where(models.c.id == model_id)
                    .values(status="failed", onnx_detail=exc.message)
                )
            return ExportOutcome(model_status="failed", error_message=exc.message)
        try:
            result: ExportOutcome = fn(
                ctx, engine=self.ctx.engine, store=self.ctx.store, bus=self.ctx.bus, settings=self.s
            )
            return result
        except ExportAbortedError:
            raise
        except StorageError as exc:
            return ExportOutcome(model_status="failed", error_message=str(exc), infra_error=True)
        except Exception as exc:
            log.exception("exporter crashed")
            with self.ctx.engine.begin() as conn:
                conn.execute(
                    update(models)
                    .where(models.c.id == model_id)
                    .values(status="failed", onnx_detail=str(exc)[:2000])
                )
            return ExportOutcome(model_status="failed", error_message=f"{type(exc).__name__}: {exc}")
