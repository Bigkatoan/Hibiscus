from __future__ import annotations

from typing import Any

import pytest

from hibiscus.api import ApiError, HibiscusApi
from hibiscus.logs import LogFollower, LogSink
from hibiscus.sse import RunEventStream, SseParser, iter_sse_lines
from tests.fake_server import FakeHibiscus, SseConnection, now


def _status(run_id: str, frm: str | None, to: str) -> dict[str, Any]:
    return {"kind": "status", "run_id": run_id, "from": frm, "to": to, "ts": now(), "attempt": 1}


def _metrics(step: int, loss: float) -> dict[str, Any]:
    return {"kind": "metrics", "step": step, "values": {"loss": loss, "grad_norm": None}, "ts": now()}


def _log(offset: int, lines: list[str]) -> dict[str, Any]:
    return {"kind": "log", "byte_offset": offset, "lines": lines}


def test_parser_whatwg_rules() -> None:
    lines = [
        ": comment",
        "retry: 2500",
        "id: 7",
        "event: metrics",
        'data: {"a":',
        "data:  1}",
        "",
        "data: no-event-name",
        "",
        "id: bad\0id",
        "event: x",
        "",
        "",
    ]
    msgs = list(iter_sse_lines(lines))
    assert [(m.event, m.data, m.id) for m in msgs] == [
        ("metrics", '{"a":\n 1}', "7"),
        ("message", "no-event-name", None),
        ("x", "", None),
    ]
    p = SseParser()
    for ln in lines[:3]:
        p.feed(ln)
    assert p.retry_ms == 2500 and p.last_event_id == "7"


def test_stream_reconnects_with_last_event_id(fake: FakeHibiscus, api: HibiscusApi) -> None:
    run = fake.add_run(status="running")
    rid = run["id"]
    fake.persist_event(rid, "status", _status(rid, "queued", "running"))  # seq 1, replayed on first connect
    fake.sse_scripts[rid] = [
        SseConnection(
            live=[
                ("metrics", _metrics(200, 0.9), True),
                ("metrics", _metrics(400, 0.7), True),
                ("heartbeat", {"kind": "heartbeat", "ts": now()}, False),
                ("metrics", _metrics(600, 0.5), True),
            ],
            drop_after=2,
        ),
        SseConnection(status=503),
        SseConnection(live=[("metrics", _metrics(800, 0.3), True)], end=True),
    ]
    delays: list[float] = []
    reconnects: list[str] = []
    stream = RunEventStream(
        api, rid, sleep=delays.append, on_reconnect=lambda n, why, d: reconnects.append(why)
    )
    seen = [(m.event, m.id) for m in stream]
    assert seen == [
        ("status", "1"),
        ("metrics", "2"),
        ("metrics", "3"),  # connection 1 then dropped
        ("metrics", "4"),
        ("end", None),  # connection 3 after a 503: no duplicates replayed
    ]
    last_ids = [r.headers.get("last-event-id") for r in fake.requests if r.operation_id == "streamRunEvents"]
    assert last_ids == [None, "3", "3"]
    assert len(reconnects) == 2 and "ReadError" in reconnects[0] and "503" in reconnects[1]
    assert delays == [3.0, 6.0]  # server retry: 3000, doubled on consecutive failure
    assert stream.ended


def test_stream_not_found_is_fatal(fake: FakeHibiscus, api: HibiscusApi) -> None:
    with pytest.raises(ApiError) as ei:
        list(RunEventStream(api, "00000000-0000-0000-0000-000000000000", sleep=lambda s: None))
    assert ei.value.status == 404 and ei.value.code == "not_found"


def test_stream_gives_up_after_max_reconnects(fake: FakeHibiscus, api: HibiscusApi) -> None:
    run = fake.add_run()
    fake.sse_scripts[run["id"]] = [SseConnection(status=502) for _ in range(5)]
    with pytest.raises(ApiError, match="gave up"):
        list(RunEventStream(api, run["id"], sleep=lambda s: None, max_reconnects=3))


