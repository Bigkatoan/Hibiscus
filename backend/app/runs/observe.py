"""getRunMetrics, getRunTelemetry, getRunLogs, searchRunLogs, listRunEvents."""

from __future__ import annotations

import csv
import io
import math
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core.errors import ErrorCode, ProblemError
from app.core.pagination import decode_cursor, encode_cursor
from app.db.models import GpuTelemetry, Run, RunEvent, RunMetric
from app.runs.access import load_run
from app.runs.deps import DB, CurrentPrincipal
from app.runs.metrics import downsample_series, load_series
from app.runs.serialize import event_record, iso
from app.runs.storage import AsyncStore, ObjectInfo

router = APIRouter(tags=["runs"])
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
RANGE_RE = re.compile(r"^bytes=(\d+)-(\d*)$")
ATTEMPT_RE = re.compile(r"attempt-(\d+)\.log$")
LEVEL_RE = re.compile(r"(?:^|\])\s*(DEBUG|INFO|WARNING|ERROR|CRITICAL) \d{4}-\d{2}-\d{2} ")
PERSISTED_TYPES = {"status", "metrics", "checkpoint", "warning", "error", "model", "eval"}


def _keys(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    keys = [k for k in raw.split(",") if k]
    for k in keys:
        if not KEY_RE.match(k):
            raise ProblemError(
                422,
                ErrorCode.VALIDATION_FAILED,
                f"bad metric key {k!r}",
                errors=[{"loc": ["query", "keys"], "code": "pattern", "message": k}],
            )
    return keys


@router.get("/runs/{run_id}/metrics", operation_id="getRunMetrics", response_model=None)
async def get_run_metrics(
    run_id: uuid.UUID,
    db: DB,
    principal: CurrentPrincipal,
    keys: str | None = None,
    from_step: Annotated[int | None, Query(ge=0)] = None,
    to_step: Annotated[int | None, Query(ge=0)] = None,
    max_points: Annotated[int, Query(ge=50, le=10000)] = 2000,
    format: Annotated[str, Query(pattern="^(json|csv)$")] = "json",
) -> dict[str, Any] | Response:
    run, _ = await load_run(db, principal, run_id, "runs:read")
    key_list = _keys(keys)
    if format == "csv":
        stmt = select(RunMetric).where(RunMetric.run_id == run.id)
        if key_list:
            stmt = stmt.where(RunMetric.key.in_(key_list))
        if from_step is not None:
            stmt = stmt.where(RunMetric.step >= from_step)
        if to_step is not None:
            stmt = stmt.where(RunMetric.step <= to_step)
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["step", "key", "value", "ts"])
        for m in (await db.execute(stmt.order_by(RunMetric.step, RunMetric.key))).scalars():
            v = m.value
            w.writerow([m.step, m.key, repr(v) if math.isfinite(v) else str(v).lower(), iso(m.ts)])
        return Response(buf.getvalue(), media_type="text/csv; charset=utf-8")
    series = await load_series(db, run.id, key_list, from_step, to_step)
    return {"run_id": str(run.id), "series": [downsample_series(k, s, max_points) for k, s in series.items()]}


@router.get("/runs/{run_id}/telemetry", operation_id="getRunTelemetry")
async def get_run_telemetry(
    run_id: uuid.UUID,
    db: DB,
    principal: CurrentPrincipal,
    since: datetime | None = None,
    max_points: Annotated[int, Query(ge=50, le=10000)] = 2000,
) -> dict[str, Any]:
    run, _ = await load_run(db, principal, run_id, "runs:read")
    stmt = select(GpuTelemetry).where(GpuTelemetry.run_id == run.id)
    if since is not None:
        stmt = stmt.where(GpuTelemetry.ts > (since if since.tzinfo else since.replace(tzinfo=UTC)))
    rows = list((await db.execute(stmt.order_by(GpuTelemetry.ts))).scalars())
    if len(rows) > max_points:
        stride = math.ceil(len(rows) / max_points)
        rows = rows[::stride]
    return {
        "items": [
            {
                "gpu_id": r.gpu_node_id,
                "ts": iso(r.ts),
                "util_pct": r.util_pct,
                "mem_used_mb": r.mem_used_mb,
                "mem_total_mb": r.mem_total_mb,
                "temperature_c": r.temperature_c,
                "power_w": r.power_w,
            }
            for r in rows
        ]
    }


async def log_objects(store: AsyncStore, bucket: str, run_id: uuid.UUID) -> list[tuple[int, ObjectInfo]]:
    objs = await store.list_prefix(bucket, f"runs/{run_id}/logs/")
    out = []
    for o in objs:
        m = ATTEMPT_RE.search(o.key)
        if m:
            out.append((int(m.group(1)), o))
    return sorted(out, key=lambda t: t[0])


