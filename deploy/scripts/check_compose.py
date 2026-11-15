#!/usr/bin/env python3
"""Static policy check for the Hibiscus compose files (CONTRACT_NOTES §3, ADR-0008).

Renders the stack with ``docker compose config --format json`` and fails when:

* a port is published on anything but 127.0.0.1, or host port 8000 (LeLab) is used;
* prod publishes anything besides proxy 127.0.0.1:18000 and the loopback admin ports;
* dev publishes outside 18100-18199;
* Postgres / Redis / MinIO / Prometheus / Loki / API share a network with a published port,
  or the internal networks are not ``internal``;
* the GPU workers are not pinned to one GPU each, do not register under the matching gpu id
  (HIBISCUS_GPU_INDEX = reserved device, HIBISCUS_NVML_INDEX = 0 inside the container), lack the
  shared /cache + /scratch mounts, the 120 s stop grace period, cgroup limits, or the P40 TF32 off;
* worker-cpu does not run the `validate` module (the image default is `train`);
* a third-party image is not pinned by digest (``name:tag@sha256:...``, SEC-infra-3);
* any service is privileged, uses host networking/PID, or mounts the Docker socket.

Which HIBISCUS_* names reach which container is checked separately against the application
settings classes by deploy/tests/test_env_contract.py.

Usage::

    deploy/scripts/check_compose.py --mode prod
    deploy/scripts/check_compose.py --mode dev
    deploy/scripts/check_compose.py --mode prod --rendered rendered.json   # skip docker
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Mode = Literal["prod", "dev"]

DEPLOY_DIR = Path(__file__).resolve().parent.parent
FORBIDDEN_HOST_PORTS = frozenset({8000})
PUBLIC_ENTRYPOINT = ("proxy", "127.0.0.1", 18000, 8080)
PROD_ALLOWED_PUBLISHED: dict[str, frozenset[int]] = {
    "proxy": frozenset({18000}),
    "grafana": frozenset({13000}),
}
DEV_PORT_RANGE = range(18100, 18200)
INTERNAL_ONLY_SERVICES = frozenset({"postgres", "redis", "minio", "api", "prometheus", "loki"})
INTERNAL_NETWORKS = frozenset({"app", "data", "obs"})
GPU_WORKERS: dict[str, dict[str, str]] = {
    "worker-cuda0": {"device": "0", "gpu_index": "0"},
    "worker-cuda1": {"device": "1", "gpu_index": "1"},
}
#: Images built from this repository (tagged by HIBISCUS_IMAGE_TAG); everything else is pulled.
LOCAL_IMAGE_PREFIX = "hibiscus/"
WORKER_STOP_GRACE_SECONDS = 120
LOOPBACK = "127.0.0.1"


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.errors.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _duration_seconds(value: Any) -> float:
    """Parse a compose duration ("2m0s", "120s", "1h") into seconds; 0 when absent."""
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    total = 0.0
    number = ""
    units = {"h": 3600.0, "m": 60.0, "s": 1.0}
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isdigit() or ch == ".":
            number += ch
        elif text.startswith("ms", i):
            total += float(number or 0) / 1000.0
            number = ""
            i += 1
        elif ch in units:
            total += float(number or 0) * units[ch]
            number = ""
        else:
            raise ValueError(f"unparseable duration {value!r}")
        i += 1
    if number:
        total += float(number)
    return total


def _service_networks(svc: Mapping[str, Any]) -> set[str]:
    nets = svc.get("networks")
    if isinstance(nets, dict):
        return set(nets)
    if isinstance(nets, list):
        return {str(n) for n in nets}
    return set()


def _published(svc: Mapping[str, Any]) -> list[tuple[str, int, int]]:
    out: list[tuple[str, int, int]] = []
    for port in _as_list(svc.get("ports")):
        p = _as_dict(port)
        published = p.get("published")
        if published in (None, ""):
            # container port only -> docker would pick a random host port on 0.0.0.0
            out.append((str(p.get("host_ip") or ""), -1, int(p.get("target", 0))))
            continue
        out.append((str(p.get("host_ip") or ""), int(str(published)), int(p.get("target", 0))))
    return out


def check_ports(services: Mapping[str, Any], mode: Mode, report: Report) -> None:
    seen_entrypoint = False
    for name, raw in services.items():
        svc = _as_dict(raw)
        for host_ip, published, target in _published(svc):
            shown_ip = host_ip or "*"
            where = f"{name}: {shown_ip}:{published}->{target}"
            if host_ip != LOOPBACK:
                report.fail(f"{where} is not bound to {LOOPBACK} (only loopback ports are allowed)")
            if published == -1:
                report.fail(f"{where} publishes a random host port")
                continue
            if published in FORBIDDEN_HOST_PORTS:
                report.fail(f"{where} uses forbidden host port {published} (LeLab)")
            if mode == "prod":
                allowed = PROD_ALLOWED_PUBLISHED.get(name, frozenset())
                if published not in allowed:
                    report.fail(f"{where} is not an allowed production port")
            elif published not in DEV_PORT_RANGE:
                report.fail(f"{where} is outside the dev range 18100-18199")
            if (name, host_ip, published, target) == PUBLIC_ENTRYPOINT:
                seen_entrypoint = True
    if mode == "prod" and not seen_entrypoint:
        report.fail("proxy must be published exactly as 127.0.0.1:18000->8080 in production")


def check_networks(services: Mapping[str, Any], networks: Mapping[str, Any], report: Report) -> None:
    for net in INTERNAL_NETWORKS:
        cfg = _as_dict(networks.get(net))
        if not cfg:
            report.fail(f"network {net!r} is missing")
        elif cfg.get("internal") is not True:
            report.fail(f"network {net!r} must be internal: true")
    exposed_networks: set[str] = set()
    for raw in services.values():
        svc = _as_dict(raw)
        if svc.get("ports"):
            exposed_networks |= _service_networks(svc)
    for name in INTERNAL_ONLY_SERVICES & set(services):
        svc = _as_dict(services[name])
        if svc.get("ports"):
            continue  # dev-only loopback publishing is judged by check_ports
        if "edge" in _service_networks(svc):
            report.fail(f"{name} must not join the edge network")


def check_hardening(services: Mapping[str, Any], report: Report) -> None:
    for name, raw in services.items():
        svc = _as_dict(raw)
        if svc.get("privileged"):
            report.fail(f"{name} is privileged")
        for key in ("network_mode", "pid", "ipc"):
            if str(svc.get(key, "")) == "host":
                report.fail(f"{name} uses {key}: host")
        for vol in _as_list(svc.get("volumes")):
            source = str(_as_dict(vol).get("source", ""))
            if source.endswith("docker.sock"):
                report.fail(f"{name} mounts the Docker socket")


def _gpu_device_ids(svc: Mapping[str, Any]) -> list[str]:
    deploy = _as_dict(svc.get("deploy"))
    devices = _as_list(_as_dict(_as_dict(deploy.get("resources")).get("reservations")).get("devices"))
    ids: list[str] = []
    for dev in devices:
        ids.extend(str(i) for i in _as_list(_as_dict(dev).get("device_ids")))
    return ids


def check_workers(services: Mapping[str, Any], report: Report, *, require_gpu: bool) -> None:
    for name, expect in GPU_WORKERS.items():
        if name not in services:
            if require_gpu:
                report.fail(f"{name} is missing")
            continue
        svc = _as_dict(services[name])
        ids = _gpu_device_ids(svc)
        if ids != [expect["device"]]:
            report.fail(f"{name} must reserve exactly GPU {expect['device']} (got {ids})")
        env = _as_dict(svc.get("environment"))
        # worker/core/settings.py: gpu_id = f"cuda{gpu_index}"; NVML sees only this container's GPU.
        if env.get("HIBISCUS_GPU_INDEX") != expect["gpu_index"]:
            report.fail(
                f"{name} must set HIBISCUS_GPU_INDEX={expect['gpu_index']} "
                f"(registers as cuda{expect['gpu_index']})"
            )
        if env.get("HIBISCUS_NVML_INDEX") != "0":
            report.fail(f"{name} must set HIBISCUS_NVML_INDEX=0 (one GPU visible in the container)")
        if env.get("HIBISCUS_WORKER_MODULE", "train") != "train":
            report.fail(f"{name} must run the train module")
        if _duration_seconds(svc.get("stop_grace_period")) < WORKER_STOP_GRACE_SECONDS:
            report.fail(f"{name} needs stop_grace_period >= {WORKER_STOP_GRACE_SECONDS}s")
        mounts = {
            (str(_as_dict(v).get("source")), str(_as_dict(v).get("target")))
            for v in _as_list(svc.get("volumes"))
        }
        for target in ("/cache", "/scratch"):
            if not any(t == target for _, t in mounts):
                report.fail(f"{name} must mount the shared {target} volume")
        limits = _as_dict(_as_dict(_as_dict(svc.get("deploy")).get("resources")).get("limits"))
        if not limits.get("memory") or not limits.get("cpus"):
            report.fail(f"{name} needs cgroup cpu + memory limits")
    if "worker-cuda1" in services:
        # fp32 itself follows from the P40's compute capability (the worker registers
        # supports_bf16/supports_fast_fp16 from NVML); TF32 must not be enabled by the CUDA libs.
        env = _as_dict(_as_dict(services["worker-cuda1"]).get("environment"))
        if env.get("NVIDIA_TF32_OVERRIDE") != "0":
            report.fail("worker-cuda1 (Tesla P40) must set NVIDIA_TF32_OVERRIDE=0")
    if "worker-cpu" in services:
        env = _as_dict(_as_dict(services["worker-cpu"]).get("environment"))
        if env.get("HIBISCUS_WORKER_MODULE") != "validate":
            report.fail("worker-cpu must set HIBISCUS_WORKER_MODULE=validate (the image default is train)")
    # Both GPU workers must see the very same /cache and /scratch volumes.
    sources: dict[str, set[str]] = {"/cache": set(), "/scratch": set()}
    for name in GPU_WORKERS:
        if name not in services:
            continue
        for v in _as_list(_as_dict(services[name]).get("volumes")):
            vd = _as_dict(v)
            target = str(vd.get("target"))
            if target in sources:
                sources[target].add(str(vd.get("source")))
    for target, srcs in sources.items():
        if len(srcs) > 1:
            report.fail(f"GPU workers mount different sources at {target}: {sorted(srcs)}")


def is_digest_pinned(image: str) -> bool:
    """``repo:tag@sha256:<64 hex>`` (the tag is kept for humans; the digest is what is pulled)."""
    name, sep, digest = image.partition("@")
    return bool(sep) and ":" in name and digest.startswith("sha256:") and len(digest) == 7 + 64


def check_images(services: Mapping[str, Any], report: Report) -> None:
    for name, raw in services.items():
        svc = _as_dict(raw)
        image = str(svc.get("image", ""))
        if image and not image.startswith(LOCAL_IMAGE_PREFIX) and not is_digest_pinned(image):
            report.fail(f"{name}: image {image!r} is not pinned by digest (name:tag@sha256:...)")
        args = _as_dict(_as_dict(svc.get("build")).get("args"))
        base = args.get("RUNTIME_BASE")
        if base is not None and not is_digest_pinned(str(base)):
            report.fail(f"{name}: build arg RUNTIME_BASE {base!r} is not pinned by digest")


def check_rendered(rendered: Mapping[str, Any], mode: Mode, *, require_gpu: bool = True) -> Report:
    report = Report()
    services = _as_dict(rendered.get("services"))
    networks = _as_dict(rendered.get("networks"))
    if "proxy" not in services:
        report.fail("proxy service is missing")
    check_ports(services, mode, report)
    check_networks(services, networks, report)
    check_hardening(services, report)
    check_workers(services, report, require_gpu=require_gpu)
    check_images(services, report)
    return report


def render(mode: Mode, env_file: Path, compose_bin: Sequence[str] = ("docker", "compose")) -> dict[str, Any]:
    files = ["-f", str(DEPLOY_DIR / "docker-compose.yml")]
    if mode == "dev":
        files += ["-f", str(DEPLOY_DIR / "compose.dev.yml")]
    cmd = [
        *compose_bin,
        "--project-directory",
        str(DEPLOY_DIR),
        *files,
        "--env-file",
        str(env_file),
        "--profile",
        "gpu",
        "config",
        "--format",
        "json",
    ]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True)  # noqa: S603 (argv list)
    data = json.loads(out.stdout)
    if not isinstance(data, dict):
        raise ValueError("docker compose config did not return an object")
    return data


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--mode", choices=["prod", "dev"], required=True)
    parser.add_argument("--env-file", type=Path, default=DEPLOY_DIR / ".env.example")
    parser.add_argument("--rendered", type=Path, help="pre-rendered `docker compose config --format json`")
    args = parser.parse_args(argv)
    mode: Mode = "prod" if args.mode == "prod" else "dev"
    if args.rendered:
        rendered = json.loads(args.rendered.read_text())
    else:
        rendered = render(mode, args.env_file)
    report = check_rendered(rendered, mode)
    for err in report.errors:
        print(f"FAIL {err}", file=sys.stderr)
    if report.ok:
        print(f"compose policy OK ({mode}, {len(_as_dict(rendered.get('services')))} services)")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
