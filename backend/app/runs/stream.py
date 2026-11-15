"""``streamRunEvents`` - SSE with Last-Event-ID replay and 15 s heartbeats (ADR-10, run-lifecycle §9).

Algorithm (no gap, no duplicate):
1. subscribe to ``hibiscus:run:<id>`` *before* reading the backlog;
2. replay ``run_events`` with ``seq > last_id`` from Postgres;
3. live: persisted messages with ``id <= sent`` are dropped, a jump (``id > sent + 1``) is
   back-filled from Postgres; ephemeral messages (``progress``/``log``/``telemetry``) pass through,
   filtered by ``include``;
4. ``heartbeat`` every 15 s; without Redis the table is polled every 2 s;
5. once the run is terminal and the backlog is flushed: ``event: end`` and close;
6. every ``sse_auth_recheck_s`` the caller's session / PAT and workspace membership are re-checked
   and the stream closes when either is gone; it also closes after ``sse_max_lifetime_s`` so the
   client reconnects with fresh credentials (SEC-auth-03).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.deps import Principal, StreamAuthGuard
from app.core.errors import ErrorCode, ProblemError
from app.db.models import RUN_TERMINAL_STATUSES, Run, RunEvent
from app.runs.access import load_run
from app.runs.deps import DB, CurrentPrincipal
from app.runs.events import iso_now, run_channel

router = APIRouter(tags=["runs"])
EPHEMERAL = {"progress", "log", "telemetry"}


def sse(event: str, data: Any, id_: int | None = None) -> bytes:
    lines = []
    if id_ is not None:
        lines.append(f"id: {id_}")
    lines.append(f"event: {event}")
    lines.append("data: " + json.dumps(data, separators=(",", ":"), default=str))
    return ("\n".join(lines) + "\n\n").encode()


async def _backlog(
    maker: async_sessionmaker[AsyncSession], run_id: uuid.UUID, after: int
) -> tuple[list[RunEvent], str]:
    async with maker() as db:
        rows = list(
            (
                await db.execute(
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id, RunEvent.seq > after)
                    .order_by(RunEvent.seq)
                    .limit(5000)
                )
            ).scalars()
        )
        status = await db.scalar(select(Run.status).where(Run.id == run_id))
    return rows, (status.value if status is not None else "cancelled")


async def event_stream(
    request: Request,
    run_id: uuid.UUID,
    after: int,
    include: set[str],
    *,
    principal: Principal | None = None,
    workspace_id: uuid.UUID | None = None,
) -> AsyncIterator[bytes]:
    st = request.app.state.runs
    guard = (
        StreamAuthGuard.for_request(request, principal, workspace_id, st.sessionmaker)
        if principal is not None and workspace_id is not None
        else None
    )
    maker: async_sessionmaker[AsyncSession] = st.sessionmaker
    hb_every: float = st.settings.sse_heartbeat_s
    poll_every: float = st.settings.sse_poll_s
    terminal = {s.value for s in RUN_TERMINAL_STATUSES}
    pubsub = None
    if st.redis is not None:
        try:
            pubsub = st.redis.pubsub()
            await pubsub.subscribe(run_channel(run_id))
        except Exception:
            pubsub = None
    yield b"retry: 3000\n\n"
    sent = after
    try:
        rows, status = await _backlog(maker, run_id, sent)
        for e in rows:
            yield sse(e.type, e.data, int(e.seq))
            sent = int(e.seq)
        last_hb = time.monotonic()
        last_poll = time.monotonic()
        while True:
            if await request.is_disconnected():
                return
            if guard is not None and not await guard.ok():
                return
            if status in terminal:
                rows, status = await _backlog(maker, run_id, sent)
                for e in rows:
                    yield sse(e.type, e.data, int(e.seq))
                    sent = int(e.seq)
                yield sse("end", {"kind": "end", "final_status": status})
                return
            msg = None
            if pubsub is not None:
                try:
                    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                except Exception:
                    pubsub = None
            else:
                await asyncio.sleep(min(poll_every, 1.0))
            if msg is not None and msg.get("type") == "message":
                try:
                    env = json.loads(msg["data"])
                except (ValueError, TypeError):
                    env = None
                if isinstance(env, dict):
                    ev, seq, data = env.get("event"), env.get("id"), env.get("data")
                    if seq is None:
                        if ev in EPHEMERAL and ev in include:
                            yield sse(str(ev), data)
                    elif int(seq) > sent:
                        if int(seq) > sent + 1:
                            rows, status = await _backlog(maker, run_id, sent)
                            for e in rows:
                                yield sse(e.type, e.data, int(e.seq))
                                sent = int(e.seq)
                        if int(seq) > sent:
                            yield sse(str(ev), data, int(seq))
                            sent = int(seq)
                        if ev == "status" and isinstance(data, dict) and data.get("to") in terminal:
                            status = str(data["to"])
            now = time.monotonic()
            if pubsub is None or now - last_poll >= max(poll_every, 5.0):
                rows, status = await _backlog(maker, run_id, sent)
                for e in rows:
                    yield sse(e.type, e.data, int(e.seq))
                    sent = int(e.seq)
                last_poll = now
            if now - last_hb >= hb_every:
                yield sse("heartbeat", {"kind": "heartbeat", "ts": iso_now()})
                last_hb = now
    finally:
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
                await pubsub.aclose()
            except Exception:  # noqa: S110 - connection may already be gone
                pass


@router.get("/runs/{run_id}/events", operation_id="streamRunEvents", response_model=None)
async def stream_run_events(
    run_id: uuid.UUID,
    request: Request,
    db: DB,
    principal: CurrentPrincipal,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID", pattern=r"^[0-9]{1,18}$")] = None,
    after_seq: Annotated[int | None, Query(ge=0)] = None,
    include: str | None = None,
) -> StreamingResponse:
    run, _ = await load_run(db, principal, run_id, "runs:read")
    inc = set(EPHEMERAL) if include is None else {x for x in include.split(",") if x}
    if not inc <= EPHEMERAL:
        raise ProblemError(
            422,
            ErrorCode.VALIDATION_FAILED,
            "include accepts progress, log, telemetry",
            errors=[{"loc": ["query", "include"], "code": "enum", "message": include or ""}],
        )
    after = int(last_event_id) if last_event_id is not None else (after_seq or 0)
    await db.close()  # do not hold a pooled connection for the lifetime of the stream
    return StreamingResponse(
        event_stream(request, run.id, after, inc, principal=principal, workspace_id=run.workspace_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
