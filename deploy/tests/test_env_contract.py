"""Compose <-> application settings contract (QC-e2e-01, -03, -09, -10).

Every ``HIBISCUS_*`` name a compose file hands to a container must be one that the process in that
container actually reads:

* api / migrate:  pydantic fields (+ aliases, ``_FILE`` secret variants) of
  ``backend/app/core/settings.py::Settings`` and ``backend/app/notifications/settings.py``, direct
  ``os.environ`` reads in ``backend/app``, and the names the api image CMD expands;
* worker-cuda0/1: ``worker/core/settings.py::WorkerSettings`` + direct reads in the GPU worker
  packages + the worker image CMD / healthcheck;
* worker-cpu:     ``worker/validate/settings.py`` (``_env(...)``) + direct reads in ``worker/validate``
  + the worker image CMD / healthcheck;
* infrastructure containers: the init / backup scripts and the Caddyfile they run.

A misspelt or renamed variable used to be ignored silently (``extra="ignore"``): S3 credentials,
GPU index, email and cookie settings never reached the apps. This test fails on any unknown name.
The names are read from the settings sources with ``ast`` (no backend/worker dependencies needed);
``test_settings_instantiate_from_rendered_env`` additionally builds the real ``Settings`` /
``WorkerSettings`` from the rendered compose environment, which also catches wrong *values*
(``HIBISCUS_ENV=production`` vs ``Literal["prod", "dev", "test"]``) and missing prod secrets.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

import check_compose
from dockerutil import docker_available

DEPLOY = Path(__file__).resolve().parent.parent
REPO = DEPLOY.parent
COMPOSE_FILES = (DEPLOY / "docker-compose.yml", DEPLOY / "compose.dev.yml")
ENV_EXAMPLE = DEPLOY / ".env.example"

# ---------------------------------------------------------------------------------------------
# What each program reads
# ---------------------------------------------------------------------------------------------
_DIRECT_READ_RE = re.compile(
    r"""(?:environ\.get|environ\.setdefault|getenv|_env)\(\s*["'](HIBISCUS_[A-Z0-9_]+)["']"""
    r"""|environ\[\s*["'](HIBISCUS_[A-Z0-9_]+)["']\s*\]"""
)
_SHELL_VAR_RE = re.compile(r"\$\{?(HIBISCUS_[A-Z0-9_]+)")
_CADDY_VAR_RE = re.compile(r"\{\$(HIBISCUS_[A-Z0-9_]+)|\{env\.(HIBISCUS_[A-Z0-9_]+)\}")


def _str_const(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _alias_names(call: ast.Call) -> set[str]:
    out: set[str] = set()
    for kw in call.keywords:
        if kw.arg not in ("alias", "validation_alias"):
            continue
        if (s := _str_const(kw.value)) is not None:
            out.add(s.upper())
        elif isinstance(kw.value, ast.Call):  # AliasChoices("A", "B")
            out |= {s.upper() for a in kw.value.args if (s := _str_const(a)) is not None}
    return out


def settings_env_names(path: Path, class_name: str) -> set[str]:
    """Env names of a pydantic ``BaseSettings`` class: prefix + field (case-insensitive) and aliases."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next((n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == class_name), None)
    assert cls is not None, f"{class_name} not found in {path}"
    prefix = ""
    fields: set[str] = set()
    aliases: set[str] = set()
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "model_config" for t in stmt.targets
        ):
            assert isinstance(stmt.value, ast.Call), path
            for kw in stmt.value.keywords:
                if kw.arg == "env_prefix":
                    prefix = _str_const(kw.value) or ""
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            fields.add(stmt.target.id)
            if isinstance(stmt.value, ast.Call):
                aliases |= _alias_names(stmt.value)
    return {f"{prefix}{f}".upper() for f in fields} | aliases


def file_secret_names(path: Path) -> set[str]:
    """``HIBISCUS_<NAME>_FILE`` variants accepted by ``_load_file_secrets`` (backend)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "_FILE_SECRETS" for t in node.targets)
            and isinstance(node.value, ast.Tuple)
        ):
            return {f"HIBISCUS_{s}_FILE" for e in node.value.elts if (s := _str_const(e)) is not None}
    return set()


