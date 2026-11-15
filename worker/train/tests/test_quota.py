"""Monthly GPU-hour quota enforced by the running worker (run-lifecycle §6 ``quota_exceeded``):
exhausted mid-run => ``pausing`` at the next checkpoint => ``paused`` (checkpoint kept, resumable
once the quota allows); exhausted before start => ``paused`` without spawning; notification
``quota.warning`` in both cases. Real PG/Redis/MinIO + the fake ``lerobot-train``."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, select, text

from core.tables import checkpoints, notifications
from core.testing import Seed, Services
from train.quota import gpu_hours, month_start
from train.tests.harness import (
    WorkerThread,
    api_transition,
    events,
    metric_steps,
    queue_run,
    run_row,
    settings_for,
    upload_dataset,
    wait_for,
)
from train.worker import GpuWorker


@pytest.fixture
def ws(engine: Engine, services: Services, tmp_path: Path) -> Seed:
    return upload_dataset(services, engine, None, tmp_path)


def _set_quota(engine: Engine, seed: Seed, hours: float, *, user: bool = False) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO quotas (id, workspace_id, user_id, gpu_hours_per_month) VALUES (:i, :w, :u, :h)"
            ),
            {"i": uuid.uuid4(), "w": seed.workspace_id, "u": seed.user_id if user else None, "h": hours},
        )


def _notes(engine: Engine, kind: str) -> list[dict[str, object]]:
    with engine.connect() as conn:
        rows = conn.execute(select(notifications.c.params).where(notifications.c.kind == kind)).scalars()
        return [dict(r) for r in rows]


def _activity(engine: Engine, rid: uuid.UUID, *steps: tuple[str, datetime]) -> None:
    """Status events (``data.to``) at the given times, as the API / worker / reaper write them."""
    with engine.begin() as conn:
        for seq, (to, ts) in enumerate(steps, start=1):
            conn.execute(
                text(
                    "INSERT INTO run_events (run_id, seq, type, level, attempt, data, created_at) "
                    "VALUES (:r, :s, 'status', 'info', 1, CAST(:d AS jsonb), :t)"
                ),
                {"r": rid, "s": seq, "d": json.dumps({"kind": "status", "to": to}), "t": ts},
            )
        conn.execute(text("UPDATE runs SET last_event_seq = :n WHERE id = :r"), {"n": len(steps), "r": rid})


def test_gpu_hours_resolution(engine: Engine, ws: Seed) -> None:
    with engine.connect() as conn:
        h = gpu_hours(conn, ws.workspace_id, ws.user_id)
    assert h.limit_h == 200.0 and h.used_h == 0.0 and not h.exhausted
    now = datetime.now(UTC)
    old = month_start() - timedelta(days=3)
    last = queue_run(engine, ws, status="succeeded", gpu_seconds=7200.0, finished_at=old)  # last month
    _activity(engine, last, ("preparing", old - timedelta(hours=2)), ("succeeded", old))
    done = queue_run(engine, ws, status="succeeded", gpu_seconds=3600.0, finished_at=now)
    _activity(engine, done, ("preparing", now - timedelta(hours=1)), ("succeeded", now))
    paused = queue_run(engine, ws, status="paused", gpu_seconds=1800.0)  # ran 30 min this month
    _activity(
        engine, paused, ("preparing", now - timedelta(hours=1)), ("paused", now - timedelta(minutes=30))
    )
    _set_quota(engine, ws, 10.0)
    with engine.connect() as conn:
        h = gpu_hours(conn, ws.workspace_id, ws.user_id)
    assert h.limit_h == 10.0 and h.used_h == pytest.approx(1.5, abs=1e-3) and h.percent == 15
    _set_quota(engine, ws, 1.5, user=True)  # per-user row overrides the workspace row
    with engine.connect() as conn:
        h = gpu_hours(conn, ws.workspace_id, ws.user_id)
    assert h.limit_h == 1.5 and h.exhausted


def test_gpu_hours_count_only_this_months_usage(engine: Engine, ws: Seed) -> None:
    """QC-backend-03: a run quota-paused last month (200 GPU-h) must not lock its owner out of
    resuming / creating runs in later months; a run spanning the month boundary only counts the
    part it ran this month; queued and paused runs add nothing while they wait."""
    ms = month_start()
    long_ago = ms - timedelta(days=45)
    paused = queue_run(engine, ws, status="paused", gpu_seconds=200 * 3600.0, error_code="quota_exceeded")
    _activity(
        engine,
        paused,
        ("preparing", long_ago - timedelta(days=9)),
        ("running", long_ago - timedelta(days=9)),
        ("pausing", long_ago),
        ("paused", long_ago),
    )
    queued = queue_run(engine, ws, status="queued", gpu_seconds=3600.0)  # re-queued after an infra error
    _activity(engine, queued, ("preparing", long_ago - timedelta(hours=1)), ("queued", long_ago))
    with engine.connect() as conn:
        h = gpu_hours(conn, ws.workspace_id, ws.user_id)
    assert h.used_h == 0.0 and not h.exhausted
    spanning = queue_run(
        engine, ws, status="succeeded", gpu_seconds=5400.0, finished_at=ms + timedelta(minutes=30)
    )
    _activity(
        engine,
        spanning,
        ("preparing", ms - timedelta(hours=1)),
        ("running", ms - timedelta(hours=1)),
        ("succeeded", ms + timedelta(minutes=30)),
    )
    with engine.connect() as conn:
        h = gpu_hours(conn, ws.workspace_id, ws.user_id)
    assert h.used_h == pytest.approx(0.5, abs=1e-3)


def test_user_requested_gpu_jobs_count_toward_gpu_hours(engine: Engine, ws: Seed) -> None:
    """Phase-5 re-verify N6: user-requested export / eval GPU jobs add their time this month
    (same statement as the API); other jobs and last month's jobs do not."""
    ms = month_start()
    now = datetime.now(UTC)
    rid = queue_run(engine, ws, status="succeeded", gpu_seconds=0.0, finished_at=now)
    rows = [
        ("eval_checkpoint", True, max(ms, now - timedelta(minutes=30)), now),
        ("export_model", True, ms - timedelta(hours=2), ms + timedelta(minutes=6)),  # 6 min this month
        ("export_model", False, max(ms, now - timedelta(hours=5)), now),  # automatic export: no
        ("estimate_resources", True, max(ms, now - timedelta(hours=5)), now),
        ("eval_checkpoint", True, ms - timedelta(days=10), ms - timedelta(days=9)),  # last month
    ]
    with engine.begin() as conn:
        for kind, user_req, start, end in rows:
            conn.execute(
                text(
                    "INSERT INTO jobs (id, workspace_id, kind, resource, status, payload, run_id, created_by,"
                    " started_at, finished_at) VALUES (:i, :w, :k, 'gpu', 'succeeded', CAST(:p AS jsonb),"
                    " :r, :u, :s, :e)"
                ),
                {
                    "i": uuid.uuid4(),
                    "w": ws.workspace_id,
                    "k": kind,
                    "p": json.dumps({"user_requested": user_req}),
                    "r": rid,
                    "u": ws.user_id,
                    "s": start,
                    "e": end,
                },
            )
    expected_s = (now - max(ms, now - timedelta(minutes=30))).total_seconds() + 360
    with engine.connect() as conn:
        h = gpu_hours(conn, ws.workspace_id, ws.user_id)
    assert h.used_h == pytest.approx(expected_s / 3600.0, abs=1e-3)


