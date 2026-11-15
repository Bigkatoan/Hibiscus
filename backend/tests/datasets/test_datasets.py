"""Datasets / versions API (CRUD, access rules, import, merge, revalidate, delete) - real Postgres."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.datasets.api_datasets import downsample, media_object_key, parse_range
from app.datasets.service import slugify
from app.db.models import (
    Dataset,
    DatasetSource,
    DatasetVersion,
    DatasetVersionStatus,
    Job,
    Quota,
    Run,
    RunStatus,
    WorkspaceRole,
)
from tests.datasets.conftest import Actor, assert_contract

FEATURES = {
    "action": {"dtype": "float32", "shape": [6], "names": ["a", "b", "c", "d", "e", "f"]},
    "observation.state": {"dtype": "float32", "shape": [6], "names": ["a", "b", "c", "d", "e", "f"]},
}


async def _ds(client: httpx.AsyncClient, a: Actor, name: str = "Pick place") -> dict[str, Any]:
    r = await client.post("/datasets", json={"workspace_id": str(a.workspace_id), "name": name}, headers=a.h)
    assert r.status_code == 201, r.text
    return dict(r.json())


async def _ready_version(
    sm: async_sessionmaker[AsyncSession], dataset_id: str, n: int = 1, **kw: Any
) -> uuid.UUID:
    async with sm() as db:
        v = DatasetVersion(
            dataset_id=uuid.UUID(dataset_id),
            version=n,
            status=kw.pop("status", DatasetVersionStatus.READY),
            source=DatasetSource.UPLOAD,
            content_hash=kw.pop("content_hash", uuid.uuid4().hex * 2),
            storage_prefix="s3://hibiscus-datasets/x/",
            total_episodes=2,
            total_frames=100,
            fps=30.0,
            features=kw.pop("features", FEATURES),
            robot_type=kw.pop("robot_type", "so_follower"),
            camera_keys=[],
            size_bytes=1000,
            **kw,
        )
        db.add(v)
        await db.flush()
        ds = await db.get(Dataset, uuid.UUID(dataset_id))
        assert ds is not None
        ds.latest_version_id = v.id
        await db.commit()
        return v.id


def test_pure_helpers() -> None:
    assert slugify("Pick & Place — Đợt 1!") == "pick-place-dot-1"
    assert slugify("///") == "dataset"
    assert parse_range("bytes=0-9", 100) == (0, 9)
    assert parse_range("bytes=90-", 100) == (90, 99)
    assert parse_range("bytes=90-500", 100) == (90, 99)
    assert parse_range(None, 10) is None
    assert parse_range("bytes=1-2,4-5", 10) is None
    d = {"timestamps": list(range(10)), "series": [{"values": list(range(10))}]}
    out = downsample(d, 3)
    assert out["timestamps"] == [0, 4, 9] and out["series"][0]["values"] == [0, 4, 9]
    ds = Dataset(id=uuid.uuid4(), workspace_id=uuid.uuid4())
    v = DatasetVersion(id=uuid.uuid4())
    assert media_object_key(ds, v, "videos/cam/chunk-000/file-000.mp4").endswith(
        f"{v.id}/videos/cam/chunk-000/file-000.mp4"
    )
    assert media_object_key(ds, v, "previews/cam/episode_000001.jpg").endswith(
        f"{v.id}.derived/previews/cam/episode_000001.jpg"
    )
    import pytest

    from app.core.errors import ProblemError

    for bad in (
        "../meta/info.json",
        "videos/../../x.mp4",
        "data/chunk-000/file-000.parquet",
        "videos/a.txt",
        "/meta/info.json",
        "meta//info.json",
        "meta\\info.json",
    ):
        with pytest.raises(ProblemError):
            media_object_key(ds, v, bad)


async def test_dataset_crud_and_listing(client: httpx.AsyncClient, make_actor: Any) -> None:
    a = await make_actor()
    created = await _ds(client, a, "Alpha set")
    assert (
        created["slug"] == "alpha-set" and created["version_count"] == 0 and created["latest_version"] is None
    )
    assert created["created_by"]["display_name"] == "Tester"
    r = await client.post(
        "/datasets", json={"workspace_id": str(a.workspace_id), "name": "ALPHA  set"}, headers=a.h
    )
    assert r.status_code == 409 and r.json()["code"] == "dataset_name_taken"
    assert_contract(r, "/datasets", "post")
    for i in range(3):
        await _ds(client, a, f"beta {i}")
    r = await client.get("/datasets", params={"workspace_id": str(a.workspace_id), "limit": 2}, headers=a.h)
    assert_contract(r, "/datasets")
    page1 = r.json()
    assert len(page1["items"]) == 2 and page1["next_cursor"]
    r = await client.get(
        "/datasets",
        params={"workspace_id": str(a.workspace_id), "limit": 2, "cursor": page1["next_cursor"]},
        headers=a.h,
    )
    page2 = r.json()
    names = [d["name"] for d in page1["items"] + page2["items"]]
    assert len(names) == 4 and len(set(names)) == 4 and page2["next_cursor"] is None
    r = await client.get("/datasets", params={"workspace_id": str(a.workspace_id), "q": "BETA"}, headers=a.h)
    assert len(r.json()["items"]) == 3
    r = await client.get(
        "/datasets", params={"workspace_id": str(a.workspace_id), "cursor": "garbage"}, headers=a.h
    )
    assert r.status_code == 400

    r = await client.patch(
        f"/datasets/{created['id']}", json={"name": "Gamma", "description": "d"}, headers=a.h
    )
    assert r.status_code == 200 and r.json()["slug"] == "gamma" and r.json()["description"] == "d"
    assert_contract(r, "/datasets/{dataset_id}", "patch")
    r = await client.patch(f"/datasets/{created['id']}", json={}, headers=a.h)
    assert r.status_code == 422
    r = await client.patch(f"/datasets/{created['id']}", json={"name": "beta 1"}, headers=a.h)
    assert r.status_code == 409
    r = await client.get(f"/datasets/{created['id']}", headers=a.h)
    assert_contract(r, "/datasets/{dataset_id}")


async def test_access_matrix(client: httpx.AsyncClient, make_actor: Any) -> None:
    owner = await make_actor()
    viewer = await make_actor(WorkspaceRole.VIEWER, owner.workspace_id)
    member = await make_actor(WorkspaceRole.MEMBER, owner.workspace_id)
    stranger = await make_actor()
    ds = await _ds(client, owner)
    # read: viewer ok, stranger 404 (no existence oracle) - also when naming the workspace (same as
    # core ensure_role: a non-member must not learn that the workspace exists)
    assert (await client.get(f"/datasets/{ds['id']}", headers=viewer.h)).status_code == 200
    r = await client.get(f"/datasets/{ds['id']}", headers=stranger.h)
    assert r.status_code == 404
    assert_contract(r, "/datasets/{dataset_id}")
    r = await client.get("/datasets", params={"workspace_id": str(owner.workspace_id)}, headers=stranger.h)
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    assert_contract(r, "/datasets")
    r = await client.post(
        "/datasets", json={"workspace_id": str(owner.workspace_id), "name": "s"}, headers=stranger.h
    )
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    assert_contract(r, "/datasets", "post")
    r = await client.get("/uploads", params={"workspace_id": str(owner.workspace_id)}, headers=stranger.h)
    assert r.status_code == 404
    assert_contract(r, "/uploads")
    # ... indistinguishable from a workspace id that does not exist at all
    r = await client.get("/datasets", params={"workspace_id": str(uuid.uuid4())}, headers=stranger.h)
    assert r.status_code == 404
    # write: viewer forbidden
    r = await client.post(
        "/datasets", json={"workspace_id": str(owner.workspace_id), "name": "v"}, headers=viewer.h
    )
    assert r.status_code == 403
    r = await client.patch(f"/datasets/{ds['id']}", json={"name": "zz"}, headers=viewer.h)
    assert r.status_code == 403
    # PAT: read scope can list, cannot write; other workspace -> 403 on list, 404 on item
    r = await client.get(
        "/datasets",
        params={"workspace_id": str(owner.workspace_id)},
        headers=await owner.pat("datasets:read"),
    )
    assert r.status_code == 200
    r = await client.get(
        "/datasets", params={"workspace_id": str(owner.workspace_id)}, headers=await owner.pat("runs:read")
    )
    assert r.status_code == 403 and r.json()["code"] == "insufficient_scope"
    r = await client.get(
        f"/datasets/{ds['id']}", headers=await owner.pat("datasets:write", stranger.workspace_id)
    )
    assert r.status_code == 404
    r = await client.get(
        "/datasets",
        params={"workspace_id": str(owner.workspace_id)},
        headers=await owner.pat("datasets:read", stranger.workspace_id),
    )
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    # delete is cookie-only and creator/admin-only
    r = await client.delete(f"/datasets/{ds['id']}", headers=await owner.pat("datasets:write"))
    assert r.status_code == 403
    r = await client.delete(f"/datasets/{ds['id']}", headers=member.h)
    assert r.status_code == 403
    assert_contract(r, "/datasets/{dataset_id}", "delete")
    r = await client.delete(f"/datasets/{ds['id']}", headers=owner.h)
    assert r.status_code == 204
    assert (await client.get(f"/datasets/{ds['id']}", headers=owner.h)).status_code == 404


async def test_versions_list_get_delete_and_in_use(
    client: httpx.AsyncClient, make_actor: Any, sm: async_sessionmaker[AsyncSession]
) -> None:
    a = await make_actor()
    ds = await _ds(client, a)
    v1 = await _ready_version(sm, ds["id"], 1)
    v2 = await _ready_version(sm, ds["id"], 2)
    r = await client.get(f"/datasets/{ds['id']}/versions", params={"limit": 1}, headers=a.h)
    assert_contract(r, "/datasets/{dataset_id}/versions")
    assert [v["version"] for v in r.json()["items"]] == [2]
    r = await client.get(
        f"/datasets/{ds['id']}/versions", params={"cursor": r.json()["next_cursor"]}, headers=a.h
    )
    assert [v["version"] for v in r.json()["items"]] == [1] and r.json()["next_cursor"] is None
    r = await client.get(f"/dataset-versions/{v2}", headers=a.h)
    assert r.status_code == 200
    assert_contract(r, "/dataset-versions/{version_id}")
    body = r.json()
    assert body["state_dim"] == 6 and body["action_dim"] == 6 and body["joint_names"][0] == "a"
    d = (await client.get(f"/datasets/{ds['id']}", headers=a.h)).json()
    assert d["version_count"] == 2 and d["latest_version"]["version"] == 2

    # A non-terminal run uses v2 -> cannot delete it (nor the dataset).
    async with sm() as db:
        db.add(
            Run(
                workspace_id=a.workspace_id,
                number=1,
                name="r",
                created_by=a.user_id,
                dataset_version_id=v2,
                policy_type="act",
                config={},
                heldout_episodes=[],
                train_episodes=[0],
                seed=1,
                total_steps=10,
                status=RunStatus.RUNNING,
            )
        )
        await db.commit()
    r = await client.delete(f"/dataset-versions/{v2}", headers=a.h)
    assert r.status_code == 409 and r.json()["code"] == "dataset_in_use"
    assert_contract(r, "/dataset-versions/{version_id}", "delete")
    r = await client.delete(f"/datasets/{ds['id']}", headers=a.h)
    assert r.status_code == 409 and r.json()["code"] == "dataset_in_use"
    # v1 is free: delete it; latest stays v2.
    assert (await client.delete(f"/dataset-versions/{v1}", headers=a.h)).status_code == 204
    assert (await client.get(f"/dataset-versions/{v1}", headers=a.h)).status_code == 404
    d = (await client.get(f"/datasets/{ds['id']}", headers=a.h)).json()
    assert d["version_count"] == 1 and d["latest_version"]["version"] == 2


async def test_validation_report_and_revalidate(
    client: httpx.AsyncClient, make_actor: Any, sm: async_sessionmaker[AsyncSession]
) -> None:
    a = await make_actor()
    ds = await _ds(client, a)
    v = await _ready_version(sm, ds["id"], status=DatasetVersionStatus.VALIDATING, content_hash=None)
    assert (await client.get(f"/dataset-versions/{v}/validation", headers=a.h)).status_code == 404
    r = await client.post(f"/dataset-versions/{v}/validation", headers=a.h)
    assert r.status_code == 409
    assert_contract(r, "/dataset-versions/{version_id}/validation", "post")
    async with sm() as db:
        row = await db.get(DatasetVersion, v)
        assert row is not None
        row.status = DatasetVersionStatus.INVALID
        row.validate_report = {
            "dataset_version_id": str(v),
            "job_id": None,
            "validator_version": "0.1.0",
            "lerobot_version": "0.7.1",
            "summary": {"result": "failed", "errors": 1, "warnings": 0},
            "steps": [
                {"id": s, "status": "passed", "issues": []}
                for s in ("checksum", "unpack", "structure", "schema", "decode", "timestamps", "stats")
            ],
        }
        await db.commit()
    r = await client.get(f"/dataset-versions/{v}/validation", headers=a.h)
    assert r.status_code == 200
    assert_contract(r, "/dataset-versions/{version_id}/validation")
    r = await client.get(f"/dataset-versions/{v}", headers=a.h)
    assert r.json()["validation_summary"]["result"] == "failed"
    r = await client.post(f"/dataset-versions/{v}/validation", headers=a.h)
    assert r.status_code == 202
    assert_contract(r, "/dataset-versions/{version_id}/validation", "post")
    assert r.json()["kind"] == "validate_dataset" and r.json()["status"] == "queued"
    # a second request while one is queued -> 409
    assert (await client.post(f"/dataset-versions/{v}/validation", headers=a.h)).status_code == 409
    # preview not available while pending
    r = await client.get(f"/dataset-versions/{v}/preview", headers=a.h)
    assert r.status_code == 409 and r.json()["code"] == "dataset_version_not_ready"
    assert_contract(r, "/dataset-versions/{version_id}/preview")


async def test_import_hf(
    client: httpx.AsyncClient, make_actor: Any, sm: async_sessionmaker[AsyncSession]
) -> None:
    a = await make_actor()
    r = await client.post(
        "/datasets/import-hf",
        json={
            "workspace_id": str(a.workspace_id),
            "new_dataset_name": "hub ds",
            "hf_uri": "hf://lerobot/svla_so101_pickplace@main",
        },
        headers=a.h,
    )
    assert r.status_code == 202, r.text
    assert_contract(r, "/datasets/import-hf", "post")
    body = r.json()
    assert body["version"]["source"] == "hf_import" and body["job"]["kind"] == "import_hf_dataset"
    async with sm() as db:
        job = await db.get(Job, uuid.UUID(body["job"]["id"]))
        assert job is not None and job.payload["hf_uri"] == "hf://lerobot/svla_so101_pickplace@main"
    for bad in ("https://huggingface.co/x/y", "hf://a/b/../c", "hf://onlyorg"):
        r = await client.post(
            "/datasets/import-hf",
            json={"workspace_id": str(a.workspace_id), "dataset_id": body["dataset"]["id"], "hf_uri": bad},
            headers=a.h,
        )
        assert r.status_code == 422 and r.json()["code"] == "hf_uri_invalid", bad
    r = await client.post(
        "/datasets/import-hf", json={"workspace_id": str(a.workspace_id), "hf_uri": "hf://a/b"}, headers=a.h
    )
    assert r.status_code == 422 and r.json()["code"] == "validation_failed"


async def test_import_hf_and_merge_enforce_storage_quota(
    client: httpx.AsyncClient, make_actor: Any, sm: async_sessionmaker[AsyncSession]
) -> None:
    """SEC-input-3: import-hf / merge check the storage quota up front and cap the job in bytes."""
    a = await make_actor()
    d1, d2 = await _ds(client, a, "q1"), await _ds(client, a, "q2")
    v1 = await _ready_version(sm, d1["id"])  # size_bytes=1000 each
    v2 = await _ready_version(sm, d2["id"])
    async with sm() as db:
        db.add(Quota(workspace_id=a.workspace_id, user_id=None, storage_bytes=5000))
        await db.commit()
    imp = {"workspace_id": str(a.workspace_id), "new_dataset_name": "hub", "hf_uri": "hf://o/r"}
    r = await client.post("/datasets/import-hf", json=imp, headers=a.h)
    assert r.status_code == 202, r.text
    async with sm() as db:
        job = await db.get(Job, uuid.UUID(r.json()["job"]["id"]))
        assert job is not None and job.payload["max_bytes"] == 3000  # 5000 - 2 x 1000
        job.status = "failed"  # type: ignore[assignment]  # its reservation ends with it
        await db.commit()
    merge = {
        "workspace_id": str(a.workspace_id),
        "new_dataset_name": "merged",
        "source_version_ids": [str(v1), str(v2)],
    }
    r = await client.post("/datasets/merge", json=merge, headers=a.h)
    assert r.status_code == 202, r.text
    async with sm() as db:
        job = await db.get(Job, uuid.UUID(r.json()["job"]["id"]))
        assert job is not None and job.payload["max_bytes"] == 3000
    # the merge's known size (2000) no longer fits once the quota shrinks to 3500
    async with sm() as db:
        await db.execute(update(Quota).where(Quota.workspace_id == a.workspace_id).values(storage_bytes=3500))
        await db.commit()
    r = await client.post("/datasets/merge", json={**merge, "new_dataset_name": "m2"}, headers=a.h)
    assert r.status_code == 403 and r.json()["code"] == "quota_exceeded", r.text
    assert r.json()["params"]["kind"] == "storage_bytes"
    assert_contract(r, "/datasets/merge", "post")
    # already full: an HF import (size unknown) is refused instead of downloading the whole repo
    async with sm() as db:
        await db.execute(update(Quota).where(Quota.workspace_id == a.workspace_id).values(storage_bytes=2000))
        await db.commit()
    r = await client.post("/datasets/import-hf", json={**imp, "new_dataset_name": "hub2"}, headers=a.h)
    assert r.status_code == 403 and r.json()["code"] == "quota_exceeded", r.text
    assert_contract(r, "/datasets/import-hf", "post")
    async with sm() as db:  # nothing was created by the refused requests
        names = set((await db.execute(select(Dataset.name))).scalars())
        assert "m2" not in names and "hub2" not in names


async def test_concurrent_imports_reserve_quota_at_enqueue(
    client: httpx.AsyncClient, make_actor: Any, sm: async_sessionmaker[AsyncSession]
) -> None:
    """Phase-5 re-verify (SEC-input-3 residual): 4 concurrent imports with 500 B left used to get
    ``max_bytes=500`` each. The caps are now reserved at enqueue time, so their sum fits."""
    import asyncio

    from app.datasets.quota import reserved_bytes, storage_used

    a = await make_actor()
    d1 = await _ds(client, a, "base")
    await _ready_version(sm, d1["id"])  # 1000 B
    async with sm() as db:
        db.add(Quota(workspace_id=a.workspace_id, user_id=None, storage_bytes=1500))
        await db.commit()
    rs = await asyncio.gather(
        *(
            client.post(
                "/datasets/import-hf",
                json={
                    "workspace_id": str(a.workspace_id),
                    "new_dataset_name": f"hub{i}",
                    "hf_uri": "hf://o/r",
                },
                headers=a.h,
            )
            for i in range(4)
        )
    )
    codes = sorted(r.status_code for r in rs)
    assert codes == [202, 403, 403, 403], [r.text[:200] for r in rs]
    async with sm() as db:
        caps = [
            j.payload["max_bytes"]
            for j in (await db.execute(select(Job).where(Job.workspace_id == a.workspace_id))).scalars()
            if j.kind == "import_hf_dataset"
        ]
        assert caps == [500]
        assert await reserved_bytes(db, a.workspace_id) == 500
        assert await storage_used(db, a.workspace_id) == 1500
    # an upload no longer fits in the reserved bytes either
    r = await client.post(
        "/uploads",
        json={
            "workspace_id": str(a.workspace_id),
            "new_dataset_name": "up",
            "filename": "x.tar",
            "size": 100,
            "sha256": "0" * 64,
            "part_size": 5 * 1024 * 1024,
        },
        headers=a.h,
    )
    assert r.status_code == 403 and r.json()["code"] == "quota_exceeded", r.text
    # once the import finished (its version has a size), the reservation is replaced by the size
    async with sm() as db:
        job = (await db.execute(select(Job).where(Job.kind == "import_hf_dataset"))).scalar_one()
        await db.execute(
            update(DatasetVersion).where(DatasetVersion.id == job.dataset_version_id).values(size_bytes=200)
        )
        await db.commit()
        assert await reserved_bytes(db, a.workspace_id) == 0
        assert await storage_used(db, a.workspace_id) == 1200


async def test_merge(
    client: httpx.AsyncClient, make_actor: Any, sm: async_sessionmaker[AsyncSession]
) -> None:
    a = await make_actor()
    d1, d2 = await _ds(client, a, "m1"), await _ds(client, a, "m2")
    v1 = await _ready_version(sm, d1["id"])
    v2 = await _ready_version(sm, d2["id"])
    v3 = await _ready_version(sm, d2["id"], 2, features={"action": {"dtype": "float32", "shape": [7]}})
    v4 = await _ready_version(sm, d2["id"], 3, status=DatasetVersionStatus.VALIDATING, content_hash=None)
    url = "/datasets/merge"
    base = {"workspace_id": str(a.workspace_id), "new_dataset_name": "merged"}
    r = await client.post(url, json={**base, "source_version_ids": [str(v1), str(v3)]}, headers=a.h)
    assert r.status_code == 422 and r.json()["code"] == "dataset_schema_mismatch"
    assert_contract(r, url, "post")
    r = await client.post(url, json={**base, "source_version_ids": [str(v1), str(v4)]}, headers=a.h)
    assert r.status_code == 409 and r.json()["code"] == "dataset_version_not_ready"
    r = await client.post(url, json={**base, "source_version_ids": [str(v1), str(uuid.uuid4())]}, headers=a.h)
    assert r.status_code == 404
    r = await client.post(url, json={**base, "source_version_ids": [str(v1)]}, headers=a.h)
    assert r.status_code == 422
    r = await client.post(url, json={**base, "source_version_ids": [str(v1), str(v2)]}, headers=a.h)
    assert r.status_code == 202, r.text
    assert_contract(r, url, "post")
    body = r.json()
    assert body["job"]["kind"] == "merge_datasets" and body["version"]["source"] == "merge"
    async with sm() as db:
        mv = await db.get(DatasetVersion, uuid.UUID(body["version"]["id"]))
        assert mv is not None and mv.merged_from == [v1, v2]
        jobs = (await db.execute(select(Job).where(Job.dataset_version_id == mv.id))).scalars().all()
        assert jobs[0].payload["source_version_ids"] == [str(v1), str(v2)]
    # merging into another workspace's dataset is invisible
    other = await make_actor()
    r = await client.post(
        url,
        json={
            "workspace_id": str(other.workspace_id),
            "new_dataset_name": "x",
            "source_version_ids": [str(v1), str(v2)],
        },
        headers=other.h,
    )
    assert r.status_code == 404
