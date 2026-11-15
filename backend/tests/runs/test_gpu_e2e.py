"""REAL GPU end-to-end (cuda:0, RTX 3060): API -> Postgres queue -> worker process -> unmodified
``lerobot-train`` 0.7.1 -> metrics/checkpoints in Postgres/MinIO, then kill-the-worker -> reaper ->
resume from the uploaded checkpoint on a fresh worker.

Opt-in (needs the worker venv with lerobot + torch and a free cuda:0)::

    cd backend && HIBISCUS_GPU_E2E=1 env -u PYTHONPATH uv run pytest -q tests/runs/test_gpu_e2e.py -s
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import boto3
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import models as m
from app.runs.reaper import reap_once
from tests.runs.conftest import GOLDEN, REPO, Services, World, check, run_body

pytestmark = pytest.mark.skipif(
    os.environ.get("HIBISCUS_GPU_E2E") != "1", reason="set HIBISCUS_GPU_E2E=1 (GPU box)"
)
WORKER = REPO / "worker"
PY = WORKER / ".venv" / "bin" / "python"
LEROBOT_TRAIN = WORKER / ".venv" / "bin" / "lerobot-train"


def content_hash(root: Path) -> str:
    lines = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            lines.append(f"{p.relative_to(root).as_posix()}\0{hashlib.sha256(p.read_bytes()).hexdigest()}\n")
    h = hashlib.sha256()
    for ln in sorted(lines):
        h.update(ln.encode())
    return h.hexdigest()


def upload_golden(services: Services, prefix: str) -> None:
    s3 = boto3.client(
        "s3",
        endpoint_url=services.s3_endpoint,
        aws_access_key_id=services.s3_key,
        aws_secret_access_key=services.s3_secret,
        region_name="us-east-1",
    )
    for p in sorted(GOLDEN.rglob("*")):
        if p.is_file():
            s3.upload_file(str(p), "hibiscus-datasets", f"{prefix}/{p.relative_to(GOLDEN).as_posix()}")


def start_worker(services: Services, tmp: Path, log_name: str) -> subprocess.Popen[bytes]:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "AMENT_PREFIX_PATH", "VIRTUAL_ENV")}
    env.update(
        HIBISCUS_DATABASE_URL=services.pg_sync,
        HIBISCUS_REDIS_URL=services.redis_url,
        HIBISCUS_S3_ENDPOINT_URL=services.s3_endpoint,
        HIBISCUS_S3_ACCESS_KEY=services.s3_key,
        HIBISCUS_S3_SECRET_KEY=services.s3_secret,
        HIBISCUS_GPU_INDEX="0",
        HIBISCUS_CHILD_CUDA_VISIBLE_DEVICES="0",  # A4 may only use cuda:0
        HIBISCUS_SCRATCH_DIR=str(tmp / "scratch"),
        HIBISCUS_CACHE_DIR=str(tmp / "cache"),
        HIBISCUS_LEROBOT_TRAIN_BIN=str(LEROBOT_TRAIN),
        HIBISCUS_LEASE_TTL_S="20",
        HIBISCUS_HEARTBEAT_INTERVAL_S="5",
        HIBISCUS_IMAGE_DIGEST="sha256:" + "1" * 64,
        PYTHONDONTWRITEBYTECODE="1",
    )
    logf = (tmp / log_name).open("wb")
    return subprocess.Popen(  # noqa: S603 - test harness
        [str(PY), "-m", "train"],
        cwd=str(WORKER),
        env=env,
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def q1(eng: Any, sql: str, **p: Any) -> Any:
    with eng.connect() as conn:
        return conn.execute(text(sql), p).one()


def wait(pred: Any, timeout: float, what: str, proc: subprocess.Popen[bytes] | None = None) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return
        if proc is not None and proc.poll() is not None:
            raise AssertionError(f"worker died while waiting for {what} (rc={proc.returncode})")
        time.sleep(1.0)
    raise AssertionError(f"timeout waiting for {what}")


def children(pid: int) -> list[int]:
    out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True, check=False).stdout  # noqa: S603, S607
    return [int(x) for x in out.split()]


async def test_real_act_training_then_kill_and_resume(
    client: httpx.AsyncClient, world: World, services: Services, sync_engine: Any, tmp_path: Path
) -> None:
    prefix = f"{world.workspace_id}/{world.dataset_id}/1"
    upload_golden(services, prefix)
    with Session(sync_engine) as s:
        s.execute(
            text("UPDATE dataset_versions SET content_hash=:h, storage_prefix=:p WHERE id=:v"),
            {"h": content_hash(GOLDEN), "p": f"s3://hibiscus-datasets/{prefix}/", "v": world.version_id},
        )
        s.execute(
            text("UPDATE gpu_nodes SET status='disabled' WHERE id='cuda1'")
        )  # keep everything on cuda:0
        s.commit()

    # ---------------------------------------------------------------- 1. 300-step ACT run
    body = run_body(
        world,
        name="gpu-e2e-300",
        config={
            "policy": {},
            "train": {"steps": 300, "save_freq": 100, "log_freq": 25, "batch_size": 8, "num_workers": 2},
        },
    )
    run = check(await client.post("/runs", json=body), "/runs", "POST")
    rid = uuid.UUID(run["id"])
    w1 = start_worker(services, tmp_path, "worker1.log")
    try:
        wait(
            lambda: (
                q1(sync_engine, "SELECT status FROM runs WHERE id=:r", r=rid)[0] in ("succeeded", "failed")
            ),
            900,
            "run 1 to finish",
            w1,
        )
        r = q1(
            sync_engine,
            "SELECT status, error_code, error_message, current_step, mixed_precision_effective, "
            "manifest, resolved_args, gpu_seconds FROM runs WHERE id=:r",
            r=rid,
        )
        assert r.status == "succeeded", (
            r.error_code,
            r.error_message,
            (tmp_path / "worker1.log").read_text()[-3000:],
        )
        assert r.current_step == 300 and r.mixed_precision_effective == "no" and r.gpu_seconds > 0
        assert r.manifest["gpu"]["name"] == "NVIDIA GeForce RTX 3060"
        assert r.manifest["lerobot_version"] == "0.7.1" and r.manifest["torch_version"].startswith("2.15")
        assert any(a.startswith("--dataset.episodes=[") for a in r.resolved_args)
        with sync_engine.connect() as conn:
            steps = list(
                conn.execute(
                    text("SELECT step FROM run_metrics WHERE run_id=:r AND key='loss' ORDER BY step"),
                    {"r": rid},
                ).scalars()
            )
            keys = set(
                conn.execute(
                    text("SELECT DISTINCT key FROM run_metrics WHERE run_id=:r"), {"r": rid}
                ).scalars()
            )
            cks = conn.execute(
                text(
                    "SELECT step, is_last, has_training_state, size_bytes FROM checkpoints "
                    "WHERE run_id=:r ORDER BY step"
                ),
                {"r": rid},
            ).all()
            tel = conn.execute(
                text("SELECT count(*), max(mem_used_mb) FROM gpu_telemetry WHERE run_id=:r"), {"r": rid}
            ).one()
            mem = conn.execute(
                text("SELECT max(value) FROM run_metrics WHERE run_id=:r AND key='gpu_mem_gb'"), {"r": rid}
            ).scalar_one()
        assert steps == list(range(25, 301, 25)), steps  # exact steps, never the rounded label
        assert {
            "loss",
            "grad_norm",
            "lr",
            "l1_loss",
            "kld_loss",
            "gpu_mem_gb",
            "samples_per_s",
            "epoch",
        } <= keys
        assert [(c.step, c.is_last, c.has_training_state) for c in cks] == [
            (100, False, False),
            (200, False, False),
            (300, True, True),
        ]
        assert all(c.size_bytes > 100_000_000 for c in cks)  # ACT weights (+ optimizer state on the last)
        assert tel[0] >= 3 and tel[1] > 500
        s3 = boto3.client(
            "s3",
            endpoint_url=services.s3_endpoint,
            aws_access_key_id=services.s3_key,
            aws_secret_access_key=services.s3_secret,
            region_name="us-east-1",
        )
        keys_s3 = {
            o["Key"]
            for o in s3.list_objects_v2(Bucket="hibiscus-artifacts", Prefix=f"runs/{rid}/")["Contents"]
        }
        assert f"runs/{rid}/checkpoints/000300/pretrained_model/model.safetensors" in keys_s3
        assert f"runs/{rid}/checkpoints/000300/training_state/optimizer_state.safetensors" in keys_s3
        assert f"runs/{rid}/checkpoints/000100/training_state/optimizer_state.safetensors" not in keys_s3
        assert f"runs/{rid}/logs/attempt-1.log" in keys_s3
        # the API reads it all back
        ms = check(
            await client.get(f"/runs/{rid}/metrics", params={"keys": "loss"}), "/runs/{run_id}/metrics"
        )
        assert ms["series"][0]["steps"] == steps
        got = check(await client.get(f"/runs/{rid}"), "/runs/{run_id}")
        assert got["status"] == "succeeded" and got["progress"]["last_checkpoint_step"] == 300
        logs = await client.get(f"/runs/{rid}/logs")
        assert "End of training" in logs.text
        # the export hook ran: verified bundle with ONNX in object storage, exposed by the models API
        mods = check(
            await client.get("/models", params={"workspace_id": str(world.workspace_id), "run_id": str(rid)}),
            "/models",
        )
        mine = [x for x in mods["items"] if x["run_id"] == str(rid)]
        assert len(mine) == 1, mods
        mdl = mine[0]
        assert mdl["status"] == "ready" and mdl["verified"] is True, mdl
        assert mdl["onnx_status"] == "passed", mdl
        bundle_keys = {
            o["Key"]
            for o in s3.list_objects_v2(Bucket="hibiscus-artifacts", Prefix=f"models/{mdl['id']}/").get(
                "Contents", []
            )
        }
        assert any(k.endswith("-step300.zip") for k in bundle_keys), bundle_keys
        print(f"\n[gpu-e2e] run1 metrics steps={steps} peak torch mem={mem} GB telemetry max={tel[1]} MiB")
        print(
            f"[gpu-e2e] model {mdl['name']} verified={mdl['verified']} onnx={mdl['onnx_status']}"
            f" keys={sorted(bundle_keys)}"
        )

        # ------------------------------------------------------------ 2. kill the worker mid-run
        body2 = run_body(
            world,
            name="gpu-e2e-kill",
            config={
                "policy": {},
                "train": {"steps": 600, "save_freq": 100, "log_freq": 25, "batch_size": 8, "num_workers": 2},
            },
        )
        run2 = check(await client.post("/runs", json=body2), "/runs", "POST")
        rid2 = uuid.UUID(run2["id"])
        wait(
            lambda: (
                q1(sync_engine, "SELECT count(*) FROM checkpoints WHERE run_id=:r", r=rid2)[0] >= 1
                and q1(sync_engine, "SELECT current_step FROM runs WHERE id=:r", r=rid2)[0] >= 150
            ),
            900,
            "run 2 to pass its first uploaded checkpoint",
            w1,
        )
        killed_at = q1(sync_engine, "SELECT current_step FROM runs WHERE id=:r", r=rid2)[0]
        # docker kill semantics: the whole container dies (worker + lerobot-train process group)
        kids = children(w1.pid)
        os.kill(w1.pid, signal.SIGKILL)
        for k in kids:
            try:
                os.killpg(k, signal.SIGKILL)
            except ProcessLookupError:
                pass
        w1.wait(timeout=30)
        last = q1(sync_engine, "SELECT max(step) FROM checkpoints WHERE run_id=:r AND is_last", r=rid2)[0]
        st = client.app.state.runs  # type: ignore[attr-defined]
        deadline = time.time() + 120
        done: list[str] = []
        while time.time() < deadline and not done:
            done = await reap_once(st.sessionmaker, st.redis)
            if not done:
                await asyncio.sleep(2)
        assert done == [f"{rid2}:queued"], done
        r2 = q1(
            sync_engine,
            "SELECT status, infra_retries_used, resume_checkpoint_step, error_code FROM runs WHERE id=:r",
            r=rid2,
        )
        assert (r2.status, r2.infra_retries_used, r2.resume_checkpoint_step) == ("queued", 1, last)
        print(f"[gpu-e2e] killed at step {killed_at}, last uploaded checkpoint {last}")

        # ------------------------------------------------------------ 3. fresh worker resumes
        w2 = start_worker(services, tmp_path, "worker2.log")
        try:
            wait(
                lambda: (
                    q1(sync_engine, "SELECT status FROM runs WHERE id=:r", r=rid2)[0]
                    in ("succeeded", "failed")
                ),
                900,
                "run 2 to finish after resume",
                w2,
            )
            r3 = q1(
                sync_engine,
                "SELECT status, error_code, error_message, attempt, resolved_args, manifest "
                "FROM runs WHERE id=:r",
                r=rid2,
            )
            assert r3.status == "succeeded", (
                r3.error_code,
                r3.error_message,
                (tmp_path / "worker2.log").read_text()[-3000:],
            )
            assert r3.attempt == 2 and "--resume=true" in r3.resolved_args
            assert any(a.endswith(f"{last:06d}/pretrained_model/train_config.json") for a in r3.resolved_args)
            assert [a["resumed_from_step"] for a in r3.manifest["attempts"]] == [None, last]
            with sync_engine.connect() as conn:
                steps2 = list(
                    conn.execute(
                        text("SELECT step FROM run_metrics WHERE run_id=:r AND key='loss' ORDER BY step"),
                        {"r": rid2},
                    ).scalars()
                )
                ck2 = list(
                    conn.execute(
                        text("SELECT step FROM checkpoints WHERE run_id=:r ORDER BY step"), {"r": rid2}
                    ).scalars()
                )
            assert steps2 == list(range(25, 601, 25)), (
                steps2
            )  # resumed attempt continues the exact step count
            assert ck2 == [100, 200, 300, 400, 500, 600]
            ev = check(
                await client.get(f"/runs/{rid2}/events/history", params={"types": "status"}),
                "/runs/{run_id}/events/history",
            )
            tos = [e["data"]["to"] for e in ev["items"]]
            assert tos == [
                "queued",
                "preparing",
                "running",
                "queued",
                "preparing",
                "running",
                "exporting",
                "succeeded",
            ], tos
            log2 = await client.get(f"/runs/{rid2}/logs")
            assert "attempt 2 on cuda0" in log2.text
            print(f"[gpu-e2e] resumed from {last}, metrics steps after resume ok ({len(steps2)} rows)")
        finally:
            w2.send_signal(signal.SIGTERM)
            try:
                w2.wait(timeout=120)
            except subprocess.TimeoutExpired:
                os.killpg(w2.pid, signal.SIGKILL)
    finally:
        if w1.poll() is None:
            w1.send_signal(signal.SIGTERM)
            try:
                w1.wait(timeout=120)
            except subprocess.TimeoutExpired:
                os.killpg(w1.pid, signal.SIGKILL)
    with Session(sync_engine) as s:
        est = s.query(m.ResourceEstimate).all()
    print(
        f"[gpu-e2e] resource estimates measured: {[(e.policy_type, e.peak_vram_mb, e.sec_per_step) for e in est]}"  # noqa: E501
    )
