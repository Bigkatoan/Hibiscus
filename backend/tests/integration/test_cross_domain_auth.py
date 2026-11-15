"""The merged app (``app.main.create_app`` with the default ``extra_routers``) serves datasets,
runs, models and /admin/gpus with REAL authentication: cookie session + CSRF or PAT (scopes,
workspace binding) through ``app.core.deps``; one ProblemError class and handler; core cursors;
audit through ``app.core.audit``. No dependency overrides. Every response is validated against
``api/openapi.yaml`` (``tests.auth.fixtures.Api``).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from sqlalchemy import delete, func, select, text, update

from app.core.audit import verify_chain
from app.core.settings import Settings
from app.db import models as m
from app.main import create_app
from tests.auth.fixtures import Api, Infra, make_settings, reset_db
from tests.integration.authn import create_user, create_workspace, pat_headers, session_headers
from tests.runs.conftest import golden_features

V1 = "/api/v1"
DEFAULT_EXTRA_ROUTERS: list[str] = Settings.model_fields["extra_routers"].get_default(
    call_default_factory=True
)


@dataclass
class World:
    app: Any
    api: Api
    ws_a: uuid.UUID
    ws_b: uuid.UUID
    member: uuid.UUID  # member of A and B
    viewer: uuid.UUID  # viewer of A
    dataset_a: uuid.UUID
    version_a: uuid.UUID
    dataset_b: uuid.UUID

    async def session(self, user: uuid.UUID) -> dict[str, str]:
        return await session_headers(self.app, user)

    async def pat(self, user: uuid.UUID, ws: uuid.UUID, *scopes: str) -> dict[str, str]:
        return await pat_headers(self.app, user, ws, scopes)


def assert_problem(r: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert r.status_code == status, (r.status_code, r.text[:500])
    assert r.headers["content-type"].startswith("application/problem+json"), r.headers
    body: dict[str, Any] = r.json()
    assert body["status"] == status and body["code"] == code, body
    assert body["request_id"] and body["type"].endswith(code)
    return body


async def _seed_dataset(db: Any, ws: uuid.UUID, name: str, *, ready: bool) -> tuple[uuid.UUID, uuid.UUID]:
    ds = m.Dataset(workspace_id=ws, name=name, slug=name)
    db.add(ds)
    await db.flush()
    v = m.DatasetVersion(
        dataset_id=ds.id,
        version=1,
        status=m.DatasetVersionStatus.READY if ready else m.DatasetVersionStatus.VALIDATING,
        source=m.DatasetSource.UPLOAD,
        content_hash="a" * 64,
        storage_prefix=f"s3://hibiscus-datasets/{ws}/{ds.id}/1/",
        total_episodes=20,
        total_frames=11277,
        features=golden_features(),
        camera_keys=["observation.images.wrist_cam"],
        fps=30.0,
    )
    db.add(v)
    await db.flush()
    ds.latest_version_id = v.id
    return ds.id, v.id


@pytest.fixture
async def world(containers: Infra) -> AsyncIterator[World]:
    await reset_db(containers.pg_url)
    app = create_app(make_settings(extra_routers=DEFAULT_EXTRA_ROUTERS))
    svc = app.state.services
    await svc.redis.flushdb()
    await svc.s3.ensure_buckets()
    assert app.state.mounted_extra == DEFAULT_EXTRA_ROUTERS
    member = await create_user(app)
    viewer = await create_user(app)
    ws_a = await create_workspace(app, {member: m.WorkspaceRole.MEMBER, viewer: m.WorkspaceRole.VIEWER})
    ws_b = await create_workspace(app, {member: m.WorkspaceRole.MEMBER})
    async with svc.db.sessionmaker() as db:
        dataset_a, version_a = await _seed_dataset(db, ws_a, "so101_a", ready=True)
        dataset_b, _ = await _seed_dataset(db, ws_b, "so101_b", ready=True)
        db.add(
            m.GpuNode(
                id="cuda0",
                host="box",
                device_index=0,
                name="NVIDIA GeForce RTX 3060",
                total_vram_mb=12288,
                compute_capability="8.6",
                supports_bf16=True,
                supports_fast_fp16=True,
                status=m.GpuNodeStatus.ONLINE,
            )
        )
        await db.commit()
    api = Api(app)
    async with app.router.lifespan_context(app):  # core + datasets maintenance + runs reaper
        yield World(app, api, ws_a, ws_b, member, viewer, dataset_a, version_a, dataset_b)
        await api.aclose()


def run_body(w: World, ws: uuid.UUID | None = None, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "workspace_id": str(ws or w.ws_a),
        "dataset_version_id": str(w.version_a),
        "policy_type": "act",
        "preset": "quick",
        "config": {
            "policy": {"chunk_size": 50, "n_action_steps": 50},
            "train": {"steps": 300, "save_freq": 100},
        },
        "gpu": "cuda0",
    }
    body.update(over)
    return body


def upload_body(ws: uuid.UUID, name: str = "Pick n place") -> dict[str, Any]:
    data = b"x" * 100
    return {
        "workspace_id": str(ws),
        "new_dataset_name": name,
        "filename": "Picknplace.tar",
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


async def test_unauthenticated_is_401_problem(world: World) -> None:
    api, a = world.api, str(world.ws_a)
    for method, url, kw in (
        ("GET", f"{V1}/datasets", {"params": {"workspace_id": a}}),
        ("GET", f"{V1}/datasets/{world.dataset_a}", {}),
        ("GET", f"{V1}/dataset-versions/{world.version_a}", {}),
        ("GET", f"{V1}/uploads", {"params": {"workspace_id": a}}),
        ("POST", f"{V1}/uploads", {"json": upload_body(world.ws_a)}),
        ("GET", f"{V1}/policies", {}),
        ("GET", f"{V1}/runs", {"params": {"workspace_id": a}}),
        ("POST", f"{V1}/runs", {"json": run_body(world)}),
        ("POST", f"{V1}/runs/preflight", {"json": run_body(world)}),
        ("GET", f"{V1}/gpus", {}),
        ("GET", f"{V1}/jobs", {"params": {"workspace_id": a}}),
        ("GET", f"{V1}/models", {"params": {"workspace_id": a}}),
        ("GET", f"{V1}/models/{uuid.uuid4()}", {}),
    ):
        r = await api.http.request(method, url, **kw)
        assert_problem(r, 401, "unauthenticated")
    # garbage bearer / unknown PAT / revoked PAT
    r = await api.get(f"{V1}/runs", params={"workspace_id": a}, headers={"Authorization": "Bearer nope"})
    assert_problem(r, 401, "unauthenticated")
    fake = "hbp_ABCDEFGH_" + "A" * 43
    r = await api.get(
        f"{V1}/datasets", params={"workspace_id": a}, headers={"Authorization": f"Bearer {fake}"}
    )
    assert_problem(r, 401, "unauthenticated")
    h = await world.pat(world.member, world.ws_a, "datasets:read")
    async with world.app.state.services.db.sessionmaker() as db:
        await db.execute(update(m.ApiToken).values(revoked_at=func.now()))
        await db.commit()
    r = await api.get(f"{V1}/datasets", params={"workspace_id": a}, headers=h)
    assert_problem(r, 401, "token_revoked")


async def test_cookie_session_requires_csrf_on_unsafe_methods(world: World) -> None:
    h = await world.session(world.member)
    no_csrf = {"Cookie": h["Cookie"]}
    assert_problem(
        await world.api.http.post(f"{V1}/uploads", json=upload_body(world.ws_a), headers=no_csrf),
        403,
        "csrf_failed",
    )
    assert_problem(
        await world.api.http.post(f"{V1}/runs", json=run_body(world), headers=no_csrf), 403, "csrf_failed"
    )
    wrong = {**h, "X-CSRF-Token": "x" * 43}
    assert_problem(
        await world.api.http.post(f"{V1}/runs/preflight", json=run_body(world), headers=wrong),
        403,
        "csrf_failed",
    )
    # safe methods need no CSRF header
    r = await world.api.get(f"{V1}/datasets", params={"workspace_id": str(world.ws_a)}, headers=no_csrf)
    assert r.status_code == 200


async def test_pat_scopes(world: World) -> None:
    api, a = world.api, str(world.ws_a)
    read = await world.pat(world.member, world.ws_a, "datasets:read")
    assert (await api.get(f"{V1}/datasets", params={"workspace_id": a}, headers=read)).status_code == 200
    body = assert_problem(
        await api.post(f"{V1}/uploads", csrf=False, json=upload_body(world.ws_a), headers=read),
        403,
        "insufficient_scope",
    )
    assert body["params"] == {"scope": "datasets:write"}
    assert_problem(
        await api.get(f"{V1}/runs", params={"workspace_id": a}, headers=read), 403, "insufficient_scope"
    )
    assert_problem(
        await api.get(f"{V1}/models", params={"workspace_id": a}, headers=read), 403, "insufficient_scope"
    )
    runs_read = await world.pat(world.member, world.ws_a, "runs:read")
    assert_problem(
        await api.post(f"{V1}/runs", csrf=False, json=run_body(world), headers=runs_read),
        403,
        "insufficient_scope",
    )
    assert (await api.get(f"{V1}/runs", params={"workspace_id": a}, headers=runs_read)).status_code == 200
    write = await world.pat(world.member, world.ws_a, "datasets:write", "runs:write", "models:read")
    r = await api.post(f"{V1}/uploads", csrf=False, json=upload_body(world.ws_a), headers=write)
    assert r.status_code == 201, r.text
    r = await api.post(f"{V1}/runs", csrf=False, json=run_body(world), headers=write)
    assert r.status_code == 201, r.text
    # PATs never reach /admin, and cookie-only dataset deletion rejects them
    assert_problem(
        await api.patch(f"{V1}/admin/gpus/cuda0", json={"status": "draining"}, headers=write),
        403,
        "forbidden",
    )
    assert_problem(await api.delete(f"{V1}/datasets/{world.dataset_a}", headers=write), 403, "forbidden")
    # the PAT's actions are audited with the token id through the core hash chain
    async with world.app.state.services.db.sessionmaker() as db:
        ev = (await db.execute(select(m.AuditEvent).where(m.AuditEvent.action == "run.created"))).scalar_one()
        assert ev.actor_user_id == world.member and ev.actor_token_id is not None
        assert ev.workspace_id == world.ws_a and ev.request_id
        assert await verify_chain(db) == (True, None)


async def test_pat_bound_to_workspace_a_cannot_touch_workspace_b(world: World) -> None:
    api, b = world.api, str(world.ws_b)
    h = await world.pat(world.member, world.ws_a, "datasets:write", "runs:write", "models:read")
    # the same user, by cookie, is a member of B
    s = await world.session(world.member)
    assert (await api.get(f"{V1}/datasets", params={"workspace_id": b}, headers=s)).status_code == 200
    assert_problem(await api.get(f"{V1}/datasets", params={"workspace_id": b}, headers=h), 403, "forbidden")
    assert_problem(await api.get(f"{V1}/datasets/{world.dataset_b}", headers=h), 404, "not_found")
    assert_problem(
        await api.post(f"{V1}/uploads", csrf=False, json=upload_body(world.ws_b), headers=h), 403, "forbidden"
    )
    assert_problem(await api.get(f"{V1}/runs", params={"workspace_id": b}, headers=h), 403, "forbidden")
    assert_problem(
        await api.post(f"{V1}/runs", csrf=False, json=run_body(world, world.ws_b), headers=h),
        403,
        "forbidden",
    )
    assert_problem(await api.get(f"{V1}/models", params={"workspace_id": b}, headers=h), 403, "forbidden")
    assert_problem(await api.get(f"{V1}/jobs", params={"workspace_id": b}, headers=h), 403, "forbidden")
    # a run created in B by cookie is invisible to the A-bound PAT
    r = await api.post(
        f"{V1}/runs",
        json=run_body(world, world.ws_b, dataset_version_id=str(await _version_of(world, world.dataset_b))),
        headers=s,
    )
    assert r.status_code == 201, r.text
    assert_problem(await api.get(f"{V1}/runs/{r.json()['id']}", headers=h), 404, "not_found")
    assert_problem(
        await api.post(f"{V1}/runs/{r.json()['id']}/cancel", csrf=False, headers=h), 404, "not_found"
    )


async def _version_of(world: World, dataset_id: uuid.UUID) -> uuid.UUID:
    async with world.app.state.services.db.sessionmaker() as db:
        vid: uuid.UUID | None = await db.scalar(
            select(m.DatasetVersion.id).where(m.DatasetVersion.dataset_id == dataset_id)
        )
        assert vid is not None
        return vid


async def test_viewer_cannot_create_runs_or_uploads(world: World) -> None:
    api = world.api
    h = await world.session(world.viewer)
    assert (
        await api.get(f"{V1}/runs", params={"workspace_id": str(world.ws_a)}, headers=h)
    ).status_code == 200
    assert_problem(await api.post(f"{V1}/runs", json=run_body(world), headers=h), 403, "forbidden")
    assert_problem(await api.post(f"{V1}/uploads", json=upload_body(world.ws_a), headers=h), 403, "forbidden")
    # a stranger (no membership) cannot list A at all, and cannot tell that A exists (404 like core)
    stranger = await create_user(world.app)
    sh = await world.session(stranger)
    for path in ("runs", "models", "jobs", "datasets", "uploads"):
        assert_problem(
            await api.get(f"{V1}/{path}", params={"workspace_id": str(world.ws_a)}, headers=sh),
            404,
            "not_found",
        )
    assert_problem(await api.get(f"{V1}/workspaces/{world.ws_a}", headers=sh), 404, "not_found")
    assert_problem(await api.post(f"{V1}/runs", json=run_body(world), headers=sh), 404, "not_found")
    assert_problem(await api.get(f"{V1}/datasets/{world.dataset_a}", headers=sh), 404, "not_found")
    # non-admin session on /admin/gpus
    assert_problem(
        await api.patch(f"{V1}/admin/gpus/cuda0", json={"status": "draining"}, headers=h), 403, "forbidden"
    )


async def test_member_happy_path_across_domains(world: World) -> None:
    api, a = world.api, str(world.ws_a)
    h = await world.session(world.member)
    up = await api.post(f"{V1}/uploads", json=upload_body(world.ws_a), headers=h)
    assert up.status_code == 201, up.text
    ds = await api.get(f"{V1}/datasets", params={"workspace_id": a}, headers=h)
    assert ds.status_code == 200 and [d["id"] for d in ds.json()["items"]] == [str(world.dataset_a)]
    pol = await api.get(f"{V1}/policies", headers=h)
    assert pol.status_code == 200 and {p["type"] for p in pol.json()["items"]} >= {"act", "diffusion"}
    pf = await api.post(f"{V1}/runs/preflight", json=run_body(world), headers=h)
    assert pf.status_code == 200, pf.text
    ids = []
    for _ in range(3):
        r = await api.post(f"{V1}/runs", json=run_body(world), headers=h)
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    got = await api.get(f"{V1}/runs/{ids[0]}", headers=h)
    assert got.status_code == 200 and got.json()["created_by"]["id"] == str(world.member)
    # core cursors page through runs
    seen: list[str] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"workspace_id": a, "limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = (await api.get(f"{V1}/runs", params=params, headers=h)).json()
        seen += [x["id"] for x in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert sorted(seen) == sorted(ids)
    assert (await api.get(f"{V1}/models", params={"workspace_id": a}, headers=h)).status_code == 200
    assert (await api.get(f"{V1}/gpus", headers=h)).status_code == 200
    # the member can cancel their own queued run; audited through the core chain
    c = await api.post(f"{V1}/runs/{ids[0]}/cancel", headers=h)
    assert c.status_code == 202 and c.json()["status"] == "cancelled"
    async with world.app.state.services.db.sessionmaker() as db:
        actions = (await db.execute(select(m.AuditEvent.action).order_by(m.AuditEvent.id))).scalars().all()
        assert actions.count("run.created") == 3 and "run.cancelled" in actions
        assert await verify_chain(db) == (True, None)


async def test_platform_admin_gpu_update_requires_verified_session(world: World) -> None:
    admin = await create_user(world.app, platform_admin=True)
    unverified = await session_headers(world.app, admin, mfa_verified=False)
    r = await world.api.patch(f"{V1}/admin/gpus/cuda0", json={"status": "draining"}, headers=unverified)
    assert_problem(r, 403, "mfa_reauth_required")
    ok = await world.session(admin)
    r = await world.api.patch(f"{V1}/admin/gpus/cuda0", json={"status": "draining"}, headers=ok)
    assert r.status_code == 200 and r.json()["status"] == "draining"


async def test_domain_errors_render_as_problem_json(world: World) -> None:
    api, a = world.api, str(world.ws_a)
    h = await world.session(world.member)
    # datasets
    assert_problem(await api.get(f"{V1}/datasets/{uuid.uuid4()}", headers=h), 404, "not_found")
    assert_problem(await api.get(f"{V1}/dataset-versions/{uuid.uuid4()}", headers=h), 404, "not_found")
    assert_problem(
        await api.get(f"{V1}/datasets", params={"workspace_id": a, "cursor": "garbage"}, headers=h),
        400,
        "bad_request",
    )
    r = await api.post(f"{V1}/datasets", json={"workspace_id": a, "name": "so101_a"}, headers=h)
    assert_problem(r, 409, "dataset_name_taken")
    body = assert_problem(
        await api.post(f"{V1}/uploads", json={"workspace_id": a}, headers=h), 422, "validation_failed"
    )
    assert body["errors"]
    r = await api.post(f"{V1}/uploads", json={**upload_body(world.ws_a), "filename": "x.cpio"}, headers=h)
    assert r.status_code in (422, 415) and r.headers["content-type"].startswith("application/problem+json"), (
        r.text
    )
    up = (await api.post(f"{V1}/uploads", json=upload_body(world.ws_a, "other"), headers=h)).json()
    r = await api.post(f"{V1}/uploads/{up['id']}/complete", headers=h)
    body = assert_problem(r, 409, "upload_incomplete")
    assert body["missing_parts"] == [1]
    r = await api.http.put(
        f"{V1}/uploads/{up['id']}/parts/1",
        content=b"y" * 100,
        headers={**h, "X-Content-SHA256": hashlib.sha256(b"z").hexdigest()},
    )
    assert_problem(r, 422, "upload_part_checksum_mismatch")
    # runs / policies / models / jobs
    assert_problem(await api.get(f"{V1}/policies/nope", headers=h), 404, "policy_unknown")
    assert_problem(
        await api.post(f"{V1}/runs", json=run_body(world, gpu="cuda9"), headers=h), 422, "preflight_failed"
    )
    assert_problem(await api.post(f"{V1}/runs/{uuid.uuid4()}/cancel", headers=h), 404, "not_found")
    assert_problem(
        await api.get(f"{V1}/runs", params={"workspace_id": a, "cursor": "garbage"}, headers=h),
        400,
        "bad_request",
    )
    r = await api.post(
        f"{V1}/runs",
        json=run_body(world, policy_type="act", config={"policy": {"chunk_size": -1}}),
        headers=h,
    )
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem+json"), r.text
    run = (await api.post(f"{V1}/runs", json=run_body(world), headers=h)).json()
    assert_problem(await api.post(f"{V1}/runs/{run['id']}/pause", headers=h), 409, "run_invalid_transition")
    assert_problem(await api.get(f"{V1}/models/{uuid.uuid4()}", headers=h), 404, "not_found")
    assert_problem(await api.get(f"{V1}/jobs/{uuid.uuid4()}", headers=h), 404, "not_found")
    assert_problem(
        await api.get(f"{V1}/runs/{run['id']}/metrics", params={"keys": "BAD KEY"}, headers=h),
        422,
        "validation_failed",
    )


# ------------------------------------------------------------------------------------------------
# phase-5 regressions (docs/qa/phase4-findings.md)
# ------------------------------------------------------------------------------------------------
async def test_idempotent_replay_reauthorizes_the_caller(world: World) -> None:
    """SEC-auth-05: a stored Idempotency-Key never bypasses authorization of the replaying request."""
    api = world.api
    key = {"Idempotency-Key": "replay-key-1"}
    h = await world.session(world.member)
    first = await api.post(f"{V1}/runs", json=run_body(world), headers={**h, **key})
    assert first.status_code == 201, first.text
    again = await api.post(f"{V1}/runs", json=run_body(world), headers={**h, **key})
    assert again.status_code == 201 and again.json()["id"] == first.json()["id"]
    # a read-only PAT of the same user (same workspace) does not get the stored run back
    read = await world.pat(world.member, world.ws_a, "datasets:read")
    assert_problem(
        await api.post(f"{V1}/runs", csrf=False, json=run_body(world), headers={**read, **key}),
        403,
        "insufficient_scope",
    )
    # a PAT bound to workspace B (any body) does not get workspace A's run either
    pat_b = await world.pat(world.member, world.ws_b, "runs:write")
    assert_problem(
        await api.post(f"{V1}/runs", csrf=False, json=run_body(world), headers={**pat_b, **key}),
        403,
        "forbidden",
    )
    # keys are scoped per workspace: the same key in B creates B's own run
    async with world.app.state.services.db.sessionmaker() as db:
        version_b = await db.scalar(
            select(m.DatasetVersion.id).where(m.DatasetVersion.dataset_id == world.dataset_b)
        )
    rb = await api.post(
        f"{V1}/runs",
        csrf=False,
        json=run_body(world, world.ws_b, dataset_version_id=str(version_b)),
        headers={**pat_b, **key},
    )
    assert rb.status_code == 201, rb.text
    assert rb.json()["id"] != first.json()["id"] and rb.json()["workspace_id"] == str(world.ws_b)
    # once removed from A, the member's replay is a plain 404 (no stored run leaks)
    async with world.app.state.services.db.sessionmaker() as db:
        await db.execute(
            delete(m.Membership).where(
                m.Membership.workspace_id == world.ws_a, m.Membership.user_id == world.member
            )
        )
        await db.commit()
    h = await world.session(world.member)
    assert_problem(await api.post(f"{V1}/runs", json=run_body(world), headers={**h, **key}), 404, "not_found")


async def test_concurrent_idempotent_creates_make_one_run(world: World) -> None:
    """QC-backend-06: concurrent retries with one Idempotency-Key create exactly one run."""
    import asyncio

    api = world.api
    h = {**(await world.session(world.member)), "Idempotency-Key": "same-key-1"}
    rs = await asyncio.gather(*(api.post(f"{V1}/runs", json=run_body(world), headers=h) for _ in range(4)))
    assert [r.status_code for r in rs] == [201] * 4, [r.text[:200] for r in rs]
    assert len({r.json()["id"] for r in rs}) == 1
    async with world.app.state.services.db.sessionmaker() as db:
        n = await db.scalar(select(func.count()).select_from(m.Run).where(m.Run.workspace_id == world.ws_a))
        assert n == 1
        # past the 24 h replay window the key is released and creates a new run
        await db.execute(update(m.Run).values(created_at=func.now() - text("interval '25 hours'")))
        await db.commit()
    r = await api.post(f"{V1}/runs", json=run_body(world), headers=h)
    assert r.status_code == 201 and r.json()["id"] != rs[0].json()["id"]
    again = await api.post(f"{V1}/runs", json=run_body(world), headers=h)
    assert again.json()["id"] == r.json()["id"]


async def test_policies_and_gpus_enforce_pat_scope(world: World) -> None:
    """/policies and /gpus need runs:read on a PAT (runs:write implies it); sessions are unaffected."""
    api = world.api
    data_only = await world.pat(world.member, world.ws_a, "datasets:write")
    for url in (f"{V1}/policies", f"{V1}/policies/act", f"{V1}/gpus", f"{V1}/queue"):
        body = assert_problem(await api.get(url, headers=data_only), 403, "insufficient_scope")
        assert body["params"] == {"scope": "runs:read"}
    for scopes in (("runs:read",), ("runs:write",)):
        h = await world.pat(world.member, world.ws_a, *scopes)
        for url in (f"{V1}/policies", f"{V1}/policies/act", f"{V1}/gpus", f"{V1}/queue"):
            assert (await api.get(url, headers=h)).status_code == 200, (scopes, url)
    s = await world.session(world.member)
    assert (await api.get(f"{V1}/policies", headers=s)).status_code == 200
