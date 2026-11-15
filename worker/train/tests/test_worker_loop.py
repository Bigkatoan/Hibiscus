"""Worker serve loop, estimate job (fake trainer), NVML telemetry (gpu marker: read-only NVML on cuda:0)."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from core.tables import gpu_nodes, gpu_telemetry, jobs, resource_estimates
from core.testing import Seed, Services, contract_metadata
from train.telemetry import Nvml, TelemetrySampler
from train.tests.harness import fake_args, queue_run, run_row, settings_for, upload_dataset, wait_for
from train.worker import GpuWorker


@pytest.fixture
def ws(engine: Engine, services: Services, tmp_path: Path) -> Seed:
    return upload_dataset(services, engine, None, tmp_path)


def _estimate_job(engine: Engine, seed: Seed) -> uuid.UUID:
    m = contract_metadata()
    jid = uuid.uuid4()
    with Session(engine) as s:
        s.add(
            m.Job(
                id=jid,
                workspace_id=seed.workspace_id,
                kind=m.JobKind.ESTIMATE_RESOURCES,
                resource=m.JobResource.GPU,
                max_attempts=1,
                dataset_version_id=seed.version_id,
                payload={
                    "cache_key": "k" * 64,
                    "policy_type": "act",
                    "gpu_name": None,
                    "batch_size": 8,
                    "mixed_precision": "no",
                    "image_shapes": [[3, 360, 640]],
                    "policy_config_hash": "h" * 64,
                    "lerobot_version": "0.7.1",
                    "dataset_version_id": str(seed.version_id),
                    "dataset_repo_id": "local/golden",
                    "argv": fake_args(steps=1000),
                },
            )
        )
        s.commit()
    return jid


def test_estimate_job_with_fake_trainer(engine: Engine, services: Services, tmp_path: Path, ws: Seed) -> None:
    jid = _estimate_job(engine, ws)
    w = GpuWorker(settings_for(services, tmp_path))
    w.register()
    assert w.step() is True
    with engine.connect() as conn:
        j = conn.execute(select(jobs).where(jobs.c.id == jid)).one()
        est = conn.execute(select(resource_estimates)).one()
    assert j.status == "succeeded", (j.error_code, j.error_message)
    assert est.cache_key == "k" * 64 and est.peak_vram_mb == int(1.5 * 1024) and est.sec_per_step == 0.011
    assert est.gpu_name == "Fake GPU" and j.result["gpu_id"] == "cuda0"


def test_serve_loop_claims_and_shuts_down(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed
) -> None:
    stale = tmp_path / "scratch" / "runs" / str(uuid.uuid4())
    stale.mkdir(parents=True)
    rid = queue_run(engine, ws, steps=40)
    w = GpuWorker(settings_for(services, tmp_path))
    t = threading.Thread(target=w.serve, daemon=True)
    t.start()
    wait_for(lambda: run_row(engine, rid).status == "succeeded", timeout=60)
    assert not stale.exists()  # boot cleanup of runs nobody holds
    w.shutdown.set()
    w.wake.set()
    t.join(timeout=30)
    assert not t.is_alive()
    with engine.connect() as conn:
        g = conn.execute(select(gpu_nodes)).one()
    assert g.status == "offline" and g.worker_id is None


def test_admin_draining_survives_restart_and_blocks_claims(
    engine: Engine, services: Services, tmp_path: Path, ws: Seed
) -> None:
    w = GpuWorker(settings_for(services, tmp_path))
    w.register()
    with engine.begin() as conn:
        conn.execute(text("UPDATE gpu_nodes SET status='draining'"))
    w.register()  # restart keeps the admin's choice
    rid = queue_run(engine, ws, steps=20)
    assert w.step() is False and run_row(engine, rid).status == "queued"


@pytest.mark.gpu
def test_nvml_on_cuda0(engine: Engine) -> None:
    nv = Nvml(0)
    info = nv.info()
    assert info is not None and info.total_vram_mb > 1000 and info.compute_capability.count(".") == 1
    s = nv.sample()
    assert s is not None and s.mem_total_mb == info.total_vram_mb
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO gpu_nodes (id, host, device_index, name, total_vram_mb, compute_capability, "
                "supports_bf16, supports_fast_fp16, status) "
                "VALUES ('cuda0', 'h', 0, 'g', 1, '8.6', true, true, 'online')"
            )
        )
    ts = TelemetrySampler(engine=engine, bus=None, nvml=nv, gpu_id="cuda0", interval_s=5)
    ts.tick()
    with engine.connect() as conn:
        n = conn.execute(select(gpu_telemetry)).all()
        hb = conn.execute(select(gpu_nodes.c.last_heartbeat_at)).scalar_one()
    assert len(n) == 1 and hb is not None and ts.peak_used_mb > 0