def direct_reads(roots: Iterable[Path]) -> set[str]:
    out: set[str] = set()
    for root in roots:
        for py in root.rglob("*.py"):
            if "tests" in py.relative_to(root).parts:
                continue
            for a, b in _DIRECT_READ_RE.findall(py.read_text(encoding="utf-8")):
                out.add(a or b)
    return out


def dockerfile_runtime_reads(path: Path) -> set[str]:
    """Names the image's CMD / ENTRYPOINT / HEALTHCHECK expand at run time."""
    text = path.read_text(encoding="utf-8")
    out: set[str] = set()
    for line in re.findall(r"^\s*(?:CMD|ENTRYPOINT|HEALTHCHECK).*$", text, re.M):
        out |= set(_SHELL_VAR_RE.findall(line))
    return out


def text_reads(paths: Iterable[Path]) -> set[str]:
    out: set[str] = set()
    for p in paths:
        text = p.read_text(encoding="utf-8")
        out |= set(_SHELL_VAR_RE.findall(text))
        for a, b in _CADDY_VAR_RE.findall(text):
            out.add(a or b)
    return out


BACKEND_SETTINGS = REPO / "backend" / "app" / "core" / "settings.py"
WORKER_SETTINGS = REPO / "worker" / "core" / "settings.py"
VALIDATE_SETTINGS = REPO / "worker" / "validate" / "settings.py"


def readers() -> dict[str, set[str]]:
    backend = (
        settings_env_names(BACKEND_SETTINGS, "Settings")
        | settings_env_names(
            REPO / "backend" / "app" / "notifications" / "settings.py", "NotificationSettings"
        )
        | settings_env_names(REPO / "backend" / "app" / "runs" / "settings.py", "RunsSettings")
        | file_secret_names(BACKEND_SETTINGS)
        | direct_reads([REPO / "backend" / "app"])
        | dockerfile_runtime_reads(DEPLOY / "docker" / "api.Dockerfile")
    )
    worker_image = dockerfile_runtime_reads(DEPLOY / "docker" / "worker.Dockerfile") | text_reads(
        [DEPLOY / "docker" / "worker-healthcheck.sh"]
    )
    w = REPO / "worker"
    gpu = (
        settings_env_names(WORKER_SETTINGS, "WorkerSettings")
        | direct_reads([w / "core", w / "train", w / "export", w / "eval"])
        | worker_image
    )
    cpu = direct_reads([w / "validate"]) | worker_image
    return {
        "api": backend,
        "migrate": backend,
        "worker-cuda0": gpu,
        "worker-cuda1": gpu,
        "worker-cpu": cpu,
        "postgres": text_reads(sorted((DEPLOY / "postgres" / "initdb").glob("*"))),
        "minio-init": text_reads(sorted((DEPLOY / "minio").glob("*.sh"))),
        "proxy": text_reads([DEPLOY / "caddy" / "Caddyfile"]),
        "backup": text_reads(sorted((DEPLOY / "backup").glob("*.sh"))),
    }


# ---------------------------------------------------------------------------------------------
# What compose hands to each container
# ---------------------------------------------------------------------------------------------
class _ComposeLoader(yaml.SafeLoader):
    pass


def _tagged(loader: yaml.SafeLoader, node: yaml.Node) -> Any:
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)  # type: ignore[arg-type]


for _tag in ("!override", "!reset"):
    _ComposeLoader.add_constructor(_tag, _tagged)


def _env_keys(env: Any) -> set[str]:
    if isinstance(env, Mapping):
        return {str(k) for k in env}
    if isinstance(env, list):
        return {str(e).split("=", 1)[0] for e in env}
    return set()


def compose_service_env(files: Iterable[Path] = COMPOSE_FILES) -> dict[str, set[str]]:
    """``{service: env names}`` over all compose files (YAML anchors / ``<<`` merges resolved)."""
    out: dict[str, set[str]] = {}
    for f in files:
        doc = yaml.load(f.read_text(encoding="utf-8"), Loader=_ComposeLoader)  # noqa: S506 (SafeLoader subclass)
        for name, svc in (doc.get("services") or {}).items():
            out.setdefault(name, set()).update(_env_keys((svc or {}).get("environment")))
    return out


