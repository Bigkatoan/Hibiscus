"""SEC-auth-04 residual (docs/security/phase5-reverify.md N1/N8): invite tokens never reach the
Caddy access log, in any URI form, nor through the Referer header; the SPA is served with a
Referrer-Policy that never sends the path or query.

Runs the repo's Caddyfile in the pinned Caddy image with ``--network none`` and issues requests from
inside the container (busybox wget), then inspects the JSON access log on stdout.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

import pytest

from dockerutil import LABEL, docker_available, suffix

DEPLOY = Path(__file__).resolve().parent.parent
CADDY = "caddy:2.11.9-alpine@sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0"
TOKEN = "l5buQ2" + "Zx9_-aB3" * 5  # 46 url-safe chars

URIS = [
    f"/api/v1/auth/invites/{TOKEN}",
    f"/api/v1//auth/invites/{TOKEN}",
    f"/api/v1/auth//invites/{TOKEN}/accept",
    f"/api/v1/auth%2Finvites%2F{TOKEN}",
    f"/invite/{TOKEN}",
    f"//invite/{TOKEN}",
    f"/invite?token={TOKEN}",
    f"/invite?x=1&TOKEN={TOKEN}",
    f"/login?next=%2Finvite%3Ftoken%3D{TOKEN}",
    f"/login?next=%252Finvite%253Ftoken%253D{TOKEN}",
    f"/login?next=%2Finvite%2F{TOKEN}",
]


def _sh(*cmd: str, check: bool = True) -> str:
    res = subprocess.run(list(cmd), capture_output=True, text=True, timeout=120)
    if check and res.returncode != 0:
        raise RuntimeError(f"{cmd}: {res.stdout}\n{res.stderr}")
    return res.stdout + res.stderr


@pytest.mark.skipif(not docker_available(), reason="docker unavailable")
def test_caddy_access_log_never_contains_invite_tokens(tmp_path: Path) -> None:
    srv = tmp_path / "srv"
    srv.mkdir()
    (srv / "index.html").write_text("<!doctype html><title>spa</title>")
    srv.chmod(0o755)
    (srv / "index.html").chmod(0o644)
    name = f"hibiscus-caddy-redact-{suffix()}"
    _sh(
        "docker", "run", "-d", "--name", name, "--label", LABEL, "--network", "none",
        "-v", f"{DEPLOY / 'caddy/Caddyfile'}:/etc/caddy/Caddyfile:ro", "-v", f"{srv}:/srv:ro",
        CADDY, "caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile",
    )  # fmt: skip
    try:
        for _ in range(50):
            if "ok" in _sh(
                "docker", "exec", name, "wget", "-q", "-O-", "http://127.0.0.1:8081/livez", check=False
            ):
                break
            time.sleep(0.2)
        headers = ""
        for uri in URIS:
            headers += _sh(
                "docker", "exec", name, "wget", "-S", "-q", "-O", "/dev/null",
                "--header", f"Referer: https://robot.example.com/invite?token={TOKEN}",
                f"http://127.0.0.1:8080{uri}",
                check=False,
            )  # fmt: skip
        time.sleep(0.5)
        logs = _sh("docker", "logs", name)
    finally:
        _sh("docker", "rm", "-f", name, check=False)

    entries = []
    for line in logs.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("logger", "").startswith("http.log.access"):
            entries.append(obj)
    uris = [e["request"]["uri"] for e in entries]
    assert len(uris) >= len(URIS), logs
    assert TOKEN not in logs, [u for u in uris if TOKEN in u]
    assert all("REDACTED" in u for u in uris), uris
    assert not any("Referer" in e["request"].get("headers", {}) for e in entries)
    assert re.search(r"(?im)^\s*Referrer-Policy: strict-origin\s*$", headers), headers
