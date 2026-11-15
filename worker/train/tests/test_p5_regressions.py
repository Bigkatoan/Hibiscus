"""Regression tests for the phase-4 QC findings on the GPU worker (real PG/Redis/MinIO + fake trainer).

* QC-backend-01 / QC-e2e-05: the run lease stays alive through a long export (and a lease expiry
  can no longer happen while the worker is still exporting);
* QC-backend-05: cancel during ``exporting`` (and during ``preparing``) ends the run ``cancelled``;
* QC-backend-04: the concurrent-run limit holds when two workers claim at the same moment;
* QC-backend-02: ``export_model`` / ``eval_checkpoint`` jobs are claimed and processed;
* SEC-input-1: ``init_from.hf_repo_id`` never reaches lerobot-train as a Hub id;
* SEC-input-2: the child env is an allow-list;
* QC-e2e-08 / QC-e2e-09: heartbeat file, compose env names.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from core.events import Outbox
from core.export_api import ExportContext, ExportOutcome
from core.settings import WorkerSettings
from core.tables import checkpoints, jobs, models
from core.testing import Seed, Services, contract_metadata
from train.queue import claim_run
from train.telemetry import resolve_nvml_index
from train.tests.harness import (
    WorkerThread,
    api_transition,
    events,
    queue_run,
    run_row,
    settings_for,
    upload_dataset,
    wait_for,
)
from train.worker import GpuWorker, _job_handlers


@pytest.fixture
def ws(engine: Engine, services: Services, tmp_path: Path) -> Seed:
    return upload_dataset(services, engine, None, tmp_path)


def _statuses(engine: Engine, rid: uuid.UUID) -> list[str]:
    return [e.data["to"] for e in events(engine, rid, "status")]


def _lease_expired(engine: Engine, rid: uuid.UUID) -> bool:
    with engine.connect() as conn:
        return bool(
            conn.execute(
                text("SELECT lease_expires_at < now() FROM runs WHERE id = :r"), {"r": rid}
            ).scalar_one()
        )


# ---------------------------------------------------------------------------------------------
# QC-backend-01 / QC-e2e-05
# ---------------------------------------------------------------------------------------------
def test_lease_kept_alive_during_long_export(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Export (6 s) far longer than the lease (2 s): the background keeper renews it, so the
    reaper's condition ``lease_expires_at < now()`` is never true and the run succeeds."""
    import export.pipeline

    seen: list[bool] = []

    def slow_export(ctx: ExportContext, **_: Any) -> ExportOutcome:
        assert ctx.log_files, "attempt logs are handed to the exporter"
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            seen.append(_lease_expired(engine, ctx.run_id))
            ctx.check_abort()
            time.sleep(0.2)
        with engine.begin() as conn:
            conn.execute(text("UPDATE models SET status='ready' WHERE id=:m"), {"m": ctx.model_id})
        return ExportOutcome(model_status="ready", verified=True, onnx_status="passed")

    monkeypatch.setattr(export.pipeline, "run_export", slow_export)
    rid = queue_run(engine, ws, steps=40)
    w = GpuWorker(settings_for(services, tmp_path, lease_ttl_s=2, heartbeat_interval_s=0.5))
    WorkerThread(w).start().join(timeout=120)
    r = run_row(engine, rid)
    assert r.status == "succeeded", (r.status, r.error_code, r.error_message)
    assert len(seen) > 20 and not any(seen), "lease expired while the worker was still exporting"
    assert _statuses(engine, rid) == ["preparing", "running", "exporting", "succeeded"]
    assert r.gpu_seconds >= 5.0  # export time is GPU time too (the keeper's heartbeats count it)


