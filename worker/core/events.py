"""Persisted run events, metrics upserts and guarded status transitions (run-lifecycle §2, §9).

Every write happens inside a caller-provided transaction (``Connection`` from
``engine.begin()``); Redis publishes are collected in an :class:`Outbox` and sent **after commit**
via :meth:`Outbox.flush`.

Public API (stable for A5's export step, which runs under the train worker's lease):
    * :class:`Outbox`
    * :func:`append_run_event` -> seq
    * :func:`upsert_metrics`
    * :func:`transition` -> bool (False = optimistic guard lost)
    * :func:`utcnow`, :func:`iso`
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.bus import Bus, sanitize
from core.tables import gpu_nodes, run_events, run_metrics, runs

ACTIVE_STATUSES = ("preparing", "running", "pausing", "exporting", "cancelling")
TERMINAL_STATUSES = ("succeeded", "failed", "cancelled")


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class _Pending:
    kind: str  # "run" | "ws"
    target: str
    event: str
    data: dict[str, Any]
    seq: int | None


@dataclass(slots=True)
class Outbox:
    items: list[_Pending] = field(default_factory=list)

    def run(self, run_id: str, event: str, data: dict[str, Any], seq: int | None = None) -> None:
        self.items.append(_Pending("run", run_id, event, data, seq))

    def ws(self, workspace_id: str, event: str, data: dict[str, Any]) -> None:
        self.items.append(_Pending("ws", workspace_id, event, data, None))

    def flush(self, bus: Bus | None) -> None:
        items, self.items = self.items, []
        if bus is None:
            return
        for p in items:
            if p.kind == "run":
                bus.publish_run(p.target, p.event, p.data, p.seq)
            else:
                bus.publish_workspace(p.target, p.event, p.data)


def append_run_event(
    conn: Connection,
    run_id: uuid.UUID,
    event_type: str,
    data: dict[str, Any],
    *,
    outbox: Outbox,
    level: str = "info",
    attempt: int | None = None,
) -> int:
    """Allocate ``seq`` from ``runs.last_event_seq`` and insert one ``run_events`` row."""
    row = conn.execute(
        update(runs)
        .where(runs.c.id == run_id)
        .values(last_event_seq=runs.c.last_event_seq + 1)
        .returning(runs.c.last_event_seq, runs.c.attempt)
    ).one()
    seq = int(row.last_event_seq)
    att = int(row.attempt if attempt is None else attempt)
    clean = sanitize(data)
    conn.execute(
        insert(run_events).values(
            run_id=run_id, seq=seq, type=event_type, level=level, attempt=att, data=clean
        )
    )
    outbox.run(str(run_id), event_type, clean, seq)
    return seq


def upsert_metrics(
    conn: Connection, run_id: uuid.UUID, step: int, values: Mapping[str, float], ts: datetime
) -> None:
    rows = [
        {"run_id": run_id, "key": k, "step": step, "value": float(v), "ts": ts} for k, v in values.items()
    ]
    if not rows:
        return
    stmt = pg_insert(run_metrics).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[run_metrics.c.run_id, run_metrics.c.key, run_metrics.c.step],
        set_={"value": stmt.excluded.value, "ts": stmt.excluded.ts, "updated_at": func.now()},
    )
    conn.execute(stmt)


def metrics_event(step: int, values: Mapping[str, float], ts: datetime) -> dict[str, Any]:
    return {
        "kind": "metrics",
        "step": step,
        "values": {k: (v if math.isfinite(v) else None) for k, v in values.items()},
        "ts": iso(ts),
    }


def transition(
    conn: Connection,
    run_id: uuid.UUID,
    *,
    from_statuses: Iterable[str],
    to: str,
    outbox: Outbox,
    lease_owner: str | None = None,
    reason: str | None = None,
    error_code: str | None = None,
    extra: Mapping[str, Any] | None = None,
    release_gpu: bool = False,
) -> bool:
    """Guarded ``UPDATE runs SET status=:to WHERE id=:id AND status IN (:from) [AND lease_owner=:me]``.

    Inserts the ``status`` run event in the same transaction and queues Redis publishes on the run
    and workspace channels. Returns False (nothing written) when the guard does not match.
    """
    froms = list(from_statuses)
    cur = conn.execute(
        select(runs.c.status, runs.c.workspace_id, runs.c.gpu_node_id, runs.c.attempt)
        .where(runs.c.id == run_id)
        .with_for_update()
    ).one_or_none()
    if cur is None or cur.status not in froms:
        return False
    stmt = update(runs).where(runs.c.id == run_id, runs.c.status.in_(froms))
    if lease_owner is not None:
        stmt = stmt.where(runs.c.lease_owner == lease_owner)
    values: dict[str, Any] = {"status": to, "status_changed_at": func.now()}
    if extra:
        values.update(extra)
    if to in TERMINAL_STATUSES:
        values.setdefault("finished_at", func.now())
    if to in TERMINAL_STATUSES or to in ("queued", "paused"):
        values.update(lease_owner=None, lease_expires_at=None)
    res = conn.execute(stmt.values(**values).returning(runs.c.gpu_node_id, runs.c.attempt))
    row = res.one_or_none()
    if row is None:
        return False
    if release_gpu and cur.gpu_node_id is not None:
        conn.execute(
            update(gpu_nodes)
            .where(gpu_nodes.c.id == cur.gpu_node_id, gpu_nodes.c.current_run_id == run_id)
            .values(current_run_id=None)
        )
    now = utcnow()
    data: dict[str, Any] = {
        "kind": "status",
        "run_id": str(run_id),
        "from": cur.status,
        "to": to,
        "reason": reason,
        "error_code": error_code,
        "attempt": int(row.attempt),
        "gpu_id": row.gpu_node_id,
        "ts": iso(now),
    }
    level = "error" if to == "failed" else "info"
    append_run_event(conn, run_id, "status", data, outbox=outbox, level=level)
    outbox.ws(str(cur.workspace_id), "run.status", data)
    return True
