"""End-to-end smoke test of the real compose stack (dev overlay) with stand-in API/SPA code.

Builds the production api + web images from deploy/docker/*.Dockerfile against the stubs in
tests/stubs (the real backend/frontend are other agents' work), starts every infrastructure
service, waits for all healthchecks, then verifies proxy routing, body limits, SSE streaming,
the CF-Connecting-IP trust rule, MinIO bootstrap, Prometheus scraping + rules + dashboard
queries, Loki ingestion via Alloy, Grafana provisioning, Redis auth and a backup run.

Isolation: unique compose project name, random loopback host ports and random subnets, so it
never collides with the production stack (127.0.0.1:18000) or other agents. Everything is torn
down (`down -v`) at the end. GPU workers are not started (dev overlay puts them behind the
`gpu` profile) and worker-cpu is skipped because its code belongs to A3/A4.
"""

from __future__ import annotations

import json
import os
import random
import secrets
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from dockerutil import docker_available, run, suffix

pytestmark = [
    pytest.mark.docker,
    pytest.mark.slow,
    pytest.mark.skipif(not docker_available(), reason="docker unavailable"),
]

DEPLOY = Path(__file__).resolve().parent.parent
REPO = DEPLOY.parent
STUBS = Path(__file__).resolve().parent / "stubs"
SERVICES = [
    "postgres",
    "redis",
    "minio",
    "minio-init",
    "migrate",
    "api",
    "proxy",
    "prometheus",
    "postgres-exporter",
    "loki",
    "alloy",
    "grafana",
    "backup",
]

OVERRIDE = """
services:
  proxy:
    ports: !override ["127.0.0.1::8080"]
  grafana:
    ports: !override ["127.0.0.1::3000"]
  prometheus:
    ports: !override ["127.0.0.1::9090"]
  minio:
    ports: !override ["127.0.0.1::9000"]
  postgres:
    ports: !reset []
  redis:
    ports: !reset []
  loki:
    networks: [obs, ops]
    ports: ["127.0.0.1::3100"]
  migrate:
    command: ["python", "-c", "print('stub migrate: the stub API has no migrations')"]
"""


@dataclass
class Stack:
    project: str
    compose: list[str]
    env: dict[str, str]
    backups: Path

    def dc(self, *args: str, check: bool = True, timeout: float = 900) -> str:
        return run([*self.compose, *args], check=check, timeout=timeout)

    def url(self, service: str, port: int) -> str:
        out = self.dc("port", service, str(port)).strip()
        host, _, p = out.rpartition(":")
        assert host == "127.0.0.1", out
        return f"http://127.0.0.1:{p}"


