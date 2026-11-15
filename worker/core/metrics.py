"""Prometheus metrics of the worker processes (phase-5 N-2: ``HibiscusWorkerDown`` fired forever
because nothing listened on ``:9108``).

Every worker process (GPU ``python -m train``, CPU ``python -m validate``) serves ``/metrics`` on
``HIBISCUS_METRICS_PORT`` (default 9108, 0 disables). Prometheus scrapes it as job ``workers``
(``deploy/observability/prometheus/prometheus.yml``).

Metric names (also listed in ``docs/runbook/observability.md``):

* ``hibiscus_worker_info{worker_kind,gpu_id,version}`` = 1
* ``hibiscus_worker_jobs_claimed_total{kind}``, ``..._succeeded_total{kind}``, ``..._failed_total{kind}``
  (``kind`` is a job kind, or ``train_run`` for a training run attempt)
* ``hibiscus_worker_lease_heartbeats_total{result}`` (``ok`` / ``lost``), runs and jobs
* ``hibiscus_worker_run_active``, ``hibiscus_worker_run_current_step``, ``hibiscus_worker_run_total_steps``
* ``hibiscus_worker_gpu_utilization_percent``, ``..._gpu_memory_used_bytes``,
  ``..._gpu_memory_total_bytes``, ``..._gpu_temperature_celsius``, ``..._gpu_power_watts``
  (label ``gpu_id``; sampled from NVML at scrape time, absent without NVML)
* the standard ``process_*`` / ``python_*`` collectors.

Public API: :data:`REGISTRY`, :func:`start_metrics_server`, :func:`set_info`, :func:`register_gpu`,
:func:`job_claimed`, :func:`job_ended`, :func:`lease_heartbeat`, :func:`run_started`,
:func:`run_step`, :func:`run_ended`.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from typing import Any, Protocol

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    PlatformCollector,
    ProcessCollector,
    start_http_server,
)
from prometheus_client.core import GaugeMetricFamily, Metric
from prometheus_client.registry import Collector

log = logging.getLogger("hibiscus.metrics")

REGISTRY = CollectorRegistry(auto_describe=True)
ProcessCollector(registry=REGISTRY)
PlatformCollector(registry=REGISTRY)

INFO = Gauge(
    "hibiscus_worker_info",
    "Worker identity (always 1)",
    ["worker_kind", "gpu_id", "version"],
    registry=REGISTRY,
)
JOBS_CLAIMED = Counter(
    "hibiscus_worker_jobs_claimed", "Jobs / run attempts claimed by this worker", ["kind"], registry=REGISTRY
)
JOBS_SUCCEEDED = Counter(
    "hibiscus_worker_jobs_succeeded", "Jobs / run attempts that ended succeeded", ["kind"], registry=REGISTRY
)
JOBS_FAILED = Counter(
    "hibiscus_worker_jobs_failed", "Jobs / run attempts that ended failed", ["kind"], registry=REGISTRY
)
LEASE_HEARTBEATS = Counter(
    "hibiscus_worker_lease_heartbeats", "Lease heartbeats (runs and jobs)", ["result"], registry=REGISTRY
)
RUN_ACTIVE = Gauge(
    "hibiscus_worker_run_active", "1 while a training run attempt is active", registry=REGISTRY
)
RUN_STEP = Gauge(
    "hibiscus_worker_run_current_step", "Current training step of the active run", registry=REGISTRY
)
RUN_TOTAL = Gauge("hibiscus_worker_run_total_steps", "Total steps of the active run", registry=REGISTRY)

TRAIN_RUN_KIND = "train_run"
_SUCCEEDED = frozenset({"succeeded"})
_FAILED = frozenset({"failed", "lease_lost", "lost"})
for _r in ("ok", "lost"):
    LEASE_HEARTBEATS.labels(result=_r)


class _Sample(Protocol):
    util_pct: float
    mem_used_mb: int
    mem_total_mb: int
    temperature_c: float
    power_w: float


class _Sampler(Protocol):
    @property
    def available(self) -> bool: ...

    def sample(self) -> Any: ...


class GpuCollector(Collector):
    """Reads NVML at scrape time (no extra thread, always fresh)."""

    def __init__(self, nvml: _Sampler, gpu_id: str) -> None:
        self.nvml = nvml
        self.gpu_id = gpu_id

    def describe(self) -> Iterator[Metric]:
        return iter(())

    def collect(self) -> Iterator[Metric]:
        if not self.nvml.available:
            return
        s: _Sample | None = self.nvml.sample()
        if s is None:
            return
        mib = 1024 * 1024
        for name, doc, value in (
            ("hibiscus_worker_gpu_utilization_percent", "GPU utilisation (NVML)", s.util_pct),
            ("hibiscus_worker_gpu_memory_used_bytes", "GPU memory used (NVML)", s.mem_used_mb * mib),
            ("hibiscus_worker_gpu_memory_total_bytes", "GPU memory total (NVML)", s.mem_total_mb * mib),
            ("hibiscus_worker_gpu_temperature_celsius", "GPU temperature (NVML)", s.temperature_c),
            ("hibiscus_worker_gpu_power_watts", "GPU power draw (NVML)", s.power_w),
        ):
            g = GaugeMetricFamily(name, doc, labels=["gpu_id"])
            g.add_metric([self.gpu_id], float(value))
            yield g


_gpu_lock = threading.Lock()
_gpu_collector: GpuCollector | None = None


def register_gpu(nvml: _Sampler, gpu_id: str) -> None:
    """(Re)register the NVML collector of this process."""
    global _gpu_collector
    with _gpu_lock:
        if _gpu_collector is not None:
            REGISTRY.unregister(_gpu_collector)
        _gpu_collector = GpuCollector(nvml, gpu_id)
        REGISTRY.register(_gpu_collector)


def set_info(worker_kind: str, gpu_id: str, version: str) -> None:
    INFO.clear()
    INFO.labels(worker_kind=worker_kind, gpu_id=gpu_id, version=version).set(1)


def start_metrics_server(port: int, addr: str = "0.0.0.0") -> Any | None:  # noqa: S104 - scraped over the compose network
    """Serve ``/metrics`` on ``addr:port``; ``port <= 0`` disables. Never raises (a busy port
    must not stop the worker); returns the server or None."""
    if port <= 0:
        log.info("metrics server disabled (HIBISCUS_METRICS_PORT=0)")
        return None
    try:
        server, _thread = start_http_server(port, addr=addr, registry=REGISTRY)
    except OSError as exc:
        log.warning("metrics server on %s:%d not started: %s", addr, port, exc)
        return None
    log.info("metrics on http://%s:%d/metrics", addr, port)
    return server


def job_claimed(kind: str) -> None:
    JOBS_CLAIMED.labels(kind=kind).inc()


def job_ended(kind: str, status: str) -> None:
    """Count an end status; statuses other than succeeded / failed (queued, cancelled) are not
    counted as either."""
    if status in _SUCCEEDED:
        JOBS_SUCCEEDED.labels(kind=kind).inc()
    elif status in _FAILED:
        JOBS_FAILED.labels(kind=kind).inc()


def lease_heartbeat(ok: bool) -> None:
    LEASE_HEARTBEATS.labels(result="ok" if ok else "lost").inc()


def run_started(current_step: int, total_steps: int) -> None:
    RUN_ACTIVE.set(1)
    RUN_STEP.set(current_step)
    RUN_TOTAL.set(total_steps)


def run_step(step: int) -> None:
    RUN_STEP.set(step)


def run_ended() -> None:
    RUN_ACTIVE.set(0)