@router.get("/runs/{run_id}/logs", operation_id="getRunLogs", response_model=None)
async def get_run_logs(
    run_id: uuid.UUID,
    request: Request,
    db: DB,
    principal: CurrentPrincipal,
    range_: Annotated[str | None, Header(alias="Range")] = None,
    download: bool = False,
) -> Response:
    run, _ = await load_run(db, principal, run_id, "runs:read")
    st = request.app.state.runs
    parts = await log_objects(st.store, st.settings.bucket_artifacts, run.id)
    total = sum(o.size for _, o in parts)
    start, end = 0, total - 1
    status = 200
    headers: dict[str, str] = {"Accept-Ranges": "bytes"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="run-{run.number}.log"'
    if range_:
        m = RANGE_RE.match(range_)
        if m is None:
            raise ProblemError(416, ErrorCode.RANGE_NOT_SATISFIABLE, "unsupported Range")
        start = int(m.group(1))
        end = min(int(m.group(2)), total - 1) if m.group(2) else total - 1
        if start >= total or start > end:
            raise ProblemError(
                416, ErrorCode.RANGE_NOT_SATISFIABLE, f"log has {total} bytes", params={"size": total}
            )
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
    if total == 0:
        return Response(b"", status_code=200, media_type="text/plain; charset=utf-8", headers=headers)

    async def body() -> Any:
        offset = 0
        for _, o in parts:
            lo, hi = offset, offset + o.size - 1
            offset += o.size
            if hi < start or lo > end or o.size == 0:
                continue
            async for chunk in st.store.stream(
                st.settings.bucket_artifacts, o.key, max(start - lo, 0), min(end, hi) - lo
            ):
                yield chunk

    headers["Content-Length"] = str(end - start + 1)
    return StreamingResponse(
        body(), status_code=status, media_type="text/plain; charset=utf-8", headers=headers
    )


@router.get("/runs/{run_id}/logs/search", operation_id="searchRunLogs")
async def search_run_logs(
    run_id: uuid.UUID,
    request: Request,
    db: DB,
    principal: CurrentPrincipal,
    q: Annotated[str, Query(min_length=2, max_length=200)],
    level: Annotated[str | None, Query(pattern="^(debug|info|warning|error)$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> dict[str, Any]:
    run, _ = await load_run(db, principal, run_id, "runs:read")
    st = request.app.state.runs
    after_line = int(decode_cursor(cursor)["l"]) if cursor else 0
    needle = q.lower()
    items: list[dict[str, Any]] = []
    line_no = 0
    offset = 0
    nxt = None
    for attempt, o in await log_objects(st.store, st.settings.bucket_artifacts, run.id):
        data = await st.store.get_bytes(st.settings.bucket_artifacts, o.key) if o.size else b""
        for raw in data.splitlines(keepends=True):
            line_no += 1
            line_off = offset
            offset += len(raw)
            if line_no <= after_line:
                continue
            textline = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if needle not in textline.lower():
                continue
            if level is not None:
                m = LEVEL_RE.search(textline)
                lv = (m.group(1) if m else "").lower()
                if lv == "critical":
                    lv = "error"
                if lv != level:
                    continue
            if len(items) == limit:
                nxt = encode_cursor({"l": items[-1]["line_no"]})
                break
            items.append(
                {"line_no": line_no, "byte_offset": line_off, "attempt": attempt, "text": textline[:4000]}
            )
        if nxt:
            break
    return {"items": items, "next_cursor": nxt}


@router.get("/runs/{run_id}/events/history", operation_id="listRunEvents")
async def list_run_events(
    run_id: uuid.UUID,
    db: DB,
    principal: CurrentPrincipal,
    after_seq: Annotated[int, Query(ge=0)] = 0,
    types: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> dict[str, Any]:
    run, _ = await load_run(db, principal, run_id, "runs:read")
    stmt = select(RunEvent).where(RunEvent.run_id == run.id, RunEvent.seq > after_seq)
    if types:
        tl = [t for t in types.split(",") if t]
        bad = [t for t in tl if t not in PERSISTED_TYPES]
        if bad:
            raise ProblemError(
                422,
                ErrorCode.VALIDATION_FAILED,
                f"unknown event types {bad}",
                errors=[{"loc": ["query", "types"], "code": "enum", "message": ",".join(bad)}],
            )
        stmt = stmt.where(RunEvent.type.in_(tl))
    rows = list((await db.execute(stmt.order_by(RunEvent.seq).limit(limit))).scalars())
    last = await db.scalar(select(Run.last_event_seq).where(Run.id == run.id))
    return {"items": [event_record(e) for e in rows], "last_seq": int(last or 0)}