def unknown_names(service_env: Mapping[str, set[str]], read: Mapping[str, set[str]]) -> list[str]:
    problems = []
    for service, names in sorted(service_env.items()):
        for name in sorted(n for n in names if n.startswith("HIBISCUS_")):
            if service not in read:
                problems.append(f"{service}: {name} (no known reader for this service)")
            elif name not in read[service]:
                problems.append(f"{service}: {name} is not read by the program in this container")
    return problems


def env_example() -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        out[key] = value
    return out


def compose_interpolations(path: Path) -> set[str]:
    return set(re.findall(r"\$\{([A-Z0-9_]+)", path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------------------------
def test_ast_reader_sees_known_fields() -> None:
    """Guard the parser itself: a broken AST walk would make every name 'unknown' or vacuous."""
    r = readers()
    assert {
        "HIBISCUS_ENV",
        "HIBISCUS_S3_ACCESS_KEY",
        "HIBISCUS_JWT_PRIVATE_KEY",
        "HIBISCUS_COOKIE_SECURE",
    } <= r["api"]
    assert {"HIBISCUS_JWT_PRIVATE_KEY_FILE", "HIBISCUS_NOTIFY_DISPATCHER_ENABLED"} <= r["api"]
    assert {"HIBISCUS_API_APP", "HIBISCUS_TRUSTED_PROXY_IPS"} <= r["api"]  # image CMD
    assert {"HIBISCUS_GPU_INDEX", "HIBISCUS_NVML_INDEX", "HIBISCUS_S3_SECRET_KEY"} <= r["worker-cuda1"]
    assert {"HIBISCUS_S3_ACCESS_KEY", "HIBISCUS_DATABASE_URL", "HIBISCUS_WORKER_MODULE"} <= r["worker-cpu"]
    assert "HIBISCUS_S3_ACCESS_KEY_ID" not in r["api"] | r["worker-cuda0"] | r["worker-cpu"]


def test_every_compose_env_name_is_read_by_its_container() -> None:
    assert unknown_names(compose_service_env(), readers()) == []


def test_e2e_overlay_env_names_are_read_too() -> None:
    """The golden-journey overlay must not reintroduce ignored names either."""
    overlay = REPO / "tests" / "e2e" / "golden_journey" / "compose.e2e.yml"
    if not overlay.exists():
        pytest.skip("e2e overlay not present")
    assert unknown_names(compose_service_env([overlay]), readers()) == []


@pytest.mark.parametrize(
    ("service", "name"),
    [
        ("api", "HIBISCUS_S3_ACCESS_KEY_ID"),  # QC-e2e-03
        ("api", "HIBISCUS_EMAIL_CF_WORKER_URL"),  # QC-e2e-10
        ("api", "HIBISCUS_SESSION_COOKIE_SECURE"),
        ("api", "HIBISCUS_LOG_FORMAT"),
        ("worker-cuda1", "HIBISCUS_GPU_FORCE_FP32"),
        ("worker-cpu", "HIBISCUS_WORKER_JOB_KINDS"),
        ("worker-cpu", "HIBISCUS_LOG_LEVEL"),  # the validate loop has a fixed log level
    ],
)
def test_names_that_were_silently_ignored_are_rejected(service: str, name: str) -> None:
    problems = unknown_names({service: {name}}, readers())
    assert problems and name in problems[0]


def test_secrets_go_only_where_they_are_used() -> None:
    env = compose_service_env()
    for svc in ("api", "migrate"):
        assert {"HIBISCUS_JWT_PRIVATE_KEY", "HIBISCUS_CURSOR_SECRET", "HIBISCUS_DATA_KEY"} <= env[svc], svc
    for svc in ("worker-cuda0", "worker-cuda1", "worker-cpu"):
        assert not {"HIBISCUS_JWT_PRIVATE_KEY", "HIBISCUS_CURSOR_SECRET"} & env[svc], svc
    for svc in ("worker-cuda0", "worker-cuda1"):  # lerobot-train children must not inherit it
        assert "HIBISCUS_DATA_KEY" not in env[svc], svc


def test_env_example_lists_every_compose_variable_and_nothing_stale() -> None:
    example = env_example()
    base = compose_interpolations(DEPLOY / "docker-compose.yml")
    dev = compose_interpolations(DEPLOY / "compose.dev.yml")
    # image overrides (*_IMAGE) are deliberately undocumented knobs; dev-only names start HIBISCUS_DEV_
    missing = sorted(v for v in base - set(example) if not v.endswith("_IMAGE"))
    assert missing == [], f"used by docker-compose.yml but missing from .env.example: {missing}"
    stale = sorted(set(example) - base - dev)
    assert stale == [], f".env.example variables nothing consumes: {stale}"


def test_env_example_values_match_settings_vocabulary() -> None:
    """QC-e2e-01: Settings.env is Literal["prod", "dev", "test"]."""
    tree = ast.parse(BACKEND_SETTINGS.read_text(encoding="utf-8"))
    allowed: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "env"
            and isinstance(node.annotation, ast.Subscript)
        ):
            sl = node.annotation.slice
            elts = sl.elts if isinstance(sl, ast.Tuple) else [sl]
            allowed = {s for e in elts if (s := _str_const(e)) is not None}
    assert allowed == {"prod", "dev", "test"}
    assert env_example()["HIBISCUS_ENV"] in allowed
    text = "\n".join(f.read_text(encoding="utf-8") for f in COMPOSE_FILES)
    for value in re.findall(r"HIBISCUS_ENV:\s*\$\{HIBISCUS_ENV:-([a-z]+)\}|HIBISCUS_ENV:\s*([a-z]+)", text):
        v = value[0] or value[1]
        assert v in allowed, v


def test_gen_secrets_covers_every_change_me() -> None:
    script = (DEPLOY / "scripts" / "gen-secrets.sh").read_text(encoding="utf-8")
    generated = set(re.findall(r"^([A-Z0-9_]+)=", script, re.M))
    change_me = {k for k, v in env_example().items() if "CHANGE_ME" in v}
    assert change_me <= generated, sorted(change_me - generated)
    assert "HIBISCUS_JWT_PRIVATE_KEY" in generated and "HIBISCUS_CURSOR_SECRET" in generated


# ---------------------------------------------------------------------------------------------
# Real settings classes, built from the rendered compose environment (needs docker + uv)
# ---------------------------------------------------------------------------------------------
def _gen_env_file(tmp_path: Path) -> Path:
    gen = subprocess.run(
        ["bash", str(DEPLOY / "scripts" / "gen-secrets.sh")], check=True, capture_output=True, text=True
    ).stdout
    generated = dict(line.split("=", 1) for line in gen.splitlines() if "=" in line)
    lines = []
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        key = raw.split("=", 1)[0]
        lines.append(f"{key}={generated[key]}" if key in generated and not raw.startswith("#") else raw)
    lines.append("HIBISCUS_EMAIL_PROVIDER=none")
    f = tmp_path / "env"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f


def _uv() -> list[str] | None:
    uv = shutil.which("uv")
    return [uv] if uv else None


_BACKEND_PROBE = """
import json
from app.core.settings import Settings
s = Settings()
names = set()
for name, f in Settings.model_fields.items():
    names.add(("HIBISCUS_" + name).upper())
    for a in (f.alias, f.validation_alias):
        if isinstance(a, str):
            names.add(a.upper())
print(json.dumps({"env": s.env, "s3": bool(s.s3_access_key and s.s3_secret_key),
                  "cookie_secure": s.cookie_secure, "names": sorted(names)}))
"""
_WORKER_PROBE = """
import json
from core.settings import WorkerSettings
s = WorkerSettings()
print(json.dumps({"gpu_id": s.gpu_id, "nvml": s.nvml_device_index,
                  "s3": bool(s.s3_access_key and s.s3_secret_key),
                  "names": sorted(("HIBISCUS_" + n).upper() for n in WorkerSettings.model_fields)}))
"""


def _probe(cmd: list[str], cwd: Path, env: Mapping[str, str]) -> dict[str, Any]:
    clean = {k: v for k, v in os.environ.items() if not k.startswith("HIBISCUS_")}
    clean.pop("PYTHONPATH", None)
    clean.pop("AMENT_PREFIX_PATH", None)
    out = subprocess.run(
        cmd, cwd=cwd, env={**clean, **env}, check=False, capture_output=True, text=True, timeout=600
    )
    assert out.returncode == 0, out.stderr[-3000:]
    data = json.loads(out.stdout.strip().splitlines()[-1])
    assert isinstance(data, dict)
    return data


def _env_of(rendered: Mapping[str, Any], service: str) -> dict[str, str]:
    env = rendered["services"][service].get("environment") or {}
    return {k: "" if v is None else str(v) for k, v in env.items()}


@pytest.mark.skipif(not docker_available() or _uv() is None, reason="needs docker compose + uv")
@pytest.mark.parametrize("mode", ["prod", "dev"])
def test_settings_instantiate_from_rendered_env(mode: check_compose.Mode, tmp_path: Path) -> None:
    uv = _uv()
    assert uv is not None
    rendered = check_compose.render(mode, _gen_env_file(tmp_path))
    for service in ("migrate", "api"):
        got = _probe(
            [*uv, "run", "--frozen", "--project", str(REPO / "backend"), "python", "-c", _BACKEND_PROBE],
            REPO / "backend",
            _env_of(rendered, service),
        )
        assert got["env"] == ("prod" if mode == "prod" else "dev"), (service, got)
        assert got["s3"], service
        if service == "api":
            assert got["cookie_secure"] is (mode == "prod")
        # the AST reader and pydantic agree on the field names
        assert set(got["names"]) <= readers()["api"]
    for service, gpu_id in (("worker-cuda0", "cuda0"), ("worker-cuda1", "cuda1")):
        got = _probe(
            [
                *uv,
                "run",
                "--isolated",
                "--no-project",
                "--with",
                "pydantic-settings>=2.6,<3",
                "python",
                "-c",
                _WORKER_PROBE,
            ],
            REPO / "worker",
            {**_env_of(rendered, service), "PYTHONPATH": str(REPO / "worker")},
        )
        assert (got["gpu_id"], got["nvml"], got["s3"]) == (gpu_id, 0, True), (service, got)
        assert set(got["names"]) <= readers()[service]
    cpu = _env_of(rendered, "worker-cpu")
    assert cpu["HIBISCUS_WORKER_MODULE"] == "validate"
    for name in re.findall(r'_env\("(HIBISCUS_[A-Z0-9_]+)"\)', VALIDATE_SETTINGS.read_text(encoding="utf-8")):
        assert cpu.get(name), f"worker-cpu: required {name} is not set"  # _env() without default


def test_worker_metrics_port_is_set_read_and_scraped() -> None:
    """Phase-5 N-2: Prometheus scraped worker-*:9108 but no worker listened there, so
    HibiscusWorkerDown fired permanently. Every worker container must get HIBISCUS_METRICS_PORT,
    its program must read it, and the scrape targets must use the same port."""
    doc = yaml.load((DEPLOY / "docker-compose.yml").read_text(encoding="utf-8"), Loader=_ComposeLoader)  # noqa: S506
    r = readers()
    prom_file = DEPLOY / "observability" / "prometheus" / "prometheus.yml"
    prom = yaml.safe_load(prom_file.read_text(encoding="utf-8"))
    job = next(j for j in prom["scrape_configs"] if j["job_name"] == "workers")
    targets = {t for sc in job["static_configs"] for t in sc["targets"]}
    for svc in ("worker-cuda0", "worker-cuda1", "worker-cpu"):
        env = doc["services"][svc]["environment"]
        assert "HIBISCUS_METRICS_PORT" in env, svc
        assert "HIBISCUS_METRICS_PORT" in r[svc], f"{svc} does not read HIBISCUS_METRICS_PORT"
        assert f"{svc}:{env['HIBISCUS_METRICS_PORT']}" in targets, (svc, targets)


def test_golden_journey_onnx_step_pins_python_312() -> None:
    """QC-e2e reverify: uv picked Python 3.15 for the ONNX self-test and onnxruntime has no
    cp315 wheel. The step must pin 3.12 explicitly."""
    run_sh = (REPO / "tests" / "e2e" / "golden_journey" / "run.sh").read_text(encoding="utf-8")
    onnx_cmds = [ln for ln in run_sh.splitlines() if "uv run" in ln and "onnx" in ln]
    assert onnx_cmds, "ONNX step not found in run.sh"
    assert all("--python 3.12" in ln for ln in onnx_cmds), onnx_cmds