def _subnet_octets() -> tuple[int, int]:
    a = random.randint(100, 250)  # noqa: S311 (not crypto)
    return a, random.randint(0, 250)  # noqa: S311


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    root = tmp_path_factory.mktemp("repo")
    shutil.copytree(
        DEPLOY,
        root / "deploy",
        ignore=shutil.ignore_patterns(
            ".venv", "backups", "data", "node_modules", "tests", ".env", "__pycache__"
        ),
    )
    shutil.copytree(REPO / "api", root / "api")
    shutil.copytree(STUBS / "backend", root / "backend")
    shutil.copytree(STUBS / "frontend", root / "frontend")
    (root / "deploy" / "compose.test.yml").write_text(OVERRIDE)
    backups = tmp_path_factory.mktemp("backups")
    os.chmod(backups, 0o777)  # noqa: S103 (postgres uid in the backup container writes here)

    a, b = _subnet_octets()
    sfx = suffix()
    env = {
        "HIBISCUS_ENV": "test",
        "HIBISCUS_IMAGE_TAG": f"a8smoke-{sfx}",
        "HIBISCUS_BUILD_NETWORK": os.environ.get("HIBISCUS_BUILD_NETWORK", "default"),
        "POSTGRES_SUPERUSER_PASSWORD": secrets.token_hex(12),
        "HIBISCUS_DB_PASSWORD": secrets.token_hex(12),
        "HIBISCUS_DB_MONITOR_PASSWORD": secrets.token_hex(12),
        "HIBISCUS_REDIS_PASSWORD": secrets.token_hex(12),
        "MINIO_ROOT_PASSWORD": secrets.token_hex(12),
        "HIBISCUS_S3_SECRET_KEY": secrets.token_hex(12),
        "HIBISCUS_DATA_KEY": secrets.token_hex(16),
        # the stub API ignores these, but compose requires them (QC-e2e-01 / SEC-infra-2)
        "HIBISCUS_JWT_PRIVATE_KEY": "stub-not-a-key",
        "HIBISCUS_CURSOR_SECRET": secrets.token_hex(16),
        "HIBISCUS_BACKUP_PASSPHRASE": secrets.token_hex(16),
        "GRAFANA_ADMIN_PASSWORD": secrets.token_hex(12),
        "HIBISCUS_BACKUP_DIR": str(backups),
        "HIBISCUS_DEV_EDGE_SUBNET": f"10.{a}.{b}.0/24",
        "HIBISCUS_DEV_EDGE_GATEWAY": f"10.{a}.{b}.1",
        "HIBISCUS_DEV_APP_SUBNET": f"10.{a}.{b + 1}.0/24",
        "HIBISCUS_DEV_PROXY_APP_IP": f"10.{a}.{b + 1}.2",
        "HIBISCUS_DEV_API_APP_IP": f"10.{a}.{b + 1}.10",
    }
    env_file = root / "deploy" / ".env.test"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    project = f"hibiscus-a8smoke-{sfx}"
    d = root / "deploy"
    compose = [
        "docker",
        "compose",
        "-p",
        project,
        "--project-directory",
        str(d),
        "-f",
        str(d / "docker-compose.yml"),
        "-f",
        str(d / "compose.dev.yml"),
        "-f",
        str(d / "compose.test.yml"),
        "--env-file",
        str(env_file),
    ]
    # Build with the daemon's own BuildKit (docker driver): a docker-container buildx builder runs in
    # a bridge container and may lack DNS/egress on this host (install.md §2).
    os.environ.setdefault("BUILDX_BUILDER", "default")
    s = Stack(project=project, compose=compose, env=env, backups=backups)
    try:
        s.dc("build", "api", "proxy", timeout=1800)
        s.dc("up", "-d", "--wait", "--wait-timeout", "240", *SERVICES, timeout=600)
        yield s
    finally:
        logs = subprocess.run(
            [*compose, "logs", "--no-color", "--tail", "40"], capture_output=True, text=True
        )
        if os.environ.get("A8_SMOKE_LOGS"):
            print(logs.stdout[-20000:])
        subprocess.run([*compose, "down", "-v", "--remove-orphans", "--rmi", "local"], capture_output=True)
        subprocess.run(
            [
                "docker",
                "image",
                "rm",
                f"hibiscus/api:{env['HIBISCUS_IMAGE_TAG']}",
                f"hibiscus/web:{env['HIBISCUS_IMAGE_TAG']}",
            ],
            capture_output=True,
        )


def http(
    method: str,
    url: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30,
) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (loopback test URL)
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, {k.lower(): v for k, v in err.headers.items()}, err.read()


def jget(url: str, headers: dict[str, str] | None = None) -> Any:
    status, _, body = http("GET", url, headers=headers)
    assert status == 200, (url, status, body[:500])
    return json.loads(body)


def test_every_service_healthy_and_loopback_only(stack: Stack) -> None:
    rows = [json.loads(line) for line in stack.dc("ps", "--format", "json").splitlines() if line.strip()]
    by_name = {r["Service"]: r for r in rows}
    for svc in (
        "postgres",
        "redis",
        "minio",
        "api",
        "proxy",
        "prometheus",
        "postgres-exporter",
        "grafana",
        "backup",
    ):
        assert by_name[svc]["Health"] == "healthy", (svc, by_name[svc])
    for svc in ("loki", "alloy"):
        assert by_name[svc]["State"] == "running", stack.dc("logs", "--tail", "30", svc, check=False)
    for r in rows:
        for pub in r.get("Publishers") or []:
            if pub.get("PublishedPort"):
                assert pub["URL"] in ("127.0.0.1", "::1"), r["Service"]
                assert pub["PublishedPort"] not in (8000, 18000)


