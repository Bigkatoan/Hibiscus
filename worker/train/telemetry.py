"""NVML GPU info + 5 s telemetry sampler (run-lifecycle §9)."""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, insert, update

from core.bus import Bus
from core.events import iso, utcnow
from core.tables import gpu_nodes, gpu_telemetry

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GpuInfo:
    name: str
    uuid: str | None
    total_vram_mb: int
    compute_capability: str
    driver_version: str | None

    @property
    def supports_bf16(self) -> bool:
        return float(self.compute_capability) >= 8.0

    @property
    def supports_fast_fp16(self) -> bool:
        return float(self.compute_capability) >= 7.0


@dataclass(frozen=True, slots=True)
class Sample:
    util_pct: float
    mem_used_mb: int
    mem_total_mb: int
    temperature_c: float
    power_w: float


def torch_supports(compute_capability: str) -> bool | None:
    """Does the installed torch build ship kernels (or PTX) for this GPU? ``None`` = unknown.

    Measured on this box: torch 2.15.0+cu132 has ``sm_75..sm_120`` only, so a Tesla P40 (``sm_61``)
    fails every CUDA op (CONTRACT_NOTES CR-A4-7). The worker registers such a GPU as ``disabled``.
    """
    try:
        import torch

        archs = list(torch.cuda.get_arch_list())
    except Exception:
        return None
    if not archs:
        return None
    major, minor = (int(x) for x in compute_capability.split(".")[:2])
    cc = major * 10 + minor
    for a in archs:
        kind, _, num = a.partition("_")
        if not num.isdigit():
            continue
        n = int(num)
        if (kind == "sm" and n // 10 == major and n <= cc) or (kind == "compute" and n <= cc):
            return True
    return False


def resolve_nvml_index(index: int, device_count: int) -> int:
    """QC-e2e-09: a container that sees one GPU (compose ``device_ids: ["1"]``) has it at NVML
    index 0 even though the host index (``HIBISCUS_GPU_INDEX``) is 1."""
    if 0 <= index < device_count:
        return index
    if device_count == 1:
        log.info("NVML sees a single device: using index 0 for host GPU %d", index)
        return 0
    return index


class Nvml:
    """Thin wrapper; ``None`` handle when NVML is disabled/unavailable (tests on CPU boxes)."""

    def __init__(self, index: int, *, disabled: bool = False) -> None:
        self.index = index
        self._h: Any = None
        self._nv: Any = None
        if disabled:
            return
        try:
            import pynvml

            pynvml.nvmlInit()
            self._nv = pynvml
            self.index = resolve_nvml_index(index, int(pynvml.nvmlDeviceGetCount()))
            self._h = pynvml.nvmlDeviceGetHandleByIndex(self.index)
        except Exception as exc:
            log.warning("NVML unavailable: %s", exc)
            self._h = None

    @property
    def available(self) -> bool:
        return self._h is not None

    def info(self) -> GpuInfo | None:
        if self._h is None:
            return None
        nv = self._nv
        name = nv.nvmlDeviceGetName(self._h)
        name = name.decode() if isinstance(name, bytes) else str(name)
        major, minor = nv.nvmlDeviceGetCudaComputeCapability(self._h)
        mem = nv.nvmlDeviceGetMemoryInfo(self._h)
        try:
            u = nv.nvmlDeviceGetUUID(self._h)
            gpu_uuid: str | None = u.decode() if isinstance(u, bytes) else str(u)
        except Exception:
            gpu_uuid = None
        try:
            d = nv.nvmlSystemGetDriverVersion()
            driver: str | None = d.decode() if isinstance(d, bytes) else str(d)
        except Exception:
            driver = None
        return GpuInfo(name, gpu_uuid, int(mem.total // (1024 * 1024)), f"{major}.{minor}", driver)

    def sample(self) -> Sample | None:
        if self._h is None:
            return None
        nv = self._nv
        try:
            util = nv.nvmlDeviceGetUtilizationRates(self._h)
            mem = nv.nvmlDeviceGetMemoryInfo(self._h)
            temp = nv.nvmlDeviceGetTemperature(self._h, nv.NVML_TEMPERATURE_GPU)
            try:
                power = nv.nvmlDeviceGetPowerUsage(self._h) / 1000.0
            except Exception:
                power = 0.0
            return Sample(
                float(util.gpu),
                int(mem.used // (1024 * 1024)),
                int(mem.total // (1024 * 1024)),
                float(temp),
                float(power),
            )
        except Exception as exc:
            log.warning("NVML sample failed: %s", exc)
            return None

    def mem_used_mb(self) -> int | None:
        s = self.sample()
        return s.mem_used_mb if s else None


class TelemetrySampler(threading.Thread):
    """Inserts ``gpu_telemetry`` rows, refreshes ``gpu_nodes.last_heartbeat_at`` and publishes
    ``telemetry`` events on the current run's channel every ``interval_s``."""

    def __init__(
        self, *, engine: Engine, bus: Bus | None, nvml: Nvml, gpu_id: str, interval_s: float
    ) -> None:
        super().__init__(name=f"telemetry-{gpu_id}", daemon=True)
        self.engine = engine
        self.bus = bus
        self.nvml = nvml
        self.gpu_id = gpu_id
        self.interval_s = interval_s
        self.run_id: uuid.UUID | None = None
        self.peak_used_mb = 0
        self._stop_evt = threading.Event()

    def stop(self) -> None:
        self._stop_evt.set()

    def tick(self) -> None:
        s = self.nvml.sample()
        now = utcnow()
        run_id = self.run_id
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    update(gpu_nodes).where(gpu_nodes.c.id == self.gpu_id).values(last_heartbeat_at=now)
                )
                if s is not None:
                    conn.execute(
                        insert(gpu_telemetry).values(
                            gpu_node_id=self.gpu_id,
                            run_id=run_id,
                            ts=now,
                            util_pct=s.util_pct,
                            mem_used_mb=s.mem_used_mb,
                            mem_total_mb=s.mem_total_mb,
                            temperature_c=s.temperature_c,
                            power_w=s.power_w,
                        )
                    )
        except Exception as exc:
            log.warning("telemetry write failed: %s", type(exc).__name__)
        if s is not None:
            self.peak_used_mb = max(self.peak_used_mb, s.mem_used_mb)
            if run_id is not None and self.bus is not None:
                self.bus.publish_run(
                    str(run_id),
                    "telemetry",
                    {
                        "kind": "telemetry",
                        "gpu_id": self.gpu_id,
                        "ts": iso(now),
                        "util_pct": s.util_pct,
                        "mem_used_mb": s.mem_used_mb,
                        "mem_total_mb": s.mem_total_mb,
                        "temperature_c": s.temperature_c,
                        "power_w": s.power_w,
                    },
                )

    def run(self) -> None:
        while not self._stop_evt.is_set():
            self.tick()
            self._stop_evt.wait(self.interval_s)
