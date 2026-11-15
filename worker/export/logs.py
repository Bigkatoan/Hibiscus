"""``logs/train.log`` (attempts concatenated, tqdm frames collapsed) and ``logs/metrics.csv``."""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


@dataclass(frozen=True)
class MetricRow:
    step: int
    key: str
    value: float
    ts: datetime


def collapse_tqdm(text: str) -> str:
    """Keep only the final carriage-return frame of every line and strip ANSI cursor codes."""
    out: list[str] = []
    for line in text.split("\n"):
        frames = [f for f in _ANSI.sub("", line).split("\r") if f.strip()]
        out.append(frames[-1].rstrip() if frames else "")
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + ("\n" if out else "")


def write_train_log(attempt_logs: list[Path], dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    for i, path in enumerate(attempt_logs, start=1):
        text = path.read_bytes().decode("utf-8", errors="replace")
        header = f"===== Hibiscus attempt {i}/{len(attempt_logs)}: {path.name} =====\n"
        parts.append(header + collapse_tqdm(text))
    dst.write_text("".join(parts) if parts else "(no training log captured)\n")


def write_metrics_csv(rows: Iterable[MetricRow], dst: Path) -> int:
    dst.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with dst.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["step", "key", "value", "ts"])
        for r in sorted(rows, key=lambda r: (r.step, r.key, r.ts)):
            w.writerow([r.step, r.key, repr(float(r.value)), r.ts.isoformat()])
            n += 1
    return n
