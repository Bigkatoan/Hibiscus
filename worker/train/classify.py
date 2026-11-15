"""Attempt failure classification (run-lifecycle §6, first match wins)."""

from __future__ import annotations

import re
from dataclasses import dataclass

USER_CODES = frozenset({"config_invalid", "dataset_feature_mismatch", "oom", "nan_loss", "quota_exceeded"})
INFRA_CODES = frozenset(
    {
        "dataset_unavailable",
        "stalled",
        "gpu_error",
        "process_crashed",
        "storage_error",
        "checkpoint_corrupt",
        "worker_lost",
        "export_failed",
        "internal_error",
    }
)

_CONFIG_EXC = re.compile(r"\b(draccus|ParsingError|ValueError|NotImplementedError|TypeError)\b")
_CONFIG_SRC = re.compile(r"(lerobot/configs/|configuration_\w+\.py|draccus/)")
_FEATURE = re.compile(
    r"(KeyError: 'observation\.|feature(s)? (mismatch|validation)|Missing (image|state) feature)"
)


@dataclass(slots=True)
class ExitFacts:
    returncode: int
    training_started: bool
    oom: bool
    cuda_fatal: bool
    tail: str  # last log lines (collapsed)


def classify(f: ExitFacts) -> tuple[str, str]:
    """Return ``(error_code, message)`` for a non-zero exit we did not cause."""
    tb = f.tail
    if not f.training_started and f.returncode != 0 and _raised_from_config(tb):
        return "config_invalid", _last_exception_line(tb) or "lerobot-train rejected the configuration"
    if _FEATURE.search(tb):
        return "dataset_feature_mismatch", _last_exception_line(
            tb
        ) or "dataset features do not match the policy"
    if f.oom:
        return "oom", "CUDA out of memory - reduce batch_size (or image size / chunk size)"
    if f.cuda_fatal:
        return "gpu_error", _last_exception_line(tb) or "fatal CUDA error"
    if f.returncode < 0:
        return "process_crashed", f"lerobot-train killed by signal {-f.returncode}"
    return "process_crashed", _last_exception_line(tb) or f"lerobot-train exited with code {f.returncode}"


def _raised_from_config(tail: str) -> bool:
    """The innermost traceback frame is in lerobot/configs, a configuration_*.py or draccus."""
    frames = [ln for ln in tail.splitlines() if ln.strip().startswith('File "')]
    exc = _last_exception_line(tail) or ""
    return bool(frames) and bool(_CONFIG_SRC.search(frames[-1])) and bool(_CONFIG_EXC.search(exc))


def _last_exception_line(tail: str) -> str | None:
    for line in reversed(tail.splitlines()):
        s = line.strip()
        if re.match(r"^[A-Za-z_][\w.]*(Error|Exception)\b", s):
            return s[:500]
    return None


def is_infra(code: str) -> bool:
    return code in INFRA_CODES
