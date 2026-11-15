"""CPU worker against REAL Postgres 16 + MinIO containers (testcontainers, random host ports).

Schema = backend/app/db/models.py (contract) via ``Base.metadata.create_all``.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import tarfile
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, text

from validate import db as dbm
from validate.runner import Runner
from validate.settings import WorkerSettings
from validate.store import Store
from validate.tests.synth import SynthSpec, make_v30

REPO = Path(__file__).resolve().parents[3]
PG_IMAGE = os.environ.get("HIBISCUS_TEST_PG_IMAGE", "postgres:16.16-trixie")
MINIO_IMAGE = os.environ.get("HIBISCUS_TEST_MINIO_IMAGE", "pgsty/minio:RELEASE.2026-08-04T00-00-00Z")


def _models() -> Any:
    sys.path.insert(0, str(REPO / "backend"))
    try:
        return importlib.import_module("app.db.models")
    finally:
        sys.path.pop(0)


@dataclass
class Env:
    engine: Engine
    store: Store
    settings: WorkerSettings
    models: Any


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Env]:
    from testcontainers.minio import MinioContainer
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer(PG_IMAGE, driver="psycopg") as pg, MinioContainer(MINIO_IMAGE) as mc:
        url = pg.get_connection_url()
        engine = create_engine(url)
        models = _models()
        with engine.begin() as c:
            models.Base.metadata.create_all(c)
            c.execute(
                text(
                    "INSERT INTO roles (name, rank, requires_mfa, description) VALUES "
                    "('owner',40,true,'o'),('admin',30,true,'a'),('member',20,false,'m'),('viewer',10,false,'v')"
                )
            )
        cfg = mc.get_config()
        store = Store(f"http://{cfg['endpoint']}", cfg["access_key"], cfg["secret_key"])
        for b in ("hibiscus-uploads", "hibiscus-datasets"):
            store.client.create_bucket(Bucket=b)
        settings = WorkerSettings(
            database_url=url,
            s3_endpoint_url=f"http://{cfg['endpoint']}",
            s3_access_key=cfg["access_key"],
            s3_secret_key=cfg["secret_key"],
            work_dir=tmp_path_factory.mktemp("work"),
            heartbeat_s=0.5,
            worker_id="test-worker",
        )
        yield Env(engine, store, settings, models)
        engine.dispose()


def _runner(env: Env, **kw: Any) -> Runner:
    s = env.settings
    if kw:
        from dataclasses import replace

        s = replace(s, **kw)
    return Runner(s, dbm.Db(env.engine, s.worker_id, s.lease_s), env.store)


def _seed_dataset(env: Env) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    ws, user, ds = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with env.engine.begin() as c:
        c.execute(
            text("INSERT INTO users (id, email, display_name, password_hash) VALUES (:i, :e, 'U', 'x')"),
            {"i": user, "e": f"{user.hex}@example.com"},
        )
        c.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:i, :s, 'W')"),
            {"i": ws, "s": f"w{ws.hex[:10]}"},
        )
        c.execute(
            text("INSERT INTO datasets (id, workspace_id, name, slug) VALUES (:i, :w, 'my ds', 'my-ds')"),
            {"i": ds, "w": ws},
        )
    return ws, user, ds


def _next_version(env: Env, ds: uuid.UUID) -> int:
    with env.engine.begin() as c:
        v = c.execute(
            text("SELECT coalesce(max(version), 0) + 1 FROM dataset_versions WHERE dataset_id = :d"),
            {"d": ds},
        ).scalar_one()
    return int(v)


def _seed_upload(
    env: Env,
    ws: uuid.UUID,
    user: uuid.UUID,
    ds: uuid.UUID,
    archive: Path,
    sha: str | None = None,
    put_object: bool = True,
) -> tuple[uuid.UUID, uuid.UUID]:
    vid, up, job = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    key = f"{ws}/uploads/{up}/{archive.name}"
    if put_object:
        env.store.upload_file(archive, "hibiscus-uploads", key)
    real_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    size = archive.stat().st_size
    with env.engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO dataset_versions (id, dataset_id, version, source, source_ref, created_by) "
                "VALUES (:i, :d, :n, 'upload', :r, :u)"
            ),
            {"i": vid, "d": ds, "n": _next_version(env, ds), "r": str(up), "u": user},
        )
        c.execute(
            text(
                "INSERT INTO upload_sessions (id, workspace_id, created_by, dataset_id, filename, "
                "archive_format, total_size, part_size, part_count, sha256, s3_bucket, s3_key, s3_upload_id, "
                "status, expires_at, completed_at, dataset_version_id) "
                "VALUES (:i, :w, :u, :d, :f, 'tar', :sz, 67108864, :pc, :sha, 'hibiscus-uploads', :k, 'x', "
                "'completed', now() + interval '7 days', now(), :v)"
            ),
            {
                "i": up,
                "w": ws,
                "u": user,
                "d": ds,
                "f": archive.name,
                "sz": size,
                "pc": max(1, -(-size // 67108864)),
                "sha": sha or real_sha,
                "k": key,
                "v": vid,
            },
        )
        c.execute(
            text(
                "INSERT INTO jobs (id, workspace_id, kind, resource, payload, dataset_version_id, "
                "created_by) "
                "VALUES (:j, :w, 'validate_dataset', 'cpu', CAST(:p AS jsonb), :v, :u)"
            ),
            {
                "j": job,
                "w": ws,
                "p": f'{{"dataset_version_id": "{vid}", "upload_id": "{up}"}}',
                "v": vid,
                "u": user,
            },
        )
    return vid, job


def _row(env: Env, table: str, rid: uuid.UUID) -> dict[str, Any]:
    q = {
        "jobs": "SELECT * FROM jobs WHERE id = :i",
        "dataset_versions": "SELECT * FROM dataset_versions WHERE id = :i",
    }
    with env.engine.begin() as c:
        return dict(c.execute(text(q[table]), {"i": rid}).mappings().one())


def _keys(env: Env, prefix: str) -> list[str]:
    out: list[str] = []
    for page in env.store.client.get_paginator("list_objects_v2").paginate(
        Bucket="hibiscus-datasets", Prefix=prefix
    ):
        out += [o["Key"] for o in page.get("Contents", [])]
    return out


def _tar_of(ds_root: Path, out: Path) -> Path:
    with tarfile.open(out, "w") as tf:
        tf.add(ds_root, arcname=ds_root.name)
    return out


# --------------------------------------------------------------------------------------------------
def test_golden_rar_validated_and_stored(env: Env, golden_rar: Path) -> None:
    ws, user, ds = _seed_dataset(env)
    vid, job = _seed_upload(env, ws, user, ds, golden_rar)
    assert _runner(env).run_once() is True
    j = _row(env, "jobs", job)
    v = _row(env, "dataset_versions", vid)
    assert j["status"] == "succeeded", (j["error_code"], j["error_message"])
    assert j["progress"] == 1.0 and j["attempts"] == 1 and j["lease_owner"] is None
    assert j["result"]["version_status"] == "ready"
    assert v["status"] == "ready" and v["ready_at"] is not None
    assert v["validate_report"]["summary"] == {"result": "passed", "errors": 0, "warnings": 0}
    assert [s["status"] for s in v["validate_report"]["steps"]] == ["passed"] * 7
    assert v["total_episodes"] == 20 and v["total_frames"] == 11277 and v["fps"] == 30.0
    assert v["camera_keys"] == ["observation.images.wrist_cam"]
    assert v["codebase_version"] == "v3.0" and v["robot_type"] == "so_follower"
    assert v["size_bytes"] == 148111356
    assert v["storage_prefix"] == f"s3://hibiscus-datasets/{ws}/{ds}/{vid}/"
    assert v["features"]["action"]["shape"] == [6]
    assert v["stats"]["action"]["mean"]
    assert len(v["preview"]["episodes"]) == 20
    data_keys = _keys(env, f"{ws}/{ds}/{vid}/")
    assert sorted(k.split(f"{vid}/", 1)[1] for k in data_keys) == [
        "data/chunk-000/file-000.parquet",
        "meta/episodes/chunk-000/file-000.parquet",
        "meta/info.json",
        "meta/stats.json",
        "meta/tasks.parquet",
        "videos/observation.images.wrist_cam/chunk-000/file-000.mp4",
    ]
    derived = _keys(env, f"{ws}/{ds}/{vid}.derived/")
    assert sum(k.endswith(".mp4") for k in derived) == 20
    assert sum(k.endswith(".jpg") for k in derived) == 20
    assert sum("/episodes/episode_" in k for k in derived) == 20
    manifest = env.store.get_json("hibiscus-datasets", f"{ws}/{ds}/{vid}.derived/manifest.json")
    assert manifest["content_hash"] == v["content_hash"] and len(manifest["files"]) == 6
    head = env.store.client.head_object(
        Bucket="hibiscus-datasets",
        Key=f"{ws}/{ds}/{vid}.derived/previews/observation.images.wrist_cam/episode_000000.mp4",
    )
    assert head["ContentType"] == "video/mp4"

    # Re-validation of a ready version uses the stored immutable copy, not the upload.
    env.store.client.delete_object(
        Bucket="hibiscus-uploads", Key=f"{ws}/uploads/{v['source_ref']}/{golden_rar.name}"
    )
    job2 = uuid.uuid4()
    with env.engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO jobs (id, workspace_id, kind, resource, payload, dataset_version_id) "
                "VALUES (:j, :w, 'validate_dataset', 'cpu', '{}'::jsonb, :v)"
            ),
            {"j": job2, "w": ws, "v": vid},
        )
    assert _runner(env).run_once() is True
    assert _row(env, "jobs", job2)["status"] == "succeeded"
    v2 = _row(env, "dataset_versions", vid)
    assert v2["status"] == "ready" and v2["content_hash"] == v["content_hash"]
    steps = {s["id"]: s["status"] for s in v2["validate_report"]["steps"]}
    assert steps["checksum"] == "skipped" and steps["decode"] == "passed"


def test_duplicate_content_and_invalid_and_checksum(env: Env, tmp_path: Path) -> None:
    ws, user, ds = _seed_dataset(env)
    root = make_v30(tmp_path / "a" / "my_dataset", SynthSpec(seed=3))
    arc = _tar_of(root, tmp_path / "a.tar")
    v1, _ = _seed_upload(env, ws, user, ds, arc)
    v2, j2 = _seed_upload(env, ws, user, ds, arc)
    r = _runner(env)
    assert r.run_once() and r.run_once()
    assert _row(env, "dataset_versions", v1)["status"] == "ready"
    dup = _row(env, "jobs", j2)
    assert dup["status"] == "failed" and dup["error_code"] == "dataset_version_duplicate"
    assert dup["result"]["duplicate_of"] == str(v1)
    assert _row(env, "dataset_versions", v2)["status"] == "failed"
    assert _row(env, "dataset_versions", v2)["content_hash"] is None

    # Unsafe archive -> version invalid (user-fixable), job itself succeeded.
    evil = tmp_path / "evil.tar"
    with tarfile.open(evil, "w") as tf:
        ti = tarfile.TarInfo("ds/../../etc/x")
        ti.size = 1
        import io

        tf.addfile(ti, io.BytesIO(b"x"))
    v3, j3 = _seed_upload(env, ws, user, ds, evil)
    assert r.run_once()
    assert _row(env, "jobs", j3)["status"] == "succeeded"
    v3row = _row(env, "dataset_versions", v3)
    assert v3row["status"] == "invalid"
    assert v3row["validate_report"]["steps"][1]["issues"][0]["code"] == "archive_unsafe_path"

    # Declared sha256 differs from the bytes -> version failed, job error_code upload_checksum_mismatch.
    root2 = make_v30(tmp_path / "b" / "my_dataset", SynthSpec(seed=4))
    v4, j4 = _seed_upload(env, ws, user, ds, _tar_of(root2, tmp_path / "b.tar"), sha="a" * 64)
    assert r.run_once()
    assert _row(env, "jobs", j4)["error_code"] == "upload_checksum_mismatch"
    assert _row(env, "dataset_versions", v4)["status"] == "failed"


def test_infra_failure_retried_once_then_failed(env: Env, tmp_path: Path) -> None:
    ws, user, ds = _seed_dataset(env)
    root = make_v30(tmp_path / "c" / "my_dataset", SynthSpec(seed=5))
    vid, job = _seed_upload(env, ws, user, ds, _tar_of(root, tmp_path / "c.tar"), put_object=False)
    r = _runner(env)
    assert r.run_once()
    j = _row(env, "jobs", job)
    assert j["status"] == "queued" and j["attempts"] == 1 and j["error_code"] == "internal_error"
    assert _row(env, "dataset_versions", vid)["status"] == "pending"
    assert r.run_once()
    j = _row(env, "jobs", job)
    assert j["status"] == "failed" and j["attempts"] == 2
    assert _row(env, "dataset_versions", vid)["status"] == "failed"


def test_cancel_via_lost_lease(env: Env, tmp_path: Path) -> None:
    ws, user, ds = _seed_dataset(env)
    root = make_v30(tmp_path / "d" / "my_dataset", SynthSpec(seed=6, episodes=6, length=120))
    vid, job = _seed_upload(env, ws, user, ds, _tar_of(root, tmp_path / "d.tar"))
    r = _runner(env, heartbeat_s=0.01)
    claimed = r.db.claim()
    assert claimed is not None and claimed.id == job
    with env.engine.begin() as c:  # the API's cancelJob flips the status; the worker must notice
        c.execute(text("UPDATE jobs SET status = 'cancelled' WHERE id = :i"), {"i": job})
    r.process(claimed)
    assert _row(env, "jobs", job)["status"] == "cancelled"
    assert _row(env, "dataset_versions", vid)["status"] == "failed"
    assert _keys(env, f"{ws}/{ds}/{vid}/") == []


def test_merge_two_ready_versions(env: Env, tmp_path: Path) -> None:
    ws, user, ds = _seed_dataset(env)
    r = _runner(env)
    ids = []
    for i, n_eps in enumerate((3, 2)):
        root = make_v30(tmp_path / f"m{i}" / "my_dataset", SynthSpec(seed=10 + i, episodes=n_eps))
        vid, _ = _seed_upload(env, ws, user, ds, _tar_of(root, tmp_path / f"m{i}.tar"))
        assert r.run_once()
        assert _row(env, "dataset_versions", vid)["status"] == "ready"
        ids.append(vid)
    merged, job = uuid.uuid4(), uuid.uuid4()
    with env.engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO dataset_versions (id, dataset_id, version, source, source_ref, merged_from) "
                "VALUES (:i, :d, :n, 'merge', 'merge', :mf)"
            ),
            {"i": merged, "d": ds, "n": _next_version(env, ds), "mf": ids},
        )
        c.execute(
            text(
                "INSERT INTO jobs (id, workspace_id, kind, resource, payload, dataset_version_id) "
                "VALUES (:j, :w, 'merge_datasets', 'cpu', CAST(:p AS jsonb), :v)"
            ),
            {"j": job, "w": ws, "v": merged, "p": f'{{"source_version_ids": ["{ids[0]}", "{ids[1]}"]}}'},
        )
    assert r.run_once()
    j = _row(env, "jobs", job)
    assert j["status"] == "succeeded", (j["error_code"], j["error_message"])
    m = _row(env, "dataset_versions", merged)
    assert m["status"] == "ready" and m["total_episodes"] == 5 and m["total_frames"] == 200
    assert m["validate_report"]["summary"]["errors"] == 0
    assert m["merged_from"] == ids
    assert len(_keys(env, f"{ws}/{ds}/{merged}.derived/previews/")) == 10


def _set_storage_quota(env: Env, ws: uuid.UUID, storage_bytes: int) -> None:
    with env.engine.begin() as c:
        c.execute(
            text("INSERT INTO quotas (id, workspace_id, storage_bytes) VALUES (:i, :w, :b)"),
            {"i": uuid.uuid4(), "w": ws, "b": storage_bytes},
        )


def test_storage_quota_caps_archive_expansion(env: Env, tmp_path: Path) -> None:
    """SEC-input-3: an archive inside the upload quota may not unpack past the workspace's
    remaining storage, and nothing is stored once the quota is used up."""
    ws, user, ds = _seed_dataset(env)
    root = make_v30(tmp_path / "q" / "my_dataset", SynthSpec(seed=21))
    arc = _tar_of(root, tmp_path / "q.tar")
    _set_storage_quota(env, ws, arc.stat().st_size // 4)  # the upload itself was accepted earlier
    vid, _ = _seed_upload(env, ws, user, ds, arc)
    r = _runner(env)
    assert r.run_once()
    v = _row(env, "dataset_versions", vid)
    assert v["status"] == "invalid", v["status"]
    codes = [i["code"] for s in v["validate_report"]["steps"] for i in s.get("issues", [])]
    assert "archive_too_large" in codes
    assert _keys(env, f"{ws}/{ds}/{vid}/") == []
    # Workspace already full (another live version uses it all) -> refused before unpacking.
    with env.engine.begin() as c:
        c.execute(text("UPDATE dataset_versions SET size_bytes = :b WHERE id = :v"), {"b": 10**12, "v": vid})
    v2, j2 = _seed_upload(env, ws, user, ds, arc)
    assert r.run_once()
    j = _row(env, "jobs", j2)
    assert j["status"] == "failed" and j["error_code"] == "quota_exceeded"
    assert _row(env, "dataset_versions", v2)["status"] == "failed"
    assert _keys(env, f"{ws}/{ds}/{v2}/") == []


def test_storage_remaining_subtracts_other_jobs_reservations(env: Env) -> None:
    """Phase-5 re-verify (SEC-input-3 residual): the API reserves each queued import/merge job's
    ``max_bytes``; a worker replica must not hand those reserved bytes to another job."""
    ws, user, ds = _seed_dataset(env)
    _set_storage_quota(env, ws, 1000)
    vids = []
    for cap in (300, 200):
        vid = uuid.uuid4()
        vids.append(vid)
        with env.engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO dataset_versions (id, dataset_id, version, source, source_ref, created_by) "
                    "VALUES (:i, :d, :n, 'hf_import', 'hf://o/r', :u)"
                ),
                {"i": vid, "d": ds, "n": _next_version(env, ds), "u": user},
            )
            c.execute(
                text(
                    # running under another worker's live lease: reserved, but never claimed by
                    # the runners of the other tests
                    "INSERT INTO jobs (id, workspace_id, kind, resource, status, payload, "
                    "dataset_version_id, created_by, lease_owner, lease_expires_at) "
                    "VALUES (:j, :w, 'import_hf_dataset', 'cpu', 'running', CAST(:p AS jsonb), :v, :u, "
                    "'other-worker', now() + interval '1 hour')"
                ),
                {"j": uuid.uuid4(), "w": ws, "p": json.dumps({"max_bytes": cap}), "v": vid, "u": user},
            )
    db = _runner(env).db
    # each job sees the quota minus the *other* job's reservation, never its own
    assert db.storage_remaining(ws, user, vids[0]) == 800
    assert db.storage_remaining(ws, user, vids[1]) == 700
    # a stored version replaces its reservation by its size
    with env.engine.begin() as c:
        c.execute(text("UPDATE dataset_versions SET size_bytes = 50 WHERE id = :v"), {"v": vids[1]})
    assert db.storage_remaining(ws, user, vids[0]) == 950
    with env.engine.begin() as c:
        c.execute(text("UPDATE jobs SET status = 'failed' WHERE workspace_id = :w"), {"w": ws})


def test_hf_import_refused_when_repo_exceeds_quota(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SEC-input-3: the HF import sizes the repo first and downloads nothing when it does not fit."""
    import huggingface_hub

    ws, user, ds = _seed_dataset(env)
    _set_storage_quota(env, ws, 10 * 1024**2)
    uri = "hf://someone/huge-dataset"
    vid, job = uuid.uuid4(), uuid.uuid4()
    with env.engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO dataset_versions (id, dataset_id, version, source, source_ref, created_by) "
                "VALUES (:i, :d, :n, 'hf_import', :r, :u)"
            ),
            {"i": vid, "d": ds, "n": _next_version(env, ds), "r": uri, "u": user},
        )
        c.execute(
            text(
                "INSERT INTO jobs (id, workspace_id, kind, resource, payload, dataset_version_id, "
                "created_by) VALUES (:j, :w, 'import_hf_dataset', 'cpu', CAST(:p AS jsonb), :v, :u)"
            ),
            {"j": job, "w": ws, "p": json.dumps({"hf_uri": uri}), "v": vid, "u": user},
        )
    calls: list[str] = []

    def no_download(*a: Any, **k: Any) -> None:
        calls.append("snapshot_download")
        raise AssertionError("must not download")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", no_download)
    monkeypatch.setattr(Runner, "_hf_repo_bytes", lambda self, repo, rev, token: 300 * 1024**3)
    assert _runner(env).run_once()
    j = _row(env, "jobs", job)
    assert j["status"] == "failed" and j["error_code"] == "quota_exceeded", j
    assert _row(env, "dataset_versions", vid)["status"] == "failed"
    assert calls == []