def test_log_follower_dedupes_and_fills_gaps(fake: FakeHibiscus, api: HibiscusApi) -> None:
    lines = [f"line {i}" for i in range(10)]
    stored = "".join(ln + "\n" for ln in lines).encode()
    off = [0]
    for ln in lines:
        off.append(off[-1] + len(ln) + 1)
    run = fake.add_run(status="running", log=stored[: off[3]])  # 3 lines stored at start
    rid = run["id"]
    fake.sse_scripts[rid] = [
        # overlaps what we fetched (lines 2..3), then drops
        SseConnection(live=[("log", _log(off[2], lines[2:4]), False)], drop_after=1),
        # lines 4..6 were emitted while disconnected (ephemeral, lost); live resumes at line 7
        SseConnection(
            live=[
                ("log", _log(off[7], lines[7:9]), False),
                ("status", _status(rid, "running", "succeeded"), True),
                ("log", _log(off[9], lines[9:]), False),
            ],
            end=True,
        ),
    ]
    printed: list[str] = []
    events: list[tuple[str, str]] = []
    fake.run_logs[rid] = stored  # server keeps appending to the stored log
    follower = LogFollower(
        api,
        rid,
        LogSink(line=printed.append, event=lambda k, t: events.append((k, t))),
        stream_factory=lambda a, r: RunEventStream(a, r, include=["log"], sleep=lambda s: None),
    )
    fake.run_logs[rid] = stored[: off[3]]
    follower.print_existing(tail=None)
    fake.run_logs[rid] = stored
    fake.runs[rid]["status"] = "succeeded"
    final = follower.follow()
    assert printed == lines  # every line exactly once, in order
    assert final == "succeeded"
    assert ("status", "running -> succeeded") in events
    ranges = [r.headers.get("range") for r in fake.requests if r.operation_id == "getRunLogs"]
    assert ranges == ["bytes=0-", f"bytes={off[4]}-{off[7] - 1}"]
    includes = {r.path for r in fake.requests if r.operation_id == "streamRunEvents"}
    assert includes == {f"/runs/{rid}/events"}


def test_log_follower_tail_and_event_rendering(fake: FakeHibiscus, api: HibiscusApi) -> None:
    run = fake.add_run(status="failed", log=b"a\nb\nc\n")
    rid = run["id"]
    fake.persist_event(
        rid, "warning", {"kind": "warning", "code": "nan_detected", "message": "loss NaN", "ts": now()}
    )
    fake.persist_event(
        rid,
        "error",
        {"kind": "error", "code": "nan_loss", "message": "NaN", "ts": now(), "will_retry": False},
    )
    fake.persist_event(
        rid,
        "checkpoint",
        {
            "kind": "checkpoint",
            "step": 100,
            "checkpoint_id": "00000000-0000-0000-0000-000000000001",
            "ts": now(),
        },
    )
    fake.persist_event(rid, "metrics", _metrics(100, 1.5))
    printed: list[str] = []
    events: list[tuple[str, str]] = []
    f = LogFollower(
        api,
        rid,
        LogSink(line=printed.append, event=lambda k, t: events.append((k, t))),
        show_metrics=True,
        stream_factory=lambda a, r: RunEventStream(a, r, sleep=lambda s: None),
    )
    f.print_existing(tail=2)
    assert printed == ["b", "c"]
    assert f.follow() == "failed"
    kinds = [k for k, _ in events]
    assert kinds == ["warning", "error", "checkpoint", "metrics", "end"]
    assert "loss=1.5" in events[3][1]


def test_empty_log_416_is_tolerated(fake: FakeHibiscus, api: HibiscusApi) -> None:
    run = fake.add_run(status="queued", log=b"")
    f = LogFollower(api, run["id"], LogSink(line=lambda s: None, event=lambda k, t: None))
    f.print_existing(tail=None)
    assert f.pos == 0