def test_proxy_routes_spa_api_and_hides_internal(stack: Stack) -> None:
    base = stack.url("proxy", 8080)
    status, headers, body = http("GET", base + "/")
    assert status == 200 and b"hibiscus-spa-stub" in body
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["x-frame-options"] == "DENY"
    assert headers["cache-control"] == "no-cache"
    assert "server" not in headers
    status, _, body = http("GET", base + "/runs/42/metrics")  # SPA deep link -> index.html
    assert status == 200 and b"hibiscus-spa-stub" in body
    status, headers, _ = http("GET", base + "/assets/app-abc123.js")
    assert status == 200 and "immutable" in headers["cache-control"]
    status, _, body = http("GET", base + "/healthz")
    assert status == 200 and json.loads(body) == {"status": "ok"}
    for path in ("/metrics", "/readyz", "/metrics/x"):
        assert http("GET", base + path)[0] == 404, path
    status, _, body = http("GET", base + "/api/v1/stub/text")
    assert status == 200 and body == b"ok"


def raw_status(base: str, method: str, path: str, size: int) -> int:
    """Send `size` bytes and return the HTTP status, tolerating the server closing the socket
    early (Caddy answers 413 and stops reading once the limit is exceeded)."""
    parts = urllib.parse.urlsplit(base)
    assert parts.hostname and parts.port
    with socket.create_connection((parts.hostname, parts.port), timeout=60) as sock:
        sock.sendall(
            f"{method} {path} HTTP/1.1\r\nHost: x\r\nContent-Length: {size}\r\n"
            "Connection: close\r\n\r\n".encode()
        )
        chunk = b"x" * (1024 * 1024)
        sent = 0
        try:
            while sent < size:
                n = min(len(chunk), size - sent)
                sock.sendall(chunk[:n])
                sent += n
        except (BrokenPipeError, ConnectionResetError):
            pass
        data = b""
        try:
            while b"\r\n" not in data:
                more = sock.recv(4096)
                if not more:
                    break
                data += more
        except ConnectionResetError:
            pass
    assert data.startswith(b"HTTP/1.1 "), data[:200]
    return int(data.split(b" ", 2)[1])


def test_body_limits(stack: Stack) -> None:
    base = stack.url("proxy", 8080)
    assert raw_status(base, "POST", "/api/v1/stub/echo", 900 * 1024) == 200
    assert raw_status(base, "POST", "/api/v1/stub/echo", 2 * 1024 * 1024) == 413
    status, _, body = http(
        "PUT", base + "/api/v1/uploads/u1/parts/1", body=b"x" * (64 * 1024 * 1024), timeout=120
    )
    assert status == 200 and json.loads(body)["bytes"] == 64 * 1024 * 1024
    assert raw_status(base, "PUT", "/api/v1/uploads/u1/parts/2", 71 * 1024 * 1024) == 413
    # the large limit applies only to upload parts
    assert raw_status(base, "PUT", "/api/v1/uploads/u1", 2 * 1024 * 1024) == 413


def test_sse_is_streamed_unbuffered(stack: Stack) -> None:
    base = stack.url("proxy", 8080)
    host, port = urllib.parse.urlsplit(base).hostname, urllib.parse.urlsplit(base).port
    assert host and port
    with socket.create_connection((host, port), timeout=10) as sock:
        sock.sendall(b"GET /api/v1/stub/sse HTTP/1.1\r\nHost: x\r\nAccept: text/event-stream\r\n\r\n")
        start = time.monotonic()
        buf = b""
        while b"data: 0" not in buf:
            chunk = sock.recv(4096)
            assert chunk, "connection closed before the first event"
            buf += chunk
        first = time.monotonic() - start
    # the stub needs ~3 s to finish; the first event must arrive long before that
    assert first < 1.0, f"first SSE event took {first:.2f}s (buffered?)"
    assert b"text/event-stream" in buf


