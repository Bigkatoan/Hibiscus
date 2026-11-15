"""SSE (real uvicorn on a loopback port 18100-18199), logs Range, models download / files."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import socket
import threading
import time
import uuid
import zipfile
from collections.abc import Iterator
from typing import Any

import boto3
import httpx
import pytest
import redis
import uvicorn
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import models as m
from tests.runs.conftest import (
    PrincipalHolder,
    Services,
    World,
    check,
    make_app,
    make_principal,
    problem,
    run_body,
)


def _free_port() -> int:
    for port in range(18100, 18200):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("no free port in 18100-18199")


@pytest.fixture
def live_server(services: Services, holder: PrincipalHolder, world: World) -> Iterator[str]:
    app = make_app(holder, services)  # uvicorn runs the app's own lifespan
    port = _free_port()
    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    server = uvicorn.Server(cfg)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/api/v1"
    server.should_exit = True
    t.join(timeout=10)


def _parse_sse(raw: str) -> list[dict[str, Any]]:
    out = []
    for block in raw.split("\n\n"):
        ev: dict[str, Any] = {}
        for line in block.splitlines():
            k, _, v = line.partition(": ")
            if k in ("id", "event", "data", "retry"):
                ev[k] = v
        if ev:
            out.append(ev)
    return out


def _sse_collect(url: str, headers: dict[str, str], until: str, timeout: float = 20) -> list[dict[str, Any]]:
    buf = ""
    with httpx.Client(timeout=timeout) as c, c.stream("GET", url, headers=headers) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache" and r.headers["x-accel-buffering"] == "no"
        start = time.time()
        for chunk in r.iter_text():
            buf += chunk
            if f"event: {until}" in buf or time.time() - start > timeout:
                break
    return _parse_sse(buf)


def test_sse_replay_live_heartbeat_end(
    live_server: str, world: World, services: Services, sync_engine: Any
) -> None:
    r = httpx.post(f"{live_server}/runs", json=run_body(world))
    rid = check(r, "/runs", "POST")["id"]
    # persisted backlog: seq 1 (queued) + a metrics event, then replay from Last-Event-ID
    with Session(sync_engine) as s:
        s.execute(text("UPDATE runs SET last_event_seq = 2 WHERE id=:r"), {"r": rid})
        s.add(
            m.RunEvent(
                run_id=uuid.UUID(rid),
                seq=2,
                type="metrics",
                attempt=1,
                data={"kind": "metrics", "step": 100, "values": {"loss": 1.5}, "ts": "2026-11-15T00:00:00Z"},
            )
        )
        s.commit()
    rc = redis.Redis.from_url(services.redis_url)

    def publish_later() -> None:
        time.sleep(1.5)
        # ephemeral progress (no id) + a duplicate persisted id (must be dropped) + a new persisted one
        rc.publish(
            f"hibiscus:run:{rid}",
            json.dumps(
                {
                    "event": "progress",
                    "id": None,
                    "data": {
                        "kind": "progress",
                        "step": 120,
                        "total_steps": 300,
                        "steps_per_s": 9.0,
                        "eta_s": 20.0,
                        "ts": "2026-11-15T00:00:01Z",
                    },
                }
            ),
        )
        rc.publish(f"hibiscus:run:{rid}", json.dumps({"event": "metrics", "id": 2, "data": {"dup": True}}))
        with Session(sync_engine) as s:
            s.execute(text("UPDATE runs SET status='cancelled', last_event_seq = 3 WHERE id=:r"), {"r": rid})
            data = {
                "kind": "status",
                "run_id": rid,
                "from": "queued",
                "to": "cancelled",
                "reason": "t",
                "error_code": None,
                "attempt": 0,
                "gpu_id": None,
                "ts": "2026-11-15T00:00:02Z",
            }
            s.add(m.RunEvent(run_id=uuid.UUID(rid), seq=3, type="status", attempt=0, data=data))
            s.commit()
        rc.publish(f"hibiscus:run:{rid}", json.dumps({"event": "status", "id": 3, "data": data}))

    threading.Thread(target=publish_later, daemon=True).start()
    evs = _sse_collect(f"{live_server}/runs/{rid}/events", {"Last-Event-ID": "1"}, until="end")
    assert evs[0] == {"retry": "3000"}
    kinds = [(e.get("event"), e.get("id")) for e in evs[1:]]
    assert ("metrics", "2") == kinds[0]  # replay starts after Last-Event-ID
    assert ("progress", None) in kinds and ("heartbeat", None) in kinds  # heartbeat every 1 s in tests
    assert ("status", "3") in kinds and kinds[-1] == ("end", None)
    assert sum(1 for k in kinds if k == ("metrics", "2")) == 1  # duplicate dropped
    assert json.loads(evs[-1]["data"]) == {"kind": "end", "final_status": "cancelled"}
    # include filter + already-terminal run ends right after the backlog
    evs = _sse_collect(f"{live_server}/runs/{rid}/events?after_seq=0&include=log", {}, until="end")
    assert [e.get("id") for e in evs if e.get("id")] == ["1", "2", "3"]


async def test_logs_range_download_and_search(
    client: httpx.AsyncClient, world: World, services: Services
) -> None:
    run = check(await client.post("/runs", json=run_body(world)), "/runs", "POST")
    rid = run["id"]
    empty = await client.get(f"/runs/{rid}/logs")
    assert empty.status_code == 200 and empty.text == ""
    s3 = boto3.client(
        "s3",
        endpoint_url=services.s3_endpoint,
        aws_access_key_id=services.s3_key,
        aws_secret_access_key=services.s3_secret,
        region_name="us-east-1",
    )
    a1 = "INFO 2026-11-15 10:00:00 ot_train.py:894 step:100 loss:1.0\nWARNING 2026-11-15 10:00:01 x.py:1 slow\n"  # noqa: E501
    a2 = "INFO 2026-11-15 11:00:00 ot_train.py:894 step:200 loss:0.5\nERROR 2026-11-15 11:00:01 y.py:2 Boom\n"
    s3.put_object(Bucket="hibiscus-artifacts", Key=f"runs/{rid}/logs/attempt-1.log", Body=a1.encode())
    s3.put_object(Bucket="hibiscus-artifacts", Key=f"runs/{rid}/logs/attempt-2.log", Body=a2.encode())
    full = await client.get(f"/runs/{rid}/logs", params={"download": True})
    assert full.status_code == 200 and full.text == a1 + a2
    assert full.headers["content-disposition"] == f'attachment; filename="run-{run["number"]}.log"'
    part = await client.get(f"/runs/{rid}/logs", headers={"Range": f"bytes={len(a1)}-"})
    assert part.status_code == 206 and part.text == a2
    assert part.headers["content-range"] == f"bytes {len(a1)}-{len(a1 + a2) - 1}/{len(a1 + a2)}"
    mid = await client.get(f"/runs/{rid}/logs", headers={"Range": f"bytes={len(a1) - 5}-{len(a1) + 3}"})
    assert mid.text == (a1 + a2)[len(a1) - 5 : len(a1) + 4]
    problem(
        await client.get(f"/runs/{rid}/logs", headers={"Range": "bytes=99999-"}), 416, "range_not_satisfiable"
    )
    res = check(
        await client.get(f"/runs/{rid}/logs/search", params={"q": "LOSS"}), "/runs/{run_id}/logs/search"
    )
    assert [(i["line_no"], i["attempt"]) for i in res["items"]] == [(1, 1), (3, 2)]
    assert res["items"][1]["byte_offset"] == len(a1)
    res = check(
        await client.get(f"/runs/{rid}/logs/search", params={"q": "boom", "level": "error"}),
        "/runs/{run_id}/logs/search",
    )
    assert len(res["items"]) == 1
    p1 = check(
        await client.get(f"/runs/{rid}/logs/search", params={"q": "20", "limit": 1}),
        "/runs/{run_id}/logs/search",
    )
    p2 = check(
        await client.get(
            f"/runs/{rid}/logs/search", params={"q": "20", "limit": 1, "cursor": p1["next_cursor"]}
        ),
        "/runs/{run_id}/logs/search",
    )
    assert p1["items"][0]["line_no"] < p2["items"][0]["line_no"]


def _bundle_zip(name: str) -> tuple[bytes, dict[str, Any]]:
    files = {
        "pretrained_model/config.json": b'{"type": "act"}',
        "pretrained_model/model.safetensors": bytes(range(256)) * 400,
        "MODEL_CARD.md": b"# card\n" * 50,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for p, data in files.items():
            comp = zipfile.ZIP_STORED if p.endswith(".safetensors") else zipfile.ZIP_DEFLATED
            z.writestr(f"{name}/{p}", data, compress_type=comp)
    manifest = {
        "schema_version": "1",
        "bundle_name": name,
        "files": [
            {"path": p, "size": len(d), "sha256": hashlib.sha256(d).hexdigest()} for p, d in files.items()
        ],
    }
    return buf.getvalue(), manifest


async def test_models_api(
    client: httpx.AsyncClient, world: World, services: Services, sync_engine: Any, holder: PrincipalHolder
) -> None:
    run = check(await client.post("/runs", json=run_body(world)), "/runs", "POST")
    rid = uuid.UUID(run["id"])
    name = "so101_picknplace_20261114_act-r1-step300"
    blob, manifest = _bundle_zip(name)
    mid = uuid.uuid4()
    key = f"models/{mid}/{name}.zip"
    boto3.client(
        "s3",
        endpoint_url=services.s3_endpoint,
        aws_access_key_id=services.s3_key,
        aws_secret_access_key=services.s3_secret,
        region_name="us-east-1",
    ).put_object(Bucket="hibiscus-artifacts", Key=key, Body=blob)
    with Session(sync_engine) as s:
        ck = m.Checkpoint(
            run_id=rid,
            step=300,
            storage_prefix="s3://x/",
            size_bytes=1,
            has_training_state=True,
            is_last=True,
        )
        s.add(ck)
        s.flush()
        s.add(
            m.Model(
                id=mid,
                workspace_id=world.workspace_id,
                run_id=rid,
                checkpoint_id=ck.id,
                name=name,
                policy_type="act",
                step=300,
                status=m.ModelStatus.READY,
                bundle_uri=f"s3://hibiscus-artifacts/{key}",
                bundle_sha256=hashlib.sha256(blob).hexdigest(),
                bundle_size_bytes=len(blob),
                manifest=manifest,
                onnx_status=m.OnnxStatus.PASSED,
                created_by=world.user_id,
            )
        )
        s.commit()
    page = check(await client.get("/models", params={"workspace_id": str(world.workspace_id)}), "/models")
    assert [x["id"] for x in page["items"]] == [str(mid)] and page["items"][0]["run_number"] == 1
    check(await client.get(f"/models/{mid}"), "/models/{model_id}")
    d = await client.get(f"/models/{mid}/download")
    assert (
        d.status_code == 200
        and d.content == blob
        and d.headers["etag"] == f'"{hashlib.sha256(blob).hexdigest()}"'
    )
    part = await client.get(f"/models/{mid}/download", headers={"Range": "bytes=10-19"})
    assert part.status_code == 206 and part.content == blob[10:20]
    stale = await client.get(f"/models/{mid}/download", headers={"Range": "bytes=10-19", "If-Range": '"old"'})
    assert stale.status_code == 200 and stale.content == blob
    files = check(await client.get(f"/models/{mid}/files"), "/models/{model_id}/files")
    assert files["bundle_name"] == name
    for f in manifest["files"]:
        got = await client.get(f"/models/{mid}/files/{f['path']}")
        assert got.status_code == 200 and hashlib.sha256(got.content).hexdigest() == f["sha256"]
    st = await client.get(
        f"/models/{mid}/files/pretrained_model/model.safetensors", headers={"Range": "bytes=256-511"}
    )
    assert st.status_code == 206 and st.content == bytes(range(256))
    df = await client.get(f"/models/{mid}/files/MODEL_CARD.md", headers={"Range": "bytes=7-13"})
    assert df.status_code == 206 and df.content == b"# card\n"
    problem(await client.get(f"/models/{mid}/files/etc/passwd"), 404, "not_found")
    # export of the same checkpoint returns the existing model (200)
    ex = await client.post(f"/runs/{rid}/checkpoints/300/export")
    assert ex.status_code == 200 and check(ex, "/runs/{run_id}/checkpoints/{step}/export", "POST")[
        "id"
    ] == str(mid)
    problem(await client.post(f"/runs/{rid}/checkpoints/7/export"), 404, "checkpoint_not_found")
    ev = check(
        await client.post(f"/runs/{rid}/checkpoints/300/eval"),
        "/runs/{run_id}/checkpoints/{step}/eval",
        "POST",
    )
    assert ev["kind"] == "eval_checkpoint"
    problem(await client.post(f"/runs/{rid}/checkpoints/300/eval"), 409, "conflict")
    problem(await client.get(f"/runs/{rid}/checkpoints/300/eval-result"), 404, "not_found")
    # QC-backend-02: no worker runs push_model_hub by default -> 501, and no job / audit row is made
    off = problem(
        await client.post(f"/models/{mid}/push-hub", json={"repo_id": "me/x"}), 501, "service_unavailable"
    )
    assert off["params"] == {"feature": "push_model_hub", "reason": "feature_disabled"}
    with Session(sync_engine) as s:
        assert s.scalar(text("SELECT count(*) FROM jobs WHERE model_id = :i"), {"i": mid}) == 0
        assert (
            s.scalar(
                text(
                    "SELECT count(*) FROM audit_events WHERE action = 'model.pushed_hub' AND target_id = :i"
                ),
                {"i": str(mid)},
            )
            == 0
        )
    client.app.state.runs.settings.hub_push_enabled = True  # type: ignore[attr-defined]
    problem(await client.post(f"/models/{mid}/push-hub", json={"repo_id": "me/x"}), 409, "hf_token_missing")
    problem(await client.post(f"/models/{mid}/push-hub", json={"repo_id": "bad id"}), 422, "hub_repo_invalid")
    v = check(await client.post(f"/models/{mid}/verify"), "/models/{model_id}/verify", "POST")
    assert v["kind"] == "export_model"
    ren = check(await client.patch(f"/models/{mid}", json={"name": "nice"}), "/models/{model_id}", "PATCH")
    assert ren["name"] == "nice"
    holder.p = make_principal(
        user_id=world.user_id,
        workspace_ids_roles={world.workspace_id: "member"},
        auth_method="pat",
        token_scopes=frozenset({"models:read"}),
        token_workspace_id=world.workspace_id,
    )
    assert (await client.get(f"/models/{mid}/download")).status_code == 200
    problem(await client.delete(f"/models/{mid}"), 403, "insufficient_scope")
    holder.p = world.principal
    assert (await client.delete(f"/models/{mid}")).status_code == 204
    problem(await client.get(f"/models/{mid}"), 404, "not_found")
    with Session(sync_engine) as s:
        s.execute(text("UPDATE models SET deleted_at = NULL, status='building' WHERE id=:i"), {"i": mid})
        s.commit()
    problem(await client.get(f"/models/{mid}/download"), 409, "model_not_ready")
    await asyncio.sleep(0)
