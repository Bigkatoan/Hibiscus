"""Static validation of every config file with the real tool that consumes it (pinned images)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

import gen_dashboards
from dockerutil import docker_available

DEPLOY = Path(__file__).resolve().parent.parent
needs_docker = pytest.mark.skipif(not docker_available(), reason="docker unavailable")


def docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "run", "--rm", "--network", "none", *args], capture_output=True, text=True
    )


def test_dashboards_are_generated_from_source() -> None:
    assert gen_dashboards.main(["--check"]) == 0


def test_dashboard_panel_ids_unique_and_on_grid() -> None:
    for name, text in gen_dashboards.render().items():
        import json

        panels = json.loads(text)["panels"]
        ids = [p["id"] for p in panels]
        assert len(ids) == len(set(ids)), name
        for p in panels:
            g = p["gridPos"]
            assert 0 <= g["x"] and g["x"] + g["w"] <= 24, (name, p["title"])


@needs_docker
def test_prometheus_config_and_rules() -> None:
    res = docker(
        "-v",
        f"{DEPLOY / 'observability/prometheus'}:/etc/prometheus:ro",
        "--entrypoint",
        "promtool",
        "prom/prometheus:v3.16.0",
        "check",
        "config",
        "/etc/prometheus/prometheus.yml",
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "SUCCESS" in res.stdout + res.stderr


@needs_docker
def test_loki_config() -> None:
    res = docker(
        "-v",
        f"{DEPLOY / 'observability/loki/loki.yml'}:/etc/loki/loki.yml:ro",
        "grafana/loki:3.7.10",
        "-config.file=/etc/loki/loki.yml",
        "-verify-config",
    )
    assert res.returncode == 0, res.stdout + res.stderr


@needs_docker
def test_alloy_config_syntax() -> None:
    res = docker(
        "-v",
        f"{DEPLOY / 'observability/alloy/config.alloy'}:/c.alloy:ro",
        "grafana/alloy:v1.22.0",
        "fmt",
        "/c.alloy",
    )
    assert res.returncode == 0, res.stderr


def test_csp_forbids_eval() -> None:
    """QC-e2e-04: the fix for the wizard crash is in the SPA (no runtime codegen), not a looser CSP."""
    text = (DEPLOY / "caddy/Caddyfile").read_text()
    policies = re.findall(r'Content-Security-Policy "([^"]+)"', text)
    assert policies, "the SPA must be served with a CSP"
    for policy in policies:
        directives = {d.split()[0]: d.split()[1:] for d in (x.strip() for x in policy.split(";")) if d}
        script_src = directives.get("script-src", directives.get("default-src", []))
        assert "'unsafe-eval'" not in script_src, policy
        assert "'wasm-unsafe-eval'" not in script_src, policy
        assert "'unsafe-inline'" not in script_src, policy
        assert directives.get("object-src") == ["'none'"], policy
        assert directives.get("frame-ancestors") == ["'none'"], policy
    assert "'unsafe-eval'" not in text and "'wasm-unsafe-eval'" not in text


@needs_docker
def test_caddyfile_valid_and_formatted() -> None:
    mount = f"{DEPLOY / 'caddy/Caddyfile'}:/etc/caddy/Caddyfile:ro"
    res = docker(
        "-v",
        mount,
        "caddy:2.11.9-alpine@sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0",
        "caddy",
        "validate",
        "--config",
        "/etc/caddy/Caddyfile",
        "--adapter",
        "caddyfile",
    )
    assert res.returncode == 0, res.stderr
    assert "not formatted" not in res.stderr


@needs_docker
def test_shell_scripts_pass_shellcheck() -> None:
    scripts = sorted(
        str(p.relative_to(DEPLOY))
        for p in DEPLOY.rglob("*.sh")
        if not {"node_modules", ".venv"} & set(p.parts)
    )
    assert len(scripts) >= 9
    res = docker("-v", f"{DEPLOY}:/mnt:ro", "-w", "/mnt", "koalaman/shellcheck:v0.10.0", "-x", *scripts)
    assert res.returncode == 0, res.stdout
