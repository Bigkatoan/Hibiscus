"""Compose exposure policy (CONTRACT_NOTES §3): the real files pass, and violations are caught."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

import check_compose
from dockerutil import docker_available

DEPLOY = Path(__file__).resolve().parent.parent
needs_docker = pytest.mark.skipif(not docker_available(), reason="docker unavailable")


@pytest.fixture(scope="module")
def prod() -> dict[str, Any]:
    if not docker_available():
        pytest.skip("docker unavailable")
    return check_compose.render("prod", DEPLOY / ".env.example")


@pytest.fixture(scope="module")
def dev() -> dict[str, Any]:
    if not docker_available():
        pytest.skip("docker unavailable")
    return check_compose.render("dev", DEPLOY / ".env.example")


def errors(rendered: dict[str, Any], mode: check_compose.Mode = "prod") -> list[str]:
    return check_compose.check_rendered(rendered, mode).errors


@needs_docker
def test_real_prod_stack_passes(prod: dict[str, Any]) -> None:
    assert errors(prod) == []
    ports = prod["services"]["proxy"]["ports"]
    assert [(p["host_ip"], str(p["published"]), p["target"]) for p in ports] == [("127.0.0.1", "18000", 8080)]


@needs_docker
def test_real_dev_stack_passes(dev: dict[str, Any]) -> None:
    assert errors(dev, "dev") == []
    published = {int(p["published"]) for s in dev["services"].values() for p in s.get("ports", [])}
    assert published and all(18100 <= p <= 18199 for p in published)


@needs_docker
def test_no_service_publishes_8000_anywhere(prod: dict[str, Any], dev: dict[str, Any]) -> None:
    for rendered in (prod, dev):
        for svc in rendered["services"].values():
            for p in svc.get("ports", []):
                assert str(p.get("published")) != "8000"


@needs_docker
def test_data_services_have_no_published_ports_in_prod(prod: dict[str, Any]) -> None:
    for name in ("postgres", "redis", "minio", "api", "prometheus", "loki", "alloy", "postgres-exporter"):
        assert not prod["services"][name].get("ports"), name


@needs_docker
def test_gpu_workers_pinned_and_register_under_their_own_id(prod: dict[str, Any]) -> None:
    """QC-e2e-09: the worker reads HIBISCUS_GPU_INDEX / HIBISCUS_NVML_INDEX (worker/core/settings.py)."""
    w0, w1 = prod["services"]["worker-cuda0"], prod["services"]["worker-cuda1"]
    assert check_compose._gpu_device_ids(w0) == ["0"]
    assert check_compose._gpu_device_ids(w1) == ["1"]
    assert (w0["environment"]["HIBISCUS_GPU_INDEX"], w0["environment"]["HIBISCUS_NVML_INDEX"]) == ("0", "0")
    assert (w1["environment"]["HIBISCUS_GPU_INDEX"], w1["environment"]["HIBISCUS_NVML_INDEX"]) == ("1", "0")
    assert w1["environment"]["NVIDIA_TF32_OVERRIDE"] == "0"
    assert w1["build"]["args"]["TORCH_INDEX_URL"].endswith("/cu126")


@needs_docker
def test_worker_cpu_runs_validate_module(prod: dict[str, Any]) -> None:
    """QC-e2e-03: the worker image defaults to `python -m train`."""
    assert prod["services"]["worker-cpu"]["environment"]["HIBISCUS_WORKER_MODULE"] == "validate"


@needs_docker
def test_every_pulled_image_is_pinned_by_digest(prod: dict[str, Any], dev: dict[str, Any]) -> None:
    """SEC-infra-3."""
    for rendered in (prod, dev):
        for name, svc in rendered["services"].items():
            image = svc.get("image", "")
            if image.startswith("hibiscus/"):
                continue
            assert check_compose.is_digest_pinned(image), (name, image)


def test_dockerfile_base_images_pinned_by_digest() -> None:
    """SEC-infra-3: every FROM default (ARG *_IMAGE / RUNTIME_BASE) carries a digest."""
    import re

    for df in sorted((DEPLOY / "docker").glob("*.Dockerfile")):
        args = dict(re.findall(r"^ARG ([A-Z_]*(?:IMAGE|BASE))=(\S+)$", df.read_text(), re.M))
        assert args, df
        for key, value in args.items():
            assert check_compose.is_digest_pinned(value), (df.name, key, value)


def test_digest_parser() -> None:
    good = "redis:7.4.12-alpine@sha256:" + "a" * 64
    assert check_compose.is_digest_pinned(good)
    assert not check_compose.is_digest_pinned("redis:7.4.12-alpine")
    assert not check_compose.is_digest_pinned("redis@sha256:" + "a" * 64)  # keep the tag for humans
    assert not check_compose.is_digest_pinned("redis:7@sha256:abc")


@needs_docker
@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda r: r["services"]["proxy"]["ports"][0].update(host_ip="0.0.0.0"), "not bound to 127.0.0.1"),  # noqa: S104
        (lambda r: r["services"]["proxy"]["ports"][0].update(published="8000"), "forbidden host port 8000"),
        (
            lambda r: r["services"]["postgres"].update(
                ports=[{"host_ip": "127.0.0.1", "published": "5432", "target": 5432}]
            ),
            "not an allowed production port",
        ),
        (lambda r: r["services"]["redis"].update(ports=[{"target": 6379}]), "random host port"),
        (lambda r: r["networks"]["data"].pop("internal"), "must be internal"),
        (
            lambda r: r["services"]["worker-cuda1"]["environment"].pop("NVIDIA_TF32_OVERRIDE"),
            "NVIDIA_TF32_OVERRIDE=0",
        ),
        (
            lambda r: r["services"]["worker-cuda1"]["environment"].pop("HIBISCUS_GPU_INDEX"),
            "HIBISCUS_GPU_INDEX=1",
        ),
        (
            lambda r: r["services"]["worker-cuda1"]["environment"].update(HIBISCUS_NVML_INDEX="1"),
            "HIBISCUS_NVML_INDEX=0",
        ),
        (
            lambda r: r["services"]["worker-cpu"]["environment"].pop("HIBISCUS_WORKER_MODULE"),
            "HIBISCUS_WORKER_MODULE=validate",
        ),
        (lambda r: r["services"]["redis"].update(image="redis:7.4.12-alpine"), "not pinned by digest"),
        (
            lambda r: r["services"]["worker-cpu"]["build"]["args"].update(RUNTIME_BASE="python:3.12"),
            "RUNTIME_BASE",
        ),
        (lambda r: r["services"]["worker-cuda0"].update(stop_grace_period="10s"), "stop_grace_period"),
        (
            lambda r: r["services"]["worker-cuda0"]["deploy"]["resources"]["reservations"]["devices"][
                0
            ].update(device_ids=["0", "1"]),
            "exactly GPU 0",
        ),
        (lambda r: r["services"]["api"].update(privileged=True), "privileged"),
        (
            lambda r: r["services"]["alloy"]["volumes"].append(
                {"type": "bind", "source": "/var/run/docker.sock", "target": "/var/run/docker.sock"}
            ),
            "Docker socket",
        ),
        (
            lambda r: r["services"]["worker-cuda1"]["volumes"].__setitem__(
                0, {"type": "volume", "source": "other", "target": "/cache"}
            ),
            "different sources at /cache",
        ),
        (lambda r: r["services"]["api"].update(network_mode="host"), "network_mode: host"),
    ],
)
def test_violations_are_reported(prod: dict[str, Any], mutate: Any, expected: str) -> None:
    rendered = copy.deepcopy(prod)
    mutate(rendered)
    errs = errors(rendered)
    assert any(expected in e for e in errs), errs


def test_dev_range_enforced() -> None:
    rendered = {
        "services": {"proxy": {"ports": [{"host_ip": "127.0.0.1", "published": "18000", "target": 8080}]}},
        "networks": {n: {"internal": True} for n in ("app", "data", "obs")},
    }
    errs = errors(rendered, "dev")
    assert any("outside the dev range" in e for e in errs)


def test_missing_entrypoint_in_prod() -> None:
    rendered = {
        "services": {"proxy": {}},
        "networks": {n: {"internal": True} for n in ("app", "data", "obs")},
    }
    errs = check_compose.check_rendered(rendered, "prod", require_gpu=False).errors
    assert any("127.0.0.1:18000" in e for e in errs)


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("2m0s", 120), ("120s", 120), ("1h", 3600), ("1m30s", 90), ("500ms", 0.5), (None, 0)],
)
def test_duration_parser(text: str | None, seconds: float) -> None:
    assert check_compose._duration_seconds(text) == pytest.approx(seconds)


def test_cli_with_prerendered_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "r.json"
    f.write_text(
        '{"services": {"proxy": {"ports": [{"host_ip": "", "published": "8000", "target": 8080}]}}, '
        '"networks": {}}'
    )
    assert check_compose.main(["--mode", "prod", "--rendered", str(f)]) == 1
    err = capsys.readouterr().err
    assert "forbidden host port 8000" in err and "is missing" in err