@pytest.mark.slow
def test_hf_import_real_hub_dataset(env: Env) -> None:
    """Network: imports lerobot/pusht (7.7 MB, pinned revision) from the Hugging Face Hub."""
    ws, user, ds = _seed_dataset(env)
    uri = "hf://lerobot/pusht@7628202a2180972f291ba1bc6723834921e72c19"
    vid, job = uuid.uuid4(), uuid.uuid4()
    with env.engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO dataset_versions (id, dataset_id, version, source, source_ref, created_by) "
                "VALUES (:i, :d, :n, 'hf_import', :r, :u)"
            ),
            {"i": vid, "d": ds, "n": _next_version(env, ds), "r": uri, "u": user},
        )
        c.execute(
            text(
                "INSERT INTO jobs (id, workspace_id, kind, resource, payload, dataset_version_id, "
                "created_by) VALUES (:j, :w, 'import_hf_dataset', 'cpu', CAST(:p AS jsonb), :v, :u)"
            ),
            {"j": job, "w": ws, "p": json.dumps({"hf_uri": uri}), "v": vid, "u": user},
        )
    assert _runner(env).run_once()
    j = _row(env, "jobs", job)
    v = _row(env, "dataset_versions", vid)
    assert j["status"] == "succeeded", (j["error_code"], j["error_message"])
    assert v["status"] in ("ready", "invalid"), v["validate_report"]
    assert v["codebase_version"] == "v3.0", json.dumps(v["validate_report"])[:3000]
    assert v["total_episodes"] == 206
    assert not any("/.cache/" in k for k in _keys(env, f"{ws}/{ds}/{vid}/"))
    steps = {s["id"]: s["status"] for s in v["validate_report"]["steps"]}
    assert steps["checksum"] == "skipped" and steps["structure"] == "passed"
