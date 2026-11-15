"""Metric series loading + LTTB downsampling (getRunMetrics / compareRuns)."""

from __future__ import annotations

import math
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RunMetric

Series = list[tuple[int, float]]


async def load_series(
    db: AsyncSession, run_id: uuid.UUID, keys: list[str] | None, from_step: int | None, to_step: int | None
) -> dict[str, Series]:
    stmt = select(RunMetric.key, RunMetric.step, RunMetric.value).where(RunMetric.run_id == run_id)
    if keys:
        stmt = stmt.where(RunMetric.key.in_(keys))
    if from_step is not None:
        stmt = stmt.where(RunMetric.step >= from_step)
    if to_step is not None:
        stmt = stmt.where(RunMetric.step <= to_step)
    out: dict[str, Series] = {}
    for key, step, value in (await db.execute(stmt.order_by(RunMetric.key, RunMetric.step))).all():
        out.setdefault(str(key), []).append((int(step), float(value)))
    if keys:
        return {k: out[k] for k in keys if k in out}
    return out


def lttb(points: Series, threshold: int) -> Series:
    """Largest-Triangle-Three-Buckets over finite points (non-finite points are kept separately)."""
    n = len(points)
    if threshold >= n or threshold < 3:
        return list(points)
    out = [points[0]]
    every = (n - 2) / (threshold - 2)
    a = 0
    for i in range(threshold - 2):
        start = math.floor((i + 1) * every) + 1
        end = min(math.floor((i + 2) * every) + 1, n)
        avg_x = sum(p[0] for p in points[start:end]) / max(end - start, 1)
        avg_y = sum(p[1] for p in points[start:end]) / max(end - start, 1)
        rs = math.floor(i * every) + 1
        re_ = math.floor((i + 1) * every) + 1
        ax, ay = points[a]
        best, best_area = rs, -1.0
        for j in range(rs, re_):
            area = abs((ax - avg_x) * (points[j][1] - ay) - (ax - points[j][0]) * (avg_y - ay))
            if area > best_area:
                best, best_area = j, area
        out.append(points[best])
        a = best
    out.append(points[-1])
    return out


def downsample_series(key: str, points: Series, max_points: int) -> dict[str, Any]:
    finite = [p for p in points if math.isfinite(p[1])]
    nonfinite = [p for p in points if not math.isfinite(p[1])]
    down = lttb(finite, max_points) if len(finite) > max_points else finite
    merged = sorted(down + nonfinite[: max(0, max_points - len(down))] if nonfinite else down)
    return {
        "key": key,
        "steps": [s for s, _ in merged],
        "values": [v if math.isfinite(v) else None for _, v in merged],
        "has_nonfinite": bool(nonfinite),
        "downsampled": len(merged) < len(points),
    }