def test_cf_connecting_ip_trusted_only_from_edge_gateway(stack: Stack) -> None:
    base = stack.url("proxy", 8080)
    # Through the published loopback port (= how cloudflared connects): header is honoured.
    echo = jget(base + "/api/v1/stub/echo", headers={"CF-Connecting-IP": "203.0.113.7"})
    assert echo["client"] == "203.0.113.7", echo
    assert echo["x_forwarded_for"] == "203.0.113.7"
    assert echo["cf_connecting_ip"] == "203.0.113.7"
    # Without the header the client is the gateway (no spoofable default).
    echo = jget(base + "/api/v1/stub/echo")
    assert echo["client"] == stack.env["HIBISCUS_DEV_EDGE_GATEWAY"], echo
    # From another container on the edge network: spoofed header is ignored and overwritten.
    out = run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            f"{stack.project}_edge",
            "curlimages/curl:8.11.1",
            "-s",
            "-H",
            "CF-Connecting-IP: 198.51.100.66",
            "-H",
            "X-Forwarded-For: 198.51.100.66",
            "http://proxy:8080/api/v1/stub/echo",
        ]
    )
    echo = json.loads(out)
    assert echo["client"] != "198.51.100.66", echo
    assert echo["cf_connecting_ip"] == echo["client"]
    assert echo["client"].startswith(stack.env["HIBISCUS_DEV_EDGE_SUBNET"].rsplit(".", 2)[0])
    # Direct to the API from a non-proxy peer: uvicorn ignores X-Forwarded-For.
    out = run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            f"{stack.project}_app",
            "curlimages/curl:8.11.1",
            "-s",
            "-H",
            "X-Forwarded-For: 198.51.100.66",
            "http://api:8000/api/v1/stub/echo",
        ]
    )
    assert json.loads(out)["client"] != "198.51.100.66"


def test_api_is_not_reachable_from_edge_network(stack: Stack) -> None:
    res = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            f"{stack.project}_edge",
            "curlimages/curl:8.11.1",
            "-s",
            "-m",
            "5",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "http://api:8000/healthz",
        ],
        capture_output=True,
        text=True,
    )
    assert res.stdout.strip() in ("000", ""), res.stdout


def test_minio_buckets_versioning_and_app_user(stack: Stack) -> None:
    s3 = stack.url("minio", 9000)
    net = f"{stack.project}_data"
    mc = [
        "docker",
        "run",
        "--rm",
        "--network",
        net,
        "--entrypoint",
        "sh",
        "pgsty/mc:RELEASE.2026-11-12T00-00-00Z",
        "-c",
    ]
    app = f"http://hibiscus-app:{stack.env['HIBISCUS_S3_SECRET_KEY']}@minio:9000"
    root = f"http://hibiscus-root:{stack.env['MINIO_ROOT_PASSWORD']}@minio:9000"
    script = (
        f"export MC_HOST_app='{app}' MC_HOST_root='{root}'; set -e; "
        "mc version info root/hibiscus-datasets; mc version info root/hibiscus-artifacts; "
        "echo hello > /tmp/f; mc cp /tmp/f app/hibiscus-datasets/ws/ds/v1/f.txt; "
        "echo again > /tmp/f; mc cp /tmp/f app/hibiscus-datasets/ws/ds/v1/f.txt; "
        "mc ls --versions app/hibiscus-datasets/ws/ds/v1/f.txt | wc -l; "
        "if mc mb app/not-allowed 2>/dev/null; then echo MB_ALLOWED; else echo MB_DENIED; fi; "
        "mc ilm rule ls root/hibiscus-uploads"
    )
    out = run([*mc, script])
    assert out.count("versioning is enabled") == 2, out
    assert "\n2\n" in out, out  # two versions of the object
    assert "MB_DENIED" in out
    assert "expire-uploads" in out
    # anonymous access is denied
    assert http("GET", s3 + "/hibiscus-datasets/ws/ds/v1/f.txt")[0] == 403


def _prom(stack: Stack, query: str) -> list[Any]:
    base = stack.url("prometheus", 9090)
    data = jget(base + "/api/v1/query?" + urllib.parse.urlencode({"query": query}))
    assert data["status"] == "success", data
    result: list[Any] = data["data"]["result"]
    return result


