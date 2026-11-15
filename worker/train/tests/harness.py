"""Shared helpers for worker integration tests (real PG/Redis/MinIO, fake or real lerobot-train)."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, select, text

from core.events import Outbox, transition
from core.s3 import ObjectStore
from core.settings import WorkerSettings
from core.tables import run_events, runs
from core.testing import Seed, Services, insert_run, seed_basic
from train.dataset_cache import content_hash
from train.worker import GpuWorker

FAKE = Path(__file__).parent / "fixtures" / "fake_lerobot_train.py"


def settings_for(services: Services, tmp: Path, **over: Any) -> WorkerSettings:
    base: dict[str, Any] = {
        "database_url": services.pg_url,
        "redis_url": services.redis_url,
        "s3_endpoint_url": services.s3_endpoint,
        "s3_access_key": services.s3_access_key,
        "s3_secret_key": services.s3_secret_key,
        "scratch_dir": tmp / "scratch",
        "cache_dir": tmp / "cache",
        "lerobot_train_bin": str(FAKE),
        "disable_nvml": True,
        "heartbeat_interval_s": 0.5,
        "poll_interval_s": 0.2,
        "log_upload_interval_s": 1.0,
        "kill_grace_s": 5.0,
        "checkpoint_complete_timeout_s": 20.0,
        "s3_max_retries": 2,
        # SEC-input-2: the child env is an allow-list; the fake lerobot-train reads FAKE_* knobs.
        "child_env_passthrough": ["FAKE_"],
    }
    base.update(over)
    return WorkerSettings(**base)


def store_for(services: Services) -> ObjectStore:
    return ObjectStore(
        endpoint_url=services.s3_endpoint,
        access_key=services.s3_access_key,
        secret_key=services.s3_secret_key,
        max_retries=2,
    )


def upload_dataset(services: Services, engine: Engine, src: Path | None, tmp: Path, **seed_kw: Any) -> Seed:
    """Upload ``src`` (a LeRobot dataset dir) or a tiny stand-in to MinIO and seed a READY version."""
    if src is None:
        src = tmp / "tiny_ds"
        (src / "meta").mkdir(parents=True, exist_ok=True)
        (src / "meta" / "info.json").write_text('{"codebase_version": "v3.0", "total_episodes": 20}')
        (src / "data").mkdir(exist_ok=True)
        (src / "data" / "x.parquet").write_bytes(b"\x00" * 100)
    prefix = f"datasets/{uuid.uuid4()}"
    store_for(services).upload_dir(src, "hibiscus-datasets", prefix)
    return seed_basic(
        engine,
        storage_prefix=f"s3://hibiscus-datasets/{prefix}/",
        content_hash=content_hash(src),
        **seed_kw,
    )


def fake_args(steps: int = 60, log_freq: int = 10, save_freq: int = 20) -> list[str]:
    return [
        "lerobot-train",
        "--policy.type=act",
        "--dataset.repo_id=local/golden",
        "--dataset.root={{DATASET_ROOT}}",
        "--output_dir={{OUTPUT_DIR}}",
        f"--steps={steps}",
        f"--log_freq={log_freq}",
        f"--save_freq={save_freq}",
        "--num_workers=8",
        '--accelerator.mixed_precision="bf16"',
    ]


def queue_run(
    engine: Engine, seed: Seed, *, steps: int = 60, log_freq: int = 10, save_freq: int = 20, **kw: Any
) -> uuid.UUID:
    return insert_run(
        engine,
        seed,
        resolved_args=kw.pop("resolved_args", fake_args(steps, log_freq, save_freq)),
        total_steps=steps,
        config={"policy": {}, "train": {"steps": steps, "log_freq": log_freq, "save_freq": save_freq}},
        **kw,
    )


class WorkerThread:
    """Runs ``GpuWorker.step()`` once in a background thread."""

    def __init__(self, worker: GpuWorker) -> None:
        self.worker = worker
        self.result: list[bool] = []
        self.error: list[BaseException] = []
        self.t = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        try:
            self.result.append(self.worker.step())
        except BaseException as exc:  # surfaced by join()
            self.error.append(exc)

    def start(self) -> WorkerThread:
        self.worker.register()
        self.t.start()
        return self

    def join(self, timeout: float = 120) -> None:
        self.t.join(timeout)
        assert not self.t.is_alive(), "worker step did not finish"
        if self.error:
            raise self.error[0]


def run_row(engine: Engine, rid: uuid.UUID) -> Any:
    with engine.connect() as conn:
        return conn.execute(select(runs).where(runs.c.id == rid)).one()


def events(engine: Engine, rid: uuid.UUID, typ: str | None = None) -> list[Any]:
    stmt = select(run_events).where(run_events.c.run_id == rid)
    if typ:
        stmt = stmt.where(run_events.c.type == typ)
    with engine.connect() as conn:
        return list(conn.execute(stmt.order_by(run_events.c.seq)).all())


def wait_for(pred: Callable[[], bool], timeout: float = 60, every: float = 0.1) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return
        time.sleep(every)
    raise AssertionError("condition not met in time")


def api_transition(engine: Engine, rid: uuid.UUID, frm: list[str], to: str, **extra: Any) -> None:
    """What the API does for pause / cancel / resume (no lease guard)."""
    with engine.begin() as conn:
        assert transition(conn, rid, from_statuses=frm, to=to, outbox=Outbox(), reason="api", extra=extra)


def metric_steps(engine: Engine, rid: uuid.UUID, key: str = "loss") -> list[int]:
    with engine.connect() as conn:
        return [
            int(s)
            for s in conn.execute(
                text("SELECT step FROM run_metrics WHERE run_id=:r AND key=:k ORDER BY step"),
                {"r": rid, "k": key},
            ).scalars()
        ]
