"""Phase-5 residuals in the worker process: SEC-input-2 (/proc/<ppid>/environ) and N-2 (/metrics).

No database needed; the environ test runs real processes on this Linux host.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import textwrap
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pytest

from core import metrics
from core.hardening import is_secret_env_name, scrub_secret_env

WORKER_ROOT = Path(__file__).resolve().parents[2]
SECRET = "postgresql+psycopg://hibiscus:SECRETPW@postgres:5432/hibiscus"  # noqa: S105 - fake

# The parent mimics the GPU worker: optionally prctl(PR_SET_DUMPABLE, 0), then spawn a child the way
# RunAttempt._spawn starts lerobot-train (allow-listed env, new session, stdin closed, pipes). The
# child tries to read the parent's exec-time environment.
_PARENT = textwrap.dedent(
    """
    import json, subprocess, sys
    sys.path.insert(0, sys.argv[2])
    from core.child_env import child_env
    from core.hardening import is_dumpable, set_non_dumpable
    if sys.argv[1] == "1":
        assert set_non_dumpable() and is_dumpable() is False
    child = '''
    import json, os
    try:
        data = open(f"/proc/{os.getppid()}/environ", "rb").read()
        print(json.dumps({"read": True, "leak": b"SECRETPW" in data}))
    except OSError as e:
        print(json.dumps({"read": False, "errno": e.errno}))
    '''
    p = subprocess.Popen(
        [sys.executable, "-I", "-c", child],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        env=child_env(), start_new_session=True,
    )
    out, _ = p.communicate(timeout=60)
    print(out.decode().strip().splitlines()[-1])
    """
)


def _run_parent(tmp_path: Path, harden: bool) -> dict[str, object]:
    script = tmp_path / "parent.py"
    script.write_text(_PARENT)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "AMENT_PREFIX_PATH")}
    env["HIBISCUS_DATABASE_URL"] = SECRET
    r = subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, "-I", str(script), "1" if harden else "0", str(WORKER_ROOT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert r.returncode == 0, r.stderr[-3000:]
    data = json.loads(r.stdout.strip().splitlines()[-1])
    assert isinstance(data, dict)
    return data


needs_linux_non_root = pytest.mark.skipif(
    not sys.platform.startswith("linux") or os.geteuid() == 0,
    reason="needs Linux /proc and a non-root uid (root bypasses the dumpable check)",
)


@needs_linux_non_root
def test_child_can_read_parent_environ_without_hardening(tmp_path: Path) -> None:
    """Control: this is the phase-5 N3 leak (same uid, dumpable parent)."""
    assert _run_parent(tmp_path, harden=False) == {"read": True, "leak": True}


@needs_linux_non_root
def test_non_dumpable_parent_environ_is_eacces_for_child(tmp_path: Path) -> None:
    import errno

    assert _run_parent(tmp_path, harden=True) == {"read": False, "errno": errno.EACCES}


def test_worker_mains_harden_before_spawning() -> None:
    """Both process entrypoints call the hardening (source check; main() runs forever)."""
    for rel in ("train/worker.py", "validate/runner.py"):
        src = (WORKER_ROOT / rel).read_text()
        main = src[src.index("def main(") :]
        assert "set_non_dumpable()" in main and "scrub_secret_env()" in main, rel
        assert main.index("set_non_dumpable()") < main.index("scrub_secret_env()"), rel
        assert "start_metrics_server(" in main, rel


def test_scrub_secret_env_removes_secrets_only() -> None:
    env = {
        "HIBISCUS_DATABASE_URL": SECRET,
        "HIBISCUS_REDIS_URL": "redis://:pw@redis:6379/0",
        "HIBISCUS_S3_SECRET_KEY": "s",
        "HIBISCUS_S3_ACCESS_KEY": "a",
        "HIBISCUS_DATA_KEY": "k",
        "HF_TOKEN": "hf_x",
        "AWS_SESSION_TOKEN": "t",
        "HIBISCUS_GPU_INDEX": "1",
        "HIBISCUS_LOG_LEVEL": "INFO",
        "HIBISCUS_WORKER_HEARTBEAT_FILE": "/tmp/x",  # noqa: S108 - path only
        "PATH": "/usr/bin",
    }
    removed = scrub_secret_env(env)
    assert set(removed) == {
        "HIBISCUS_DATABASE_URL",
        "HIBISCUS_REDIS_URL",
        "HIBISCUS_S3_SECRET_KEY",
        "HIBISCUS_S3_ACCESS_KEY",
        "HIBISCUS_DATA_KEY",
        "HF_TOKEN",
        "AWS_SESSION_TOKEN",
    }
    assert set(env) == {"HIBISCUS_GPU_INDEX", "HIBISCUS_LOG_LEVEL", "HIBISCUS_WORKER_HEARTBEAT_FILE", "PATH"}
    assert not is_secret_env_name("HIBISCUS_METRICS_PORT")


def test_settings_survive_scrub(monkeypatch: pytest.MonkeyPatch) -> None:
    """The settings object keeps the values after the variables are gone from the environment."""
    from core.settings import WorkerSettings

    monkeypatch.setenv("HIBISCUS_DATABASE_URL", SECRET)
    monkeypatch.setenv("HIBISCUS_S3_SECRET_KEY", "sk")
    s = WorkerSettings()
    # scrub a private copy so the rest of the test session keeps its environment
    monkeypatch.setattr(os, "environ", dict(os.environ))
    assert {"HIBISCUS_DATABASE_URL", "HIBISCUS_S3_SECRET_KEY"} <= set(scrub_secret_env())
    assert "HIBISCUS_DATABASE_URL" not in os.environ and "HIBISCUS_S3_SECRET_KEY" not in os.environ
    assert s.database_url == SECRET and s.s3_secret_key == "sk"  # noqa: S105


# ---------------------------------------------------------------------------------------------
# N-2: /metrics
# ---------------------------------------------------------------------------------------------
@dataclass
class _FakeSample:
    util_pct: float = 87.0
    mem_used_mb: int = 1024
    mem_total_mb: int = 12288
    temperature_c: float = 61.0
    power_w: float = 120.5


class _FakeNvml:
    available = True

    def sample(self) -> _FakeSample:
        return _FakeSample()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_metrics_server_exposes_worker_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.settings import WorkerSettings

    monkeypatch.setenv("HIBISCUS_METRICS_PORT", "9200")
    assert WorkerSettings().metrics_port == 9200
    assert metrics.start_metrics_server(0) is None  # 0 disables
    port = _free_port()
    server = metrics.start_metrics_server(port, addr="127.0.0.1")
    assert server is not None
    try:
        metrics.set_info("gpu", "cuda7", "9.9.9")
        metrics.register_gpu(_FakeNvml(), "cuda7")
        metrics.job_claimed("export_model")
        metrics.job_ended("export_model", "succeeded")
        metrics.job_claimed(metrics.TRAIN_RUN_KIND)
        metrics.job_ended(metrics.TRAIN_RUN_KIND, "lease_lost")
        metrics.job_ended("validate_dataset", "cancelled")  # neither succeeded nor failed
        metrics.lease_heartbeat(True)
        metrics.run_started(10, 300)
        metrics.run_step(42)
        body = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5).read().decode()
    finally:
        server.shutdown()
        metrics.run_ended()
    for line in (
        'hibiscus_worker_info{gpu_id="cuda7",version="9.9.9",worker_kind="gpu"} 1.0',
        'hibiscus_worker_jobs_claimed_total{kind="export_model"}',
        'hibiscus_worker_jobs_succeeded_total{kind="export_model"}',
        'hibiscus_worker_jobs_failed_total{kind="train_run"}',
        'hibiscus_worker_lease_heartbeats_total{result="ok"}',
        'hibiscus_worker_lease_heartbeats_total{result="lost"}',
        "hibiscus_worker_run_active 1.0",
        "hibiscus_worker_run_current_step 42.0",
        "hibiscus_worker_run_total_steps 300.0",
        'hibiscus_worker_gpu_utilization_percent{gpu_id="cuda7"} 87.0',
        'hibiscus_worker_gpu_memory_used_bytes{gpu_id="cuda7"} 1.073741824e+09',
        'hibiscus_worker_gpu_temperature_celsius{gpu_id="cuda7"} 61.0',
        'hibiscus_worker_gpu_power_watts{gpu_id="cuda7"} 120.5',
        "process_resident_memory_bytes",
    ):
        assert line in body, line
    assert 'hibiscus_worker_jobs_succeeded_total{kind="validate_dataset"}' not in body


def test_metrics_server_busy_port_does_not_raise() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        assert metrics.start_metrics_server(int(s.getsockname()[1]), addr="127.0.0.1") is None


def test_gpu_collector_absent_without_nvml() -> None:
    class _NoNvml:
        available = False

        def sample(self) -> None:
            return None

    assert list(metrics.GpuCollector(_NoNvml(), "cuda0").collect()) == []