def test_prometheus_scrapes_and_rules_load(stack: Stack) -> None:
    deadline = time.monotonic() + 90
    up: dict[str, str] = {}
    while time.monotonic() < deadline:
        up = {r["metric"]["job"]: r["value"][1] for r in _prom(stack, "up")}
        if all(up.get(j) == "1" for j in ("prometheus", "api", "postgres", "minio", "loki", "alloy")):
            break
        time.sleep(3)
    for job in ("prometheus", "api", "postgres", "minio", "loki", "alloy"):
        assert up.get(job) == "1", up
    assert up.get("gpu") == "0" or "gpu" not in up  # exporter not started in dev
    rules = jget(stack.url("prometheus", 9090) + "/api/v1/rules")["data"]["groups"]
    names = {r["name"] for g in rules for r in g["rules"]}
    assert {"HibiscusTargetDown", "HibiscusRunQueueStuck", "HibiscusGpuTemperatureHigh"} <= names
    assert all(r.get("health") != "err" for g in rules for r in g["rules"]), rules
    # postgres-exporter custom metrics exist before migrations? -> the functions error without tables,
    # but the exporter stays up; pg_up proves connectivity of the monitor role.
    assert _prom(stack, "pg_up")[0]["value"][1] == "1"


def test_dashboard_queries_parse(stack: Stack) -> None:
    exprs: list[str] = []
    for f in (DEPLOY / "observability/grafana/dashboards").glob("*.json"):
        for panel in json.loads(f.read_text())["panels"]:
            for t in panel.get("targets", []):
                if t.get("datasource", {}).get("type") == "prometheus":
                    exprs.append(t["expr"])
    assert len(exprs) > 15
    for e in exprs:
        _prom(stack, e)  # asserts status == success (valid PromQL)


def test_grafana_provisioned(stack: Stack) -> None:
    base = stack.url("grafana", 3000)
    import base64

    auth = base64.b64encode(f"admin:{stack.env['GRAFANA_ADMIN_PASSWORD']}".encode()).decode()
    hdr = {"Authorization": f"Basic {auth}"}
    dashboards = jget(base + "/api/search?tag=hibiscus", headers=hdr)
    assert {d["uid"] for d in dashboards} == {"hibiscus-overview", "hibiscus-logs"}
    ds = jget(base + "/api/datasources", headers=hdr)
    assert {d["uid"] for d in ds} == {"prometheus", "loki"}
    health = jget(base + "/api/datasources/uid/prometheus/health", headers=hdr)
    assert health["status"] == "OK", health
    assert http("GET", base + "/api/search")[0] == 401  # no anonymous access


def test_loki_receives_container_logs(stack: Stack) -> None:
    base = stack.url("loki", 3100)
    # generate a recognisable API log line
    marker = "a8-marker-" + suffix()
    http("GET", stack.url("proxy", 8080) + "/api/v1/stub/text?" + marker)
    deadline = time.monotonic() + 120
    found: list[Any] = []
    while time.monotonic() < deadline:
        q = urllib.parse.urlencode(
            {
                "query": f'{{project="{stack.project}", service="api"}} |= "{marker}"',
                "limit": "10",
                "start": str(int((time.time() - 600) * 1e9)),
            }
        )
        data = jget(base + "/loki/api/v1/query_range?" + q)
        found = data["data"]["result"]
        if found:
            break
        time.sleep(3)
    assert found, "no api log line with the marker reached Loki"
    assert found[0]["stream"]["service"] == "api"


def test_redis_requires_password(stack: Stack) -> None:
    ok = stack.dc("exec", "-T", "redis", "redis-cli", "ping").strip()
    assert ok == "PONG"
    denied = stack.dc(
        "exec", "-T", "-e", "REDISCLI_AUTH=", "redis", "redis-cli", "--no-auth-warning", "ping", check=False
    ).strip()
    assert "NOAUTH" in denied


def test_backup_service_runs_pg_backup(stack: Stack) -> None:
    stack.dc("exec", "-T", "backup", "bash", "/backup/pg-backup.sh")
    dumps = list(stack.backups.glob("hibiscus-hibiscus-*.dump.gpg"))
    assert len(dumps) == 1 and dumps[0].stat().st_size > 0
    assert (stack.backups / "last-success").exists()
