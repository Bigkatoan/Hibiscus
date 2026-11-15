"""core.* against real Postgres / Redis / MinIO containers."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
import redis
from sqlalchemy import Engine, select, text

from core.bus import Bus, run_channel
from core.db import with_retry
from core.events import Outbox, append_run_event, transition, upsert_metrics, utcnow
from core.jobs import claim_job, finish_job, heartbeat_job, oldest_queued_age_s
from core.s3 import ObjectStore, StorageError, parse_s3_uri
from core.tables import metadata as worker_metadata
from core.tables import run_events, run_metrics, runs
from core.testing import Services, contract_metadata, insert_run, seed_basic


def test_tables_mirror_contract() -> None:
    m = contract_metadata()
    contract = m.Base.metadata.tables
    for name, table in worker_metadata.tables.items():
        assert name in contract, name
        for col in table.columns:
            assert col.name in contract[name].columns, f"{name}.{col.name}"
            ct = contract[name].columns[col.name].type
            assert (
                col.type._type_affinity is ct._type_affinity
                or type(col.type).__name__ in type(ct).__name__
                or (
                    # enums are VARCHAR + CHECK in the contract
                    type(ct).__name__ == "Enum" and type(col.type).__name__ == "String"
                )
            ), f"{name}.{col.name}: {col.type!r} vs {ct!r}"


def test_events_seq_and_transition_guard(engine: Engine, services: Services) -> None:
    seed = seed_basic(engine)
    rid = insert_run(engine, seed)
    bus = Bus(services.redis_url)
    sub = redis.Redis.from_url(services.redis_url).pubsub()  # type: ignore[no-untyped-call]  # redis stub
    sub.subscribe(run_channel(str(rid)))
    sub.get_message(timeout=1)
    outbox = Outbox()
    with engine.begin() as conn:
        s1 = append_run_event(conn, rid, "warning", {"kind": "warning", "x": float("nan")}, outbox=outbox)
        s2 = append_run_event(conn, rid, "warning", {"kind": "warning"}, outbox=outbox)
        assert (s1, s2) == (1, 2)
        assert transition(conn, rid, from_statuses=["running"], to="failed", outbox=outbox) is False
        assert transition(
            conn,
            rid,
            from_statuses=["queued"],
            to="preparing",
            outbox=outbox,
            reason="claimed",
            extra={"lease_owner": "w1"},
        )
        # guarded by lease owner
        assert (
            transition(
                conn, rid, from_statuses=["preparing"], to="running", outbox=outbox, lease_owner="other"
            )
            is False
        )
        assert transition(
            conn, rid, from_statuses=["preparing"], to="running", outbox=outbox, lease_owner="w1"
        )
    outbox.flush(bus)
    with engine.connect() as conn:
        rows = conn.execute(
            select(run_events).where(run_events.c.run_id == rid).order_by(run_events.c.seq)
        ).all()
        r = conn.execute(select(runs).where(runs.c.id == rid)).one()
    assert [e.seq for e in rows] == [1, 2, 3, 4]
    assert rows[0].data["x"] is None  # NaN sanitised for JSON
    assert rows[2].data["from"] == "queued" and rows[2].data["to"] == "preparing"
    assert r.status == "running" and r.last_event_seq == 4
    got: list[dict[str, Any]] = []
    deadline = time.time() + 5
    while len(got) < 4 and time.time() < deadline:
        msg = sub.get_message(timeout=0.5)
        if msg and msg["type"] == "message":
            got.append(json.loads(msg["data"]))
    assert [g["id"] for g in got] == [1, 2, 3, 4]
    assert got[2]["event"] == "status"


def test_upsert_metrics_replay_and_nan(engine: Engine) -> None:
    seed = seed_basic(engine)
    rid = insert_run(engine, seed)
    with engine.begin() as conn:
        upsert_metrics(conn, rid, 10, {"loss": 1.0, "lr": 1e-5}, utcnow())
        upsert_metrics(conn, rid, 10, {"loss": float("nan")}, utcnow())  # resume replays a step
    with engine.connect() as conn:
        rows = conn.execute(
            select(run_metrics.c.key, run_metrics.c.value).where(run_metrics.c.run_id == rid)
        ).all()
        vals = {str(r[0]): float(r[1]) for r in rows}
    assert vals["lr"] == 1e-5
    assert vals["loss"] != vals["loss"]  # NaN stored as PG double NaN


def test_jobs_protocol(engine: Engine) -> None:
    seed = seed_basic(engine)
    m = contract_metadata()
    from sqlalchemy.orm import Session

    with Session(engine) as s:
        for prio in (0, 5):
            s.add(
                m.Job(
                    workspace_id=seed.workspace_id,
                    kind=m.JobKind.ESTIMATE_RESOURCES,
                    resource=m.JobResource.GPU,
                    payload={"p": prio},
                    priority=prio,
                )
            )
        s.commit()
    with engine.begin() as conn:
        assert oldest_queued_age_s(conn, "gpu", ["estimate_resources"]) is not None
        j = claim_job(conn, resource="gpu", kinds=["estimate_resources"], worker_id="w1")
        assert j is not None and j.payload == {"p": 5} and j.attempts == 1
    # SKIP LOCKED: a concurrent claimer gets the other job
    with engine.begin() as c1, engine.begin() as c2:
        a = claim_job(c1, resource="gpu", kinds=["estimate_resources"], worker_id="w2")
        b = claim_job(c2, resource="gpu", kinds=["estimate_resources"], worker_id="w3")
        assert (a is None) != (b is None)
    with engine.begin() as conn:
        assert heartbeat_job(conn, j.id, "w1", progress=0.5)
        assert not heartbeat_job(conn, j.id, "intruder")
        assert finish_job(conn, j.id, "w1", status="succeeded", result={"ok": True})
        row = conn.execute(text("SELECT status, progress, result FROM jobs WHERE id=:i"), {"i": j.id}).one()
    assert row.status == "succeeded" and row.progress == 1.0 and row.result == {"ok": True}


def test_object_store_roundtrip(services: Services, tmp_path: Path) -> None:
    st = ObjectStore(
        endpoint_url=services.s3_endpoint,
        access_key=services.s3_access_key,
        secret_key=services.s3_secret_key,
        max_retries=2,
    )
    src = tmp_path / "src"
    (src / "a" / "b").mkdir(parents=True)
    (src / "a" / "b" / "x.bin").write_bytes(b"x" * 1000)
    (src / "y.txt").write_text("y")
    pre = f"t/{uuid.uuid4()}"
    assert st.upload_dir(src, "hibiscus-artifacts", pre) == 1001
    dst = tmp_path / "dst"
    assert st.download_prefix("hibiscus-artifacts", pre, dst) == 1001
    assert (dst / "a" / "b" / "x.bin").read_bytes() == b"x" * 1000
    assert st.get_bytes("hibiscus-artifacts", f"{pre}/y.txt") == b"y"
    assert st.delete_prefix("hibiscus-artifacts", pre) == 2
    assert not st.exists("hibiscus-artifacts", f"{pre}/y.txt")
    with pytest.raises(StorageError):
        st.get_bytes("hibiscus-artifacts", f"{pre}/missing")
    assert parse_s3_uri("s3://b/k/x") == ("b", "k/x")
    with pytest.raises(ValueError, match="not an s3 uri"):
        parse_s3_uri("http://x")


def test_object_store_retries_then_storage_error(tmp_path: Path) -> None:
    st = ObjectStore(endpoint_url="http://127.0.0.1:1", access_key="a", secret_key="b", max_retries=2)  # noqa: S106
    f = tmp_path / "f"
    f.write_text("x")
    with pytest.raises(StorageError, match="after 2 attempts"):
        st.upload_file(f, "bucket", "k")


def test_with_retry_survives_transient_errors() -> None:
    from sqlalchemy.exc import OperationalError

    calls = {"n": 0}

    def flaky() -> int:
        calls["n"] += 1
        if calls["n"] < 3:
            raise OperationalError("SELECT 1", {}, Exception("conn reset"))
        return 7

    assert with_retry(flaky, budget_s=10) == 7
    with pytest.raises(ValueError, match="not transient"):
        with_retry(lambda: (_ for _ in ()).throw(ValueError("not transient")), budget_s=10)


def test_bus_swallows_redis_errors() -> None:
    b = Bus("redis://127.0.0.1:1/0")
    t = threading.Thread(target=b.publish_run, args=("r", "log", {"x": 1}))
    t.start()
    t.join(timeout=10)
    assert not t.is_alive()
