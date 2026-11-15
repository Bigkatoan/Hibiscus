"""Run lifecycle end to end with a fake lerobot-train (same output format) and real PG/Redis/MinIO.

Covers run-lifecycle T2-T13, §3 pause modes, §4 checkpoints, §6 classification + one infra retry,
§8 graceful shutdown / lease loss, log-parsing §6 anomaly rules.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select, text, update

from core.tables import checkpoints, gpu_nodes, models, runs
from core.testing import Seed, Services
from train.tests.harness import (
    WorkerThread,
    api_transition,
    events,
    metric_steps,
    queue_run,
    run_row,
    settings_for,
    store_for,
    upload_dataset,
    wait_for,
)
from train.worker import GpuWorker


@pytest.fixture
def ws(engine: Engine, services: Services, tmp_path: Path) -> Seed:
    seed = upload_dataset(services, engine, None, tmp_path)
    return seed


def _worker(services: Services, tmp_path: Path, **over: object) -> GpuWorker:
    return GpuWorker(settings_for(services, tmp_path, **over))


def _statuses(engine: Engine, rid: object) -> list[str]:
    return [e.data["to"] for e in events(engine, rid, "status")]  # type: ignore[arg-type]


def test_success_metrics_checkpoints_logs(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_MODE", "normal")
    rid = queue_run(engine, ws, steps=60, mixed_precision_requested="bf16")
    w = _worker(services, tmp_path, fake_gpu_cc="6.1", fake_gpu_name="Tesla P40", fake_gpu_vram_mb=24576)
    WorkerThread(w).start().join()
    r = run_row(engine, rid)
    assert r.status == "succeeded", (r.status, r.error_code, r.error_message)
    assert _statuses(engine, rid) == ["preparing", "running", "exporting", "succeeded"]
    assert metric_steps(engine, rid) == [10, 20, 30, 40, 50, 60]
    assert r.current_step == 60 and r.attempt == 1 and r.lease_owner is None
    # P40 has no bf16 -> forced fp32 + warning, effective value recorded and passed quoted to draccus
    assert r.mixed_precision_effective == "no"
    assert '--accelerator.mixed_precision="no"' in r.resolved_args
    assert "--num_workers=4" in r.resolved_args
    assert any(e.data["code"] == "mixed_precision_forced_no" for e in events(engine, rid, "warning"))
    with engine.connect() as conn:
        cks = conn.execute(
            select(checkpoints).where(checkpoints.c.run_id == rid).order_by(checkpoints.c.step)
        ).all()
        model = conn.execute(select(models).where(models.c.run_id == rid)).one()
        gpu = conn.execute(select(gpu_nodes)).one()
    assert [c.step for c in cks] == [20, 40, 60]
    assert [c.is_last for c in cks] == [False, False, True]
    assert [c.has_training_state for c in cks] == [False, False, True]
    st = store_for(services)
    keys = {o.key for o in st.list_prefix("hibiscus-artifacts", f"runs/{rid}/")}
    for s in (20, 40, 60):
        assert f"runs/{rid}/checkpoints/{s:06d}/pretrained_model/model.safetensors" in keys
    assert f"runs/{rid}/checkpoints/000060/training_state/training_step.json" in keys
    assert f"runs/{rid}/checkpoints/000020/training_state/training_step.json" not in keys
    log = st.get_bytes("hibiscus-artifacts", f"runs/{rid}/logs/attempt-1.log").decode()
    assert "End of training" in log and "\r" not in log
    # D3: no exporter installed in this worktree -> model failed, run still succeeded
    assert model.status == "failed" and gpu.current_run_id is None
    assert [e.data["status"] for e in events(engine, rid, "model")] == ["building", "failed"]
    m = r.manifest
    assert m["attempts"][0]["exit_code"] == 0 and m["gpu"]["name"] == "Tesla P40"
    assert m["mixed_precision"] == "no" and m["dataset"]["repo_id"] == "local/golden"
    assert not (tmp_path / "scratch" / "runs" / str(rid)).exists()
    # metrics event payload is the exact step and the canonical keys
    me = events(engine, rid, "metrics")[0].data
    assert me["step"] == 10 and set(me["values"]) >= {
        "loss",
        "grad_norm",
        "lr",
        "samples_per_s",
        "gpu_mem_gb",
    }


def test_pause_at_next_checkpoint_then_resume(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_MODE", "normal")
    monkeypatch.setenv("FAKE_STEP_S", "0.05")
    rid = queue_run(engine, ws, steps=100, save_freq=40)
    w = _worker(services, tmp_path)
    t = WorkerThread(w).start()
    wait_for(lambda: run_row(engine, rid).status == "running")
    api_transition(engine, rid, ["running"], "pausing", desired_state="pause")
    w.wake.set()
    t.join()
    r = run_row(engine, rid)
    assert r.status == "paused" and r.resume_checkpoint_step == 40, (r.status, r.resume_checkpoint_step)
    assert r.gpu_node_id is None
    # resume (T8) -> second attempt continues from 40
    api_transition(engine, rid, ["paused"], "queued", desired_state="run")
    monkeypatch.setenv("FAKE_STEP_S", "0.005")
    WorkerThread(_worker(services, tmp_path)).start().join()
    r = run_row(engine, rid)
    assert r.status == "succeeded" and r.attempt == 2
    assert "--resume=true" in r.resolved_args
    assert any(
        a.startswith("--config_path=") and a.endswith("000040/pretrained_model/train_config.json")
        for a in r.resolved_args
    )
    steps = metric_steps(engine, rid)
    assert steps == list(range(10, 101, 10)), steps
    assert [a["resumed_from_step"] for a in r.manifest["attempts"]] == [None, 40]


def test_pause_now_before_first_checkpoint(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_STEP_S", "0.05")
    rid = queue_run(engine, ws, steps=200, save_freq=150)
    w = _worker(services, tmp_path)
    t = WorkerThread(w).start()
    wait_for(lambda: run_row(engine, rid).status == "running")
    api_transition(engine, rid, ["running"], "pausing", desired_state="pause_now")
    w.wake.set()
    t.join()
    r = run_row(engine, rid)
    assert r.status == "paused" and r.resume_checkpoint_step is None


def test_cancel_running(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_STEP_S", "0.05")
    rid = queue_run(engine, ws, steps=500)
    w = _worker(services, tmp_path)
    t = WorkerThread(w).start()
    wait_for(lambda: run_row(engine, rid).status == "running")
    api_transition(engine, rid, ["running"], "cancelling", desired_state="cancel")
    w.wake.set()
    t.join()
    r = run_row(engine, rid)
    assert r.status == "cancelled" and r.finished_at is not None
    assert _statuses(engine, rid)[-2:] == ["cancelling", "cancelled"]
    assert not (tmp_path / "scratch" / "runs" / str(rid)).exists()


def test_nan_loss_fails_without_retry(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_MODE", "nan")
    monkeypatch.setenv("FAKE_STEP_S", "0.01")
    rid = queue_run(engine, ws, steps=300)
    WorkerThread(_worker(services, tmp_path)).start().join()
    r = run_row(engine, rid)
    assert r.status == "failed" and r.error_code == "nan_loss" and r.infra_retries_used == 0
    assert [e.data["code"] for e in events(engine, rid, "warning")].count("nan_detected") == 1
    err = events(engine, rid, "error")[-1].data
    assert err["code"] == "nan_loss" and err["will_retry"] is False and err["log_excerpt"]


def test_crash_retries_once_from_checkpoint(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_MODE", "crash")
    monkeypatch.setenv("FAKE_CRASH_AT", "30")
    rid = queue_run(engine, ws, steps=60)
    WorkerThread(_worker(services, tmp_path)).start().join()
    r = run_row(engine, rid)
    assert r.status == "queued" and r.infra_retries_used == 1 and r.resume_checkpoint_step == 20
    codes = [e.data["code"] for e in events(engine, rid, "warning")]
    assert "retrying_after_infra_error" in codes
    assert events(engine, rid, "error")[-1].data["code"] == "process_crashed"
    # second attempt crashes again (resumes at 20, crashes at 30) -> budget exhausted -> failed
    WorkerThread(_worker(services, tmp_path)).start().join()
    r = run_row(engine, rid)
    assert r.status == "failed" and r.error_code == "process_crashed" and r.attempt == 2
    assert r.resume_checkpoint_step == 20


def test_crash_then_successful_retry(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_MODE", "crash")
    monkeypatch.setenv("FAKE_CRASH_AT", "45")
    rid = queue_run(engine, ws, steps=60)
    WorkerThread(_worker(services, tmp_path)).start().join()
    assert run_row(engine, rid).resume_checkpoint_step == 40
    monkeypatch.setenv("FAKE_MODE", "normal")
    WorkerThread(_worker(services, tmp_path)).start().join()
    r = run_row(engine, rid)
    assert r.status == "succeeded" and r.attempt == 2
    assert metric_steps(engine, rid) == [10, 20, 30, 40, 50, 60]


@pytest.mark.parametrize(("mode", "code"), [("config_error", "config_invalid"), ("oom", "oom")])
def test_user_errors_not_retried(
    engine: Engine,
    services: Services,
    tmp_path: Path,
    ws: Seed,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    code: str,
) -> None:
    monkeypatch.setenv("FAKE_MODE", mode)
    rid = queue_run(engine, ws, steps=60)
    WorkerThread(_worker(services, tmp_path)).start().join()
    r = run_row(engine, rid)
    assert r.status == "failed" and r.error_code == code and r.infra_retries_used == 0


def test_stall_detection(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_MODE", "silent")
    rid = queue_run(engine, ws, steps=60)
    WorkerThread(_worker(services, tmp_path, log_silent_warn_s=1.0, log_silent_kill_s=3.0)).start().join()
    r = run_row(engine, rid)
    assert "log_silent" in [e.data["code"] for e in events(engine, rid, "warning")]
    assert events(engine, rid, "error")[-1].data["code"] == "stalled"
    assert r.status == "queued" and r.infra_retries_used == 1  # stalled is infra -> one retry
    with engine.connect() as conn:
        kinds = list(conn.execute(text("SELECT kind FROM notifications")).scalars())
    assert "run.stalled" in kinds


def test_graceful_shutdown_requeues_without_consuming_retry(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_STEP_S", "0.05")
    rid = queue_run(engine, ws, steps=400, save_freq=20)
    w = _worker(services, tmp_path)
    t = WorkerThread(w).start()
    wait_for(lambda: run_row(engine, rid).current_step >= 25, timeout=60)
    w.shutdown.set()
    t.join()
    r = run_row(engine, rid)
    assert r.status == "queued" and r.infra_retries_used == 0
    assert r.resume_checkpoint_step is not None and r.resume_checkpoint_step >= 20
    assert events(engine, rid, "status")[-1].data["reason"] == "worker_shutdown"


def test_lease_lost_kills_process(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_STEP_S", "0.05")
    rid = queue_run(engine, ws, steps=1000)
    w = _worker(services, tmp_path)
    t = WorkerThread(w).start()
    wait_for(lambda: run_row(engine, rid).status == "running")
    with engine.begin() as conn:  # e.g. the reaper re-queued it after a network partition
        conn.execute(update(runs).where(runs.c.id == rid).values(lease_owner="someone-else"))
    t0 = time.time()
    t.join(timeout=30)
    assert time.time() - t0 < 30
    r = run_row(engine, rid)
    assert r.status == "running" and r.lease_owner == "someone-else"  # untouched by the old worker


def test_progress_and_log_events_on_redis(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    import redis

    monkeypatch.setenv("FAKE_STEP_S", "0.02")
    rid = queue_run(engine, ws, steps=120)
    sub = redis.Redis.from_url(services.redis_url).pubsub()  # type: ignore[no-untyped-call]  # redis stub
    sub.subscribe(f"hibiscus:run:{rid}")
    WorkerThread(_worker(services, tmp_path)).start().join()
    seen: dict[str, list[dict[str, Any]]] = {}
    while (msg := sub.get_message(timeout=0.5)) is not None:
        if msg["type"] == "message":
            env = json.loads(msg["data"])
            seen.setdefault(env["event"], []).append(env)
    assert {"status", "metrics", "checkpoint", "progress", "log"} <= set(seen)
    assert all(e["id"] is None for e in seen["progress"] + seen["log"])
    assert all(isinstance(e["id"], int) for e in seen["metrics"])
    logs = [ln for e in seen["log"] for ln in e["data"]["lines"]]
    assert any("End of training" in ln for ln in logs) and not any("\r" in ln for ln in logs)
    offs = [e["data"]["byte_offset"] for e in seen["log"]]
    assert offs == sorted(offs) and offs[0] == 0
