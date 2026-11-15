"""Chunked upload API against real Postgres + MinIO (ADR-0010)."""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.datasets.api_uploads import expire_stale_uploads, plan_parts
from app.db.models import AuditEvent, Job, Quota, UploadSession, UploadStatus, WorkspaceRole
from tests.datasets.conftest import Actor, assert_contract

MIB = 1024 * 1024


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


async def _init(client: httpx.AsyncClient, a: Actor, data: bytes, **kw: Any) -> httpx.Response:
    body = {
        "workspace_id": str(a.workspace_id),
        "new_dataset_name": kw.pop("name", "Pick n place"),
        "filename": kw.pop("filename", "Picknplace.tar"),
        "size": len(data),
        "sha256": _sha(data),
        "part_size": 5 * MIB,
        **kw,
    }
    return await client.post("/uploads", json=body, headers=a.h)


async def _put(
    client: httpx.AsyncClient,
    a: Actor,
    uid: str,
    n: int,
    chunk: bytes,
    sha: str | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    h = {
        **a.h,
        "X-Content-SHA256": sha or _sha(chunk),
        "Content-Type": "application/octet-stream",
        **(headers or {}),
    }
    return await client.put(f"/uploads/{uid}/parts/{n}", content=chunk, headers=h)


def test_plan_parts() -> None:
    assert plan_parts(1, 64 * MIB) == (64 * MIB, 1)
    assert plan_parts(11 * MIB, 1) == (5 * MIB, 3)
    assert plan_parts(11 * MIB, 999 * MIB) == (64 * MIB, 1)
    size = 10000 * 5 * MIB + 1
    ps, pc = plan_parts(size, 5 * MIB)
    assert pc <= 10000 and ps % MIB == 0 and ps * pc >= size


async def test_full_upload_resume_and_complete(
    client: httpx.AsyncClient, make_actor: Any, s3_sync: Any, sm: async_sessionmaker[AsyncSession]
) -> None:
    a = await make_actor()
    data = os.urandom(12 * MIB + 12345)
    r = await _init(client, a, data)
    assert r.status_code == 201, r.text
    assert_contract(r, "/uploads", "post")
    up = r.json()
    assert up["part_size"] == 5 * MIB and up["part_count"] == 3 and up["status"] == "active"
    uid = up["id"]

    # Natural resume: identical init returns the same session with 200.
    r2 = await _init(client, a, data)
    assert r2.status_code == 200 and r2.json()["id"] == uid
    assert_contract(r2, "/uploads", "post")

    chunks = [data[0 : 5 * MIB], data[5 * MIB : 10 * MIB], data[10 * MIB :]]
    r = await _put(client, a, uid, 1, chunks[0])
    assert r.status_code == 200, r.text
    assert_contract(r, "/uploads/{upload_id}/parts/{part_number}", "put")
    assert r.json()["sha256"] == _sha(chunks[0])

    # Corrupted body for part 2: rejected, nothing recorded.
    r = await _put(client, a, uid, 2, chunks[1], sha=_sha(b"other"))
    assert r.status_code == 422 and r.json()["code"] == "upload_part_checksum_mismatch"
    assert_contract(r, "/uploads/{upload_id}/parts/{part_number}", "put")
    # Corrupted re-upload of a GOOD part never replaces it.
    r = await _put(client, a, uid, 1, b"x" * (5 * MIB), sha=_sha(b"nope"))
    assert r.status_code == 422

    # Complete with missing parts -> 409 upload_incomplete + missing_parts.
    r = await client.post(f"/uploads/{uid}/complete", headers=a.h)
    assert r.status_code == 409 and r.json()["code"] == "upload_incomplete"
    assert r.json()["missing_parts"] == [2, 3]
    assert_contract(r, "/uploads/{upload_id}/complete", "post")

    # Resume: GET shows received parts; send the missing ones (and re-send 1 = idempotent replace).
    g = await client.get(f"/uploads/{uid}", headers=a.h)
    assert_contract(g, "/uploads/{upload_id}")
    assert [p["part_number"] for p in g.json()["parts"]] == [1] and g.json()["bytes_received"] == 5 * MIB
    for n in (3, 2, 1):
        r = await _put(client, a, uid, n, chunks[n - 1])
        assert r.status_code == 200, r.text

    r = await client.post(f"/uploads/{uid}/complete", headers=a.h)
    assert r.status_code == 202, r.text
    assert_contract(r, "/uploads/{upload_id}/complete", "post")
    body = r.json()
    assert body["upload"]["status"] == "completed" and body["version"]["version"] == 1
    assert body["version"]["status"] == "pending" and body["version"]["source"] == "upload"
    assert body["dataset"]["name"] == "Pick n place" and body["dataset"]["slug"] == "pick-n-place"
    assert body["dataset"]["latest_version"]["id"] == body["version"]["id"]
    assert body["job"]["kind"] == "validate_dataset" and body["job"]["status"] == "queued"

    # Idempotent completion.
    again = await client.post(f"/uploads/{uid}/complete", headers=a.h)
    assert again.status_code == 202 and again.json()["version"]["id"] == body["version"]["id"]

    # The object in MinIO is byte-identical to the original file.
    async with sm() as db:
        s = await db.get(UploadSession, uuid.UUID(uid))
        assert s is not None
        obj = s3_sync.get_object(Bucket=s.s3_bucket, Key=s.s3_key)["Body"].read()
        jobs = (
            (await db.execute(select(Job).where(Job.dataset_version_id == uuid.UUID(body["version"]["id"]))))
            .scalars()
            .all()
        )
        actions = (
            (await db.execute(select(AuditEvent.action).where(AuditEvent.workspace_id == a.workspace_id)))
            .scalars()
            .all()
        )
    assert _sha(obj) == _sha(data)
    assert len(jobs) == 1 and jobs[0].payload["upload_id"] == uid and jobs[0].resource.value == "cpu"
    # SEC-input-3: archive expansion is capped at the storage quota left (default 200 GiB, empty ws)
    assert jobs[0].payload["max_bytes"] == 200 * 1024**3
    assert sorted(actions) == ["dataset.created", "dataset_version.created"]

    # Parts on a completed session are refused.
    r = await _put(client, a, uid, 1, chunks[0])
    assert r.status_code == 409 and r.json()["code"] == "upload_not_active"

    # Second upload into the existing dataset -> version 2.
    data2 = os.urandom(1000)
    r = await client.post(
        "/uploads",
        json={
            "workspace_id": str(a.workspace_id),
            "dataset_id": body["dataset"]["id"],
            "filename": "x.zip",
            "size": len(data2),
            "sha256": _sha(data2),
        },
        headers=a.h,
    )
    assert r.status_code == 201 and r.json()["archive_format"] == "zip" and r.json()["part_count"] == 1
    uid2 = r.json()["id"]
    assert (await _put(client, a, uid2, 1, data2)).status_code == 200
    r = await client.post(f"/uploads/{uid2}/complete", headers=a.h)
    assert r.status_code == 202 and r.json()["version"]["version"] == 2

    lst = await client.get(
        "/uploads", params={"workspace_id": str(a.workspace_id), "status": "completed"}, headers=a.h
    )
    assert_contract(lst, "/uploads")
    assert {u["id"] for u in lst.json()["items"]} == {uid, uid2}


async def test_part_validation_errors(client: httpx.AsyncClient, make_actor: Any) -> None:
    a = await make_actor()
    data = os.urandom(6 * MIB)
    uid = (await _init(client, a, data)).json()["id"]
    path = "/uploads/{upload_id}/parts/{part_number}"
    r = await _put(client, a, uid, 3, data[:MIB])
    assert r.status_code == 422 and r.json()["code"] == "upload_part_out_of_range"
    assert_contract(r, path, "put")
    r = await _put(client, a, uid, 1, data[:MIB])
    assert r.status_code == 422 and r.json()["code"] == "upload_part_size_invalid"
    assert r.json()["params"] == {"expected": 5 * MIB, "actual": MIB}
    r = await _put(client, a, uid, 2, data[5 * MIB :], sha="NOT-HEX")
    assert r.status_code == 422 and r.json()["code"] == "validation_failed"
    r = await client.put(
        f"/uploads/{uid}/parts/2",
        content=data[5 * MIB :],
        headers={**a.h, "X-Content-SHA256": _sha(data[5 * MIB :]), "Content-Length": str(65 * MIB)},
    )
    # the core body-limit middleware answers before the handler (generic catalogue code; the CLI
    # and its fake server expect ``payload_too_large`` here too)
    assert r.status_code == 413 and r.json()["code"] == "payload_too_large"
    assert_contract(r, path, "put")


async def test_init_validation_quota_and_names(
    client: httpx.AsyncClient, make_actor: Any, sm: async_sessionmaker[AsyncSession]
) -> None:
    a = await make_actor()
    data = b"x" * 100
    r = await _init(client, a, data, filename="data.7z")
    assert r.status_code == 422 and r.json()["code"] == "archive_format_unsupported"
    assert_contract(r, "/uploads", "post")
    r = await client.post(
        "/uploads",
        json={"workspace_id": str(a.workspace_id), "filename": "a.zip", "size": 1, "sha256": "0" * 64},
        headers=a.h,
    )
    assert r.status_code == 422 and r.json()["code"] == "validation_failed"
    r = await client.post(
        "/uploads",
        json={
            "workspace_id": str(a.workspace_id),
            "new_dataset_name": "n",
            "filename": "a.zip",
            "size": 1,
            "sha256": "0" * 64,
            "evil": 1,
        },
        headers=a.h,
    )
    assert r.status_code == 422
    # name taken
    assert (
        await client.post(
            "/datasets", json={"workspace_id": str(a.workspace_id), "name": "Taken"}, headers=a.h
        )
    ).status_code == 201
    r = await _init(client, a, data, name="taken")
    assert r.status_code == 409 and r.json()["code"] == "dataset_name_taken"
    # quota: per-upload limit and storage
    async with sm() as db:
        db.add(Quota(workspace_id=a.workspace_id, user_id=None, max_upload_bytes=50, storage_bytes=10**9))
        await db.commit()
    r = await _init(client, a, data, name="q1")
    assert r.status_code == 403 and r.json()["code"] == "quota_exceeded"
    assert_contract(r, "/uploads", "post")
    async with sm() as db:
        await db.execute(
            update(Quota)
            .where(Quota.workspace_id == a.workspace_id)
            .values(max_upload_bytes=10**9, storage_bytes=150)
        )
        await db.commit()
    r1 = await _init(client, a, data, name="q2")
    assert r1.status_code == 201
    r2 = await _init(client, a, b"y" * 100, name="q3")  # 100 active + 100 > 150
    assert r2.status_code == 403 and r2.json()["params"]["kind"] == "storage_bytes"


async def test_access_rules(client: httpx.AsyncClient, make_actor: Any) -> None:
    owner = await make_actor()
    viewer = await make_actor(WorkspaceRole.VIEWER, owner.workspace_id)
    member = await make_actor(WorkspaceRole.MEMBER, owner.workspace_id)
    stranger = await make_actor()
    data = os.urandom(100)
    r = await _init(client, viewer, data)
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    r = await _init(client, stranger, data, workspace_id=str(owner.workspace_id))
    assert r.status_code == 404 and r.json()["code"] == "not_found"  # no existence oracle
    uid = (await _init(client, owner, data)).json()["id"]
    # other members (non-admin) and strangers cannot see someone else's session -> 404
    for who in (member, stranger):
        g = await client.get(f"/uploads/{uid}", headers=who.h)
        assert g.status_code == 404 and g.json()["code"] == "not_found"
        assert_contract(g, "/uploads/{upload_id}")
    # PAT: scope + workspace binding
    r = await client.post(
        "/uploads",
        json={
            "workspace_id": str(owner.workspace_id),
            "new_dataset_name": "p",
            "filename": "a.tar",
            "size": 1,
            "sha256": "0" * 64,
        },
        headers=await owner.pat("datasets:read"),
    )
    assert r.status_code == 403 and r.json()["code"] == "insufficient_scope"
    r = await client.post(
        "/uploads",
        json={
            "workspace_id": str(owner.workspace_id),
            "new_dataset_name": "p",
            "filename": "a.tar",
            "size": 1,
            "sha256": "0" * 64,
        },
        headers=await owner.pat("datasets:write", uuid.uuid4()),
    )
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    r = await client.post(
        "/uploads",
        json={
            "workspace_id": str(owner.workspace_id),
            "new_dataset_name": "pat-up",
            "filename": "a.tar",
            "size": 1,
            "sha256": "0" * 64,
        },
        headers=await owner.pat("datasets:write"),
    )
    assert r.status_code == 201
    unauth = await client.get(f"/uploads/{uid}")
    assert unauth.status_code == 401


async def test_abort_and_expiry(
    client: httpx.AsyncClient, make_actor: Any, sm: async_sessionmaker[AsyncSession], app: Any
) -> None:
    a = await make_actor()
    data = os.urandom(100)
    uid = (await _init(client, a, data)).json()["id"]
    r = await client.delete(f"/uploads/{uid}", headers=a.h)
    assert r.status_code == 204
    assert (await client.delete(f"/uploads/{uid}", headers=a.h)).status_code == 204  # idempotent
    assert (await _put(client, a, uid, 1, data)).json()["code"] == "upload_not_active"
    r = await client.post(f"/uploads/{uid}/complete", headers=a.h)
    assert r.status_code == 409 and r.json()["code"] == "upload_not_active"

    uid2 = (await _init(client, a, os.urandom(200), name="exp")).json()["id"]
    async with sm() as db:
        await db.execute(
            update(UploadSession)
            .where(UploadSession.id == uuid.UUID(uid2))
            .values(expires_at=UploadSession.created_at - __import__("datetime").timedelta(days=1))
        )
        await db.commit()
    g = await client.get(f"/uploads/{uid2}", headers=a.h)
    assert g.json()["status"] == "expired"
    async with sm() as db:
        n = await expire_stale_uploads(db, app.state.datasets_storage)
        assert n >= 1
        s = await db.get(UploadSession, uuid.UUID(uid2))
        assert s is not None and s.status == UploadStatus.EXPIRED
    # completed sessions cannot be aborted
    data3 = os.urandom(10)
    uid3 = (await _init(client, a, data3, name="done")).json()["id"]
    await _put(client, a, uid3, 1, data3)
    await client.post(f"/uploads/{uid3}/complete", headers=a.h)
    r = await client.delete(f"/uploads/{uid3}", headers=a.h)
    assert r.status_code == 409
    assert_contract(r, "/uploads/{upload_id}", "delete")