def test_lease_kept_alive_during_slow_dataset_download(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    from train.dataset_cache import DatasetCache

    real = DatasetCache.ensure
    seen: list[bool] = []
    rid_box: list[uuid.UUID] = []

    def slow_ensure(self: DatasetCache, *a: Any, **k: Any) -> Path:
        for _ in range(20):
            seen.append(_lease_expired(engine, rid_box[0]))
            time.sleep(0.2)
        return real(self, *a, **k)

    monkeypatch.setattr(DatasetCache, "ensure", slow_ensure)
    rid = queue_run(engine, ws, steps=20)
    rid_box.append(rid)
    w = GpuWorker(settings_for(services, tmp_path, lease_ttl_s=2, heartbeat_interval_s=0.5))
    WorkerThread(w).start().join(timeout=120)
    assert not any(seen) and run_row(engine, rid).status == "succeeded"


# ---------------------------------------------------------------------------------------------
# QC-backend-05
# ---------------------------------------------------------------------------------------------
def test_cancel_during_export_ends_cancelled(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    import export.pipeline

    started = threading.Event()

    def export_until_cancelled(ctx: ExportContext, **_: Any) -> ExportOutcome:
        started.set()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            ctx.check_abort()  # raises ExportAbortedError once the cancel is seen
            time.sleep(0.05)
        raise AssertionError("cancel never reached the exporter")

    monkeypatch.setattr(export.pipeline, "run_export", export_until_cancelled)
    rid = queue_run(engine, ws, steps=40)
    w = GpuWorker(settings_for(services, tmp_path, heartbeat_interval_s=0.3))
    t = WorkerThread(w).start()
    assert started.wait(60)
    api_transition(engine, rid, ["exporting"], "cancelling", desired_state="cancel")
    t0 = time.monotonic()
    t.join(timeout=60)
    assert time.monotonic() - t0 < 10
    r = run_row(engine, rid)
    assert r.status == "cancelled" and r.lease_owner is None and r.lease_expires_at is None
    assert _statuses(engine, rid)[-2:] == ["cancelling", "cancelled"]
    with engine.connect() as conn:
        m = conn.execute(select(models).where(models.c.run_id == rid)).one()
    assert m.status == "failed" and "cancelled" in (m.onnx_detail or "")


def test_cancel_while_preparing_never_spawns(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    from train.dataset_cache import DatasetCache

    real = DatasetCache.ensure
    rid_box: list[uuid.UUID] = []

    def cancel_then_ensure(self: DatasetCache, *a: Any, **k: Any) -> Path:
        api_transition(engine, rid_box[0], ["preparing"], "cancelling", desired_state="cancel")
        return real(self, *a, **k)

    monkeypatch.setattr(DatasetCache, "ensure", cancel_then_ensure)
    rid = queue_run(engine, ws, steps=40)
    rid_box.append(rid)
    WorkerThread(GpuWorker(settings_for(services, tmp_path))).start().join(timeout=60)
    r = run_row(engine, rid)
    assert r.status == "cancelled" and r.lease_owner is None
    assert _statuses(engine, rid) == ["preparing", "cancelling", "cancelled"]
    assert r.resolved_args[0] == "lerobot-train"  # never rewritten by a spawn


# ---------------------------------------------------------------------------------------------
# QC-backend-04
# ---------------------------------------------------------------------------------------------
def test_concurrent_claims_respect_max_concurrent_runs(engine: Engine, ws: Seed) -> None:
    """Two workers claim at the same moment for a user whose limit is 1: one gets a run, the
    other waits on the claim lock and then sees the first claim (before: both started a run)."""
    from train.tests.test_queue_and_units import _gpu

    _gpu(engine, "cuda0", 12288)
    _gpu(engine, "cuda1", 24576)
    r1 = queue_run(engine, ws, steps=20)
    r2 = queue_run(engine, ws, steps=20)
    results: dict[str, uuid.UUID | None] = {}
    c1 = engine.connect()
    tx1 = c1.begin()
    results["cuda0"] = claim_run(
        c1,
        gpu_id="cuda0",
        gpu_total_vram_mb=12288,
        unsupported=[],
        worker_id="w0",
        lease_ttl_s=60,
        outbox=Outbox(),
    )

    def second() -> None:
        with engine.begin() as c2:
            results["cuda1"] = claim_run(
                c2,
                gpu_id="cuda1",
                gpu_total_vram_mb=24576,
                unsupported=[],
                worker_id="w1",
                lease_ttl_s=60,
                outbox=Outbox(),
            )

    t = threading.Thread(target=second)
    t.start()
    time.sleep(1.0)
    assert t.is_alive(), "second claim must wait for the first claim's transaction"
    tx1.commit()
    c1.close()
    t.join(timeout=10)
    assert results["cuda0"] in (r1, r2) and results["cuda1"] is None
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM runs WHERE status = 'preparing'")).scalar_one()
    assert n == 1


# ---------------------------------------------------------------------------------------------
# QC-backend-02
# ---------------------------------------------------------------------------------------------
def _job(engine: Engine, seed: Seed, kind: str, payload: dict[str, Any], **kw: Any) -> uuid.UUID:
    m = contract_metadata()
    jid = uuid.uuid4()
    with Session(engine) as s:
        s.add(
            m.Job(
                id=jid,
                workspace_id=seed.workspace_id,
                kind=m.JobKind(kind),
                resource=m.JobResource.GPU,
                payload=payload,
                created_by=seed.user_id,
                **kw,
            )
        )
        s.commit()
    return jid


def test_gpu_worker_has_export_and_eval_handlers() -> None:
    assert {"estimate_resources", "export_model", "eval_checkpoint"} <= set(_job_handlers())


def test_export_model_and_eval_checkpoint_jobs(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    import eval.offline
    import export.pipeline

    monkeypatch.setenv("FAKE_MODE", "normal")
    rid = queue_run(engine, ws, steps=40)
    w = GpuWorker(settings_for(services, tmp_path))
    WorkerThread(w).start().join()
    assert run_row(engine, rid).status == "succeeded"
    with engine.connect() as conn:
        ck = conn.execute(
            select(checkpoints).where(checkpoints.c.run_id == rid, checkpoints.c.step == 20)
        ).one()
    mid = uuid.uuid4()
    m = contract_metadata()
    with Session(engine) as s:
        s.add(
            m.Model(
                id=mid,
                workspace_id=ws.workspace_id,
                run_id=rid,
                checkpoint_id=ck.id,
                name="golden_act-r1-step20",
                policy_type="act",
                step=20,
                status=m.ModelStatus.PENDING,
                onnx_status=m.OnnxStatus.PENDING,
                created_by=ws.user_id,
            )
        )
        s.commit()
    seen: dict[str, Any] = {}

    def fake_export(ctx: ExportContext, **_: Any) -> ExportOutcome:
        seen.update(
            step=ctx.step,
            pm=(ctx.pretrained_model_dir / "config.json").is_file(),
            logs=[p.name for p in ctx.log_files],
            opts=ctx.options,
        )
        with engine.connect() as conn:
            seen["status_during"] = conn.execute(
                select(models.c.status).where(models.c.id == ctx.model_id)
            ).scalar_one()
        with engine.begin() as conn:
            conn.execute(text("UPDATE models SET status='ready' WHERE id=:m"), {"m": ctx.model_id})
        return ExportOutcome(model_status="ready", verified=True, onnx_status="passed")

    monkeypatch.setattr(export.pipeline, "run_export", fake_export)
    jid = _job(
        engine,
        ws,
        "export_model",
        {"checkpoint_id": str(ck.id), "step": 20, "options": {"onnx": False}, "user_requested": True},
        run_id=rid,
        model_id=mid,
    )
    assert w.step() is True
    with engine.connect() as conn:
        j = conn.execute(select(jobs).where(jobs.c.id == jid)).one()
        model = conn.execute(select(models).where(models.c.id == mid)).one()
    assert j.status == "succeeded", (j.error_code, j.error_message)
    assert model.status == "ready"
    assert seen["step"] == 20 and seen["pm"] and seen["logs"] == ["attempt-1.log"]
    assert seen["opts"]["onnx"] is False and seen["opts"]["eval"] is True
    assert seen["status_during"] == "building"
    assert [e.data["status"] for e in events(engine, rid, "model")][-1] == "ready"

    metrics = {"overall": {"mae": 0.5, "mse": 0.25}, "per_joint": [], "n_frames": 3}
    monkeypatch.setattr(eval.offline, "evaluate_heldout", lambda **kw: {**metrics, "step": kw["step"]})
    ej = _job(engine, ws, "eval_checkpoint", {"checkpoint_id": str(ck.id), "step": 20}, run_id=rid)
    assert w.step() is True
    with engine.connect() as conn:
        j = conn.execute(select(jobs).where(jobs.c.id == ej)).one()
        em = conn.execute(select(checkpoints.c.eval_metrics).where(checkpoints.c.id == ck.id)).scalar_one()
    assert j.status == "succeeded", (j.error_code, j.error_message)
    assert j.result["action_mae"] == 0.5 and em["overall"]["mae"] == 0.5 and em["step"] == 20


# ---------------------------------------------------------------------------------------------
# SEC-input-1 (runner side) / SEC-input-2
# ---------------------------------------------------------------------------------------------
def test_init_from_hf_repo_is_fetched_locally(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    import train.runner

    calls: list[dict[str, Any]] = []

    def fake_fetch(repo_id: str, dest: Path, **kw: Any) -> Path:
        calls.append({"repo_id": repo_id, **kw})
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "config.json").write_text('{"type": "act"}')
        return dest

    monkeypatch.setattr(train.runner, "fetch_hf_init", fake_fetch)
    from core.testing import insert_run
    from train.tests.harness import fake_args

    rid = insert_run(
        engine,
        ws,
        total_steps=20,
        resolved_args=[*fake_args(20), "--policy.pretrained_path={{INIT_PATH}}"],
        config={
            "policy": {},
            "train": {"steps": 20, "log_freq": 10, "save_freq": 20},
            "_init_from": {"hf_repo_id": "attacker/evil"},
        },
    )
    WorkerThread(GpuWorker(settings_for(services, tmp_path))).start().join()
    r = run_row(engine, rid)
    assert r.status == "succeeded", (r.status, r.error_code, r.error_message)
    (call,) = calls
    assert call["repo_id"] == "attacker/evil" and call["policy_type"] == "act"
    assert call["env"]["HF_HUB_OFFLINE"] == "1"  # the child itself never talks to the Hub for it
    pre = [a for a in r.resolved_args if a.startswith("--policy.pretrained_path=")]
    assert pre and "attacker/evil" not in pre[0] and pre[0].endswith("/init/pretrained_model")


def test_child_env_is_an_allow_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from types import SimpleNamespace

    from train.runner import RunAttempt

    secrets = {
        "HIBISCUS_DATA_KEY": "K",
        "HIBISCUS_DATABASE_URL_SYNC": "postgresql://u:pw@h/db",
        "HIBISCUS_DATABASE_URL": "postgresql+psycopg://u:pw@h/db",
        "HIBISCUS_S3_SECRET_KEY": "S",
        "HIBISCUS_S3_ACCESS_KEY": "A",
        "HIBISCUS_REDIS_URL": "redis://:pw@redis",
        "HIBISCUS_JWT_PRIVATE_KEY": "jwt",
        "AWS_SECRET_ACCESS_KEY": "aws",
        "HF_TOKEN": "hf_x",
        "HUGGING_FACE_HUB_TOKEN": "hf_y",
        "SOME_NEW_SERVICE_PASSWORD": "p",
        "PYTHONPATH": "/opt/ros/lib",
    }
    for k, v in secrets.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("CUDA_DEVICE_ORDER", "PCI_BUS_ID")
    monkeypatch.setenv("NVIDIA_VISIBLE_DEVICES", "1")
    monkeypatch.setenv("FAKE_MODE", "normal")
    o = object.__new__(RunAttempt)
    o.s = SimpleNamespace(cache_dir=tmp_path, child_cuda_visible_devices="0", child_env_passthrough=["FAKE_"])  # type: ignore[assignment]
    env = o._env(True)
    assert not set(secrets) & set(env), sorted(set(secrets) & set(env))
    assert not [k for k in env if k.startswith("HIBISCUS_")]
    assert env["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID" and env["NVIDIA_VISIBLE_DEVICES"] == "1"
    assert env["CUDA_VISIBLE_DEVICES"] == "0" and env["HF_HUB_OFFLINE"] == "0"
    assert env["FAKE_MODE"] == "normal" and env["PATH"] == os.environ["PATH"]


# ---------------------------------------------------------------------------------------------
# QC-e2e-08 / QC-e2e-09
# ---------------------------------------------------------------------------------------------
def test_heartbeat_file_touched_by_worker(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed
) -> None:
    hb = tmp_path / "alive" / "hibiscus-worker.alive"
    rid = queue_run(engine, ws, steps=40)
    w = GpuWorker(settings_for(services, tmp_path, heartbeat_file=hb))
    t = threading.Thread(target=w.serve, daemon=True)
    t.start()
    wait_for(lambda: hb.is_file(), timeout=30)
    first = hb.stat().st_mtime
    wait_for(lambda: run_row(engine, rid).status == "succeeded", timeout=60)
    w.shutdown.set()
    w.wake.set()
    t.join(timeout=30)
    assert hb.stat().st_mtime >= first and time.time() - hb.stat().st_mtime < 120


def test_compose_env_names_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in {
        "HIBISCUS_GPU_NODE_ID": "cuda1",
        "HIBISCUS_GPU_DEVICE_INDEX": "1",
        "HIBISCUS_S3_ACCESS_KEY": "ak",
        "HIBISCUS_S3_SECRET_KEY": "sk",
        "HIBISCUS_S3_BUCKET_ARTIFACTS": "arts",
        "HIBISCUS_WORKER_HEARTBEAT_SECONDS": "7",
        "HIBISCUS_WORKER_LEASE_TTL_SECONDS": "33",
        "HIBISCUS_DATASET_CACHE_MAX_GB": "2",
        "HIBISCUS_WORKER_HEARTBEAT_FILE": "/tmp/hibiscus-worker.alive",  # noqa: S108 - path only
    }.items():
        monkeypatch.setenv(k, v)
    s = WorkerSettings()
    assert (s.gpu_id, s.gpu_index, s.nvml_device_index) == ("cuda1", 1, 1)
    assert (s.s3_access_key, s.s3_secret_key, s.bucket_artifacts) == ("ak", "sk", "arts")
    assert (s.heartbeat_interval_s, s.lease_ttl_s) == (7.0, 33)
    assert s.dataset_cache_max_bytes == 2 * 1024**3
    assert str(s.heartbeat_file) == "/tmp/hibiscus-worker.alive"  # noqa: S108
    monkeypatch.delenv("HIBISCUS_GPU_NODE_ID")
    monkeypatch.delenv("HIBISCUS_GPU_DEVICE_INDEX")
    monkeypatch.setenv("HIBISCUS_GPU_INDEX", "1")  # the canonical name
    assert WorkerSettings().gpu_id == "cuda1"
    # in the cuda1 container NVML sees one device, at index 0
    assert resolve_nvml_index(1, 1) == 0 and resolve_nvml_index(1, 2) == 1 and resolve_nvml_index(0, 1) == 0
