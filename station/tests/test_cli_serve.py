"""The real entry point on a real socket: ``hibiscus-station --mock --no-browser`` (spec §10 A1)."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_serve_mock_single_instance_and_url(tmp_path: Path) -> None:
    port = _free_port()
    home = tmp_path / "home"
    env = {**os.environ, "HF_LEROBOT_CALIBRATION": str(tmp_path / "cal")}
    cmd = [
        sys.executable,
        "-m",
        "hibiscus_station.cli",
        "--mock",
        "--no-browser",
        "--port",
        str(port),
        "--home",
        str(home),
    ]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)  # noqa: S603
    try:
        token_file = home / "token"
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if token_file.is_file():
                try:
                    r = httpx.get(
                        f"{base}/api/v1/status",
                        headers={"Authorization": f"Bearer {token_file.read_text().strip()}"},
                    )
                    if r.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
            time.sleep(0.3)
        token = token_file.read_text().strip()
        assert oct(token_file.stat().st_mode & 0o777) == "0o600"
        r = httpx.get(f"{base}/api/v1/status", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200 and r.json()["station"]["mock"] is True
        assert httpx.get(f"{base}/api/v1/status").status_code == 401
        assert httpx.get(f"{base}/api/v1/status", headers={"Host": f"evil.example:{port}"}).status_code == 403
        robots = httpx.get(f"{base}/api/v1/robots", headers={"Authorization": f"Bearer {token}"}).json()
        assert robots["robots"][0]["id"] == "demo_so101"
        # bootstrap link -> cookie session
        with httpx.Client(base_url=base) as c:
            r = c.get("/auth", params={"t": token})
            assert r.status_code in (200, 303)
            assert c.get("/api/v1/status").status_code == 200
        # a second launch prints the running instance's URL and exits 0
        out = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)  # noqa: S603
        assert out.returncode == 0 and "already running" in out.stdout and str(port) in out.stdout
        url = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "hibiscus_station.cli", "url", "--home", str(home)],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert f"127.0.0.1:{port}/auth?t={token}" in url.stdout
        assert json.loads((home / "station.pid").read_text())["port"] == port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