def test_quota_exhausted_mid_run_pauses_at_next_checkpoint(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_MODE", "normal")
    monkeypatch.setenv("FAKE_STEP_S", "0.05")
    rid = queue_run(engine, ws, steps=200, save_freq=40)
    w = GpuWorker(settings_for(services, tmp_path, quota_check_interval_s=0.3))
    t = WorkerThread(w).start()
    wait_for(lambda: run_row(engine, rid).status == "running")
    _set_quota(engine, ws, 0.0)  # e.g. an admin lowers the limit / the month's budget is used up
    t.join()
    r = run_row(engine, rid)
    assert r.status == "paused", (r.status, r.error_code, r.error_message)
    assert r.error_code == "quota_exceeded" and r.desired_state == "run" and r.gpu_node_id is None
    step = r.resume_checkpoint_step
    assert step is not None and step % 40 == 0 and step < 200, step
    st = [e.data for e in events(engine, rid, "status")]
    assert [s["to"] for s in st] == ["preparing", "running", "pausing", "paused"]
    assert st[2]["reason"] == st[3]["reason"] == "quota_exceeded"
    assert st[2]["error_code"] == st[3]["error_code"] == "quota_exceeded"
    with engine.connect() as conn:
        last = conn.execute(
            select(checkpoints.c.step, checkpoints.c.has_training_state).where(
                checkpoints.c.run_id == rid, checkpoints.c.is_last.is_(True)
            )
        ).one()
    assert last.step == step and last.has_training_state  # nothing lost: resumable checkpoint
    (note,) = _notes(engine, "quota.warning")
    assert note["run_id"] == str(rid) and note["reason"] == "quota_exceeded" and note["percent"] == 100

    # quota raised -> the user resumes (T8; the API clears error_code) and training continues
    _set_quota(engine, ws, 1000.0, user=True)
    api_transition(engine, rid, ["paused"], "queued", desired_state="run", error_code=None)
    monkeypatch.setenv("FAKE_STEP_S", "0.005")
    WorkerThread(GpuWorker(settings_for(services, tmp_path, quota_check_interval_s=0.3))).start().join()
    r = run_row(engine, rid)
    assert r.status == "succeeded" and r.attempt == 2 and r.error_code is None
    assert [a["resumed_from_step"] for a in r.manifest["attempts"]] == [None, step]
    assert metric_steps(engine, rid) == list(range(10, 201, 10))


def test_quota_exhausted_before_start_pauses_without_training(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_MODE", "normal")
    now = datetime.now(UTC)
    used = queue_run(engine, ws, status="succeeded", gpu_seconds=2 * 3600.0, finished_at=now)
    _activity(engine, used, ("preparing", now - timedelta(hours=2)), ("succeeded", now))
    _set_quota(engine, ws, 1.0)
    rid = queue_run(engine, ws, steps=60, resume_checkpoint_step=None)
    WorkerThread(GpuWorker(settings_for(services, tmp_path))).start().join()
    r = run_row(engine, rid)
    assert r.status == "paused" and r.error_code == "quota_exceeded" and r.resume_checkpoint_step is None
    assert [e.data["to"] for e in events(engine, rid, "status")] == ["preparing", "pausing", "paused"]
    assert metric_steps(engine, rid) == [] and r.gpu_node_id is None
    (note,) = _notes(engine, "quota.warning")
    assert note["percent"] == 200 and note["used_h"] == 2.0 and note["limit_h"] == 1.0
