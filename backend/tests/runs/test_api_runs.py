"""Runs/policies API against real Postgres/Redis/MinIO; every JSON body validated against the contract."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.db import models as m
from tests.runs.conftest import PrincipalHolder, World, check, make_principal, problem, run_body


async def test_policies_catalogue(client: httpx.AsyncClient) -> None:
    body = check(await client.get("/policies"), "/policies")
    assert body["lerobot_version"] == "0.7.1"
    by = {p["type"]: p for p in body["items"]}
    assert set(by) == {"act", "diffusion", "vqbet", "tdmpc", "smolvla", "pi0", "pi05"}
    assert by["pi0"]["gpu_support"] == {"NVIDIA GeForce RTX 3060": "unsupported", "Tesla P40": "limited"}
    assert by["smolvla"]["gpu_support"]["NVIDIA GeForce RTX 3060"] == "limited"
    assert by["tdmpc"]["requires_reward"] and by["pi05"]["requires_peft"] and by["act"]["onnx"] == "full"
    r = await client.get("/policies/act")
    d = check(r, "/policies/{policy_type}")
    assert r.headers["etag"] == d["schema_etag"]
    assert d["policy_schema"]["x-hibiscus"]["policy_type"] == "act"
    assert {p["id"] for p in d["presets"]} == {"quick", "standard", "finetune"}
    assert (
        await client.get("/policies/act", headers={"If-None-Match": r.headers["etag"]})
    ).status_code == 304
    problem(await client.get("/policies/nope"), 404, "policy_unknown")


async def test_preflight_ok_and_resolution(client: httpx.AsyncClient, world: World, sync_engine: Any) -> None:
    rep = check(await client.post("/runs/preflight", json=run_body(world)), "/runs/preflight", "POST")
    assert rep["ok"] is True, rep["checks"]
    res = rep["resolved"]
    assert res["gpu_id"] == "cuda0" and res["mixed_precision"] == "no"
    assert (
        res["config"]["train"]["steps"] == 300 and res["config"]["train"]["log_freq"] == 100
    )  # preset quick
    assert len(res["heldout_episodes"]) == 2 and len(res["train_episodes"]) == 18  # round(20 * 0.1)
    args = res["lerobot_args"]
    assert "--policy.chunk_size=50" in args and "--steps=300" in args and "--trackio.enable=false" in args
    assert '--accelerator.mixed_precision="no"' in args
    assert "--dataset.repo_id=local/so101_picknplace_20261114" in args
    assert rep["estimate"]["source"] == "pending" and rep["estimate"]["peak_vram_mb"] > 0
    with Session(sync_engine) as s:
        job = s.scalars(select(m.Job)).one()
    assert job.kind == m.JobKind.ESTIMATE_RESOURCES and job.payload["gpu_name"] == "NVIDIA GeForce RTX 3060"
    # second preflight dedups the estimate job
    await client.post("/runs/preflight", json=run_body(world))
    with Session(sync_engine) as s:
        assert len(s.scalars(select(m.Job)).all()) == 1


async def test_preflight_blockers(client: httpx.AsyncClient, world: World, sync_engine: Any) -> None:
    rep = check(
        await client.post(
            "/runs/preflight",
            json=run_body(world, policy_type="tdmpc", preset=None, config={"policy": {}, "train": {}}),
        ),
        "/runs/preflight",
        "POST",
    )
    codes = {(c["id"], c["code"]) for c in rep["checks"] if c["severity"] == "error"}
    assert ("policy_requirements", "dataset_schema_mismatch") in codes  # no next.reward
    assert ("camera_keys", "dataset_schema_mismatch") in codes  # 640x360 is not square
    assert rep["ok"] is False
    rep = check(
        await client.post(
            "/runs/preflight",
            json=run_body(
                world, policy_type="pi0", gpu="cuda0", preset=None, config={"policy": {}, "train": {}}
            ),
        ),
        "/runs/preflight",
        "POST",
    )
    codes = {c["code"] for c in rep["checks"] if c["severity"] == "error"}
    assert {"policy_requires_peft", "gpu_insufficient_vram"} <= codes
    # P40 forces fp32
    rep = check(
        await client.post(
            "/runs/preflight",
            json=run_body(world, gpu="cuda1", config={"policy": {}, "train": {"mixed_precision": "bf16"}}),
        ),
        "/runs/preflight",
        "POST",
    )
    assert rep["resolved"]["mixed_precision"] == "no"
    assert any(c["code"] == "mixed_precision_forced_no" for c in rep["checks"])
    # dataset not validated
    with Session(sync_engine) as s:
        s.execute(update(m.DatasetVersion).values(status=m.DatasetVersionStatus.VALIDATING))
        s.commit()
    rep = check(await client.post("/runs/preflight", json=run_body(world)), "/runs/preflight", "POST")
    assert any(c["code"] == "dataset_version_not_ready" for c in rep["checks"])
    # config errors are reported as checks in preflight
    rep = check(
        await client.post(
            "/runs/preflight",
            json=run_body(
                world, config={"policy": {"chunk_size": 10, "n_action_steps": 20, "bogus": 1}, "train": {}}
            ),
        ),
        "/runs/preflight",
        "POST",
    )
    assert any(c["id"] == "config_schema" and c["severity"] == "error" for c in rep["checks"])


async def test_create_validation_errors(client: httpx.AsyncClient, world: World) -> None:
    p = problem(
        await client.post("/runs", json=run_body(world, config={"policy": {"bogus": 1}, "train": {}})),
        422,
        "validation_failed",
    )
    assert p["errors"][0]["loc"][:3] == ["body", "config", "policy"]
    p = problem(
        await client.post(
            "/runs",
            json=run_body(world, config={"policy": {"chunk_size": 10, "n_action_steps": 20}, "train": {}}),
        ),
        422,
        "policy_config_invalid",
    )
    assert p["errors"][0]["loc"] == ["body", "config", "policy", "n_action_steps"]
    problem(
        await client.post(
            "/runs",
            json=run_body(world, policy_type="tdmpc", preset=None, config={"policy": {}, "train": {}}),
        ),
        422,
        "preflight_failed",
    )
    problem(await client.post("/runs", json={**run_body(world), "extra": 1}), 422, "validation_failed")
    problem(
        await client.post("/runs", json=run_body(world, dataset_version_id=str(uuid.uuid4()))),
        404,
        "not_found",
    )
    problem(await client.post("/runs", json=run_body(world, priority=5)), 403, "forbidden")


async def test_create_list_get_update(
    client: httpx.AsyncClient, world: World, holder: PrincipalHolder
) -> None:
    r = await client.post(
        "/runs", json=run_body(world, name="first"), headers={"Idempotency-Key": "abc12345"}
    )
    run = check(r, "/runs", "POST")
    assert r.headers["location"] == f"/api/v1/runs/{run['id']}"
    assert run["status"] == "queued" and run["number"] == 1 and run["attempt"] == 0
    assert run["queue_position"] == 1 and run["requested_gpu"] == "cuda0"
    assert (
        set(run["allowed_actions"]) >= {"cancel", "clone", "edit"} and "resume" not in run["allowed_actions"]
    )
    again = check(
        await client.post(
            "/runs", json=run_body(world, name="first"), headers={"Idempotency-Key": "abc12345"}
        ),
        "/runs",
        "POST",
    )
    assert again["id"] == run["id"]
    second = check(await client.post("/runs", json=run_body(world)), "/runs", "POST")
    assert second["number"] == 2
    page = check(
        await client.get("/runs", params={"workspace_id": str(world.workspace_id), "limit": 1}), "/runs"
    )
    assert [x["id"] for x in page["items"]] == [second["id"]] and page["next_cursor"]
    page2 = check(
        await client.get(
            "/runs",
            params={"workspace_id": str(world.workspace_id), "limit": 1, "cursor": page["next_cursor"]},
        ),
        "/runs",
    )
    assert [x["id"] for x in page2["items"]] == [run["id"]]
    flt = check(
        await client.get(
            "/runs",
            params={
                "workspace_id": str(world.workspace_id),
                "status": "queued,running",
                "created_by": "me",
                "q": "first",
            },
        ),
        "/runs",
    )
    assert [x["id"] for x in flt["items"]] == [run["id"]]
    got = check(await client.get(f"/runs/{run['id']}"), "/runs/{run_id}")
    assert (
        got["dataset"]["name"] == "so101_picknplace_20261114" and got["created_by"]["display_name"] == "Alice"
    )
    upd = check(
        await client.patch(f"/runs/{run['id']}", json={"name": "renamed", "gpu": "auto"}),
        "/runs/{run_id}",
        "PATCH",
    )
    assert upd["name"] == "renamed" and upd["requested_gpu"] == "auto"
    problem(await client.patch(f"/runs/{run['id']}", json={"gpu": "cuda9"}), 422, "gpu_unknown")
    # tenancy: other workspace -> 404 on items and on lists (no existence oracle, like core)
    holder.p = make_principal(user_id=uuid.uuid4(), workspace_ids_roles={world.other_workspace_id: "owner"})
    problem(await client.get(f"/runs/{run['id']}"), 404, "not_found")
    problem(await client.get("/runs", params={"workspace_id": str(world.workspace_id)}), 404, "not_found")
    # PAT scope
    holder.p = make_principal(
        user_id=world.user_id,
        workspace_ids_roles={world.workspace_id: "member"},
        auth_method="pat",
        token_scopes=frozenset({"models:read"}),
        token_workspace_id=world.workspace_id,
    )
    problem(await client.get(f"/runs/{run['id']}"), 403, "insufficient_scope")
    holder.p = make_principal(
        user_id=world.user_id,
        workspace_ids_roles={world.workspace_id: "member"},
        auth_method="pat",
        token_scopes=frozenset({"runs:write"}),
        token_workspace_id=world.workspace_id,
    )
    check(await client.get(f"/runs/{run['id']}"), "/runs/{run_id}")  # runs:write implies runs:read
    # viewer cannot mutate
    holder.p = make_principal(user_id=uuid.uuid4(), workspace_ids_roles={world.workspace_id: "viewer"})
    problem(await client.post(f"/runs/{run['id']}/cancel"), 403, "forbidden")
    v = check(await client.get(f"/runs/{run['id']}"), "/runs/{run_id}")
    assert v["allowed_actions"] == []


async def test_lifecycle_actions(client: httpx.AsyncClient, world: World, sync_engine: Any) -> None:
    run = check(await client.post("/runs", json=run_body(world)), "/runs", "POST")
    rid = run["id"]
    problem(await client.post(f"/runs/{rid}/pause"), 409, "run_invalid_transition")  # queued
    problem(await client.post(f"/runs/{rid}/resume"), 409, "run_invalid_transition")
    # simulate a worker that claimed it
    with Session(sync_engine) as s:
        s.execute(
            update(m.Run)
            .where(m.Run.id == uuid.UUID(rid))
            .values(status=m.RunStatus.RUNNING, gpu_node_id="cuda0", lease_owner="w")
        )
        s.commit()
    p = check(
        await client.post(f"/runs/{rid}/pause", json={"mode": "next_checkpoint"}),
        "/runs/{run_id}/pause",
        "POST",
    )
    assert p["status"] == "pausing" and p["desired_state"] == "pause"
    p = check(await client.post(f"/runs/{rid}/pause", json={"mode": "now"}), "/runs/{run_id}/pause", "POST")
    assert p["desired_state"] == "pause_now"  # upgrade
    c = check(await client.post(f"/runs/{rid}/cancel"), "/runs/{run_id}/cancel", "POST")
    assert c["status"] == "cancelling" and c["desired_state"] == "cancel"  # cancel wins over pause
    assert (
        check(await client.post(f"/runs/{rid}/cancel"), "/runs/{run_id}/cancel", "POST")["status"]
        == "cancelling"
    )
    with Session(sync_engine) as s:
        s.execute(
            update(m.Run)
            .where(m.Run.id == uuid.UUID(rid))
            .values(status=m.RunStatus.PAUSED, resume_checkpoint_step=100)
        )
        s.commit()
    r = check(
        await client.post(f"/runs/{rid}/resume", json={"total_steps": 600, "gpu": "cuda1"}),
        "/runs/{run_id}/resume",
        "POST",
    )
    assert r["status"] == "queued" and r["progress"]["total_steps"] == 600 and r["requested_gpu"] == "cuda1"
    assert r["config"]["train"]["steps"] == 600 and r["desired_state"] == "run"
    c = check(await client.post(f"/runs/{rid}/cancel"), "/runs/{run_id}/cancel", "POST")
    assert c["status"] == "cancelled"
    problem(await client.post(f"/runs/{rid}/pause"), 409, "run_invalid_transition")
    hist = check(
        await client.get(f"/runs/{rid}/events/history", params={"types": "status"}),
        "/runs/{run_id}/events/history",
    )
    assert [(e["data"]["from"], e["data"]["to"]) for e in hist["items"]] == [
        (None, "queued"),
        ("running", "pausing"),
        ("pausing", "cancelling"),
        ("paused", "queued"),
        ("queued", "cancelled"),
    ]
    assert hist["last_seq"] == hist["items"][-1]["seq"]
    after = check(
        await client.get(f"/runs/{rid}/events/history", params={"after_seq": 3}),
        "/runs/{run_id}/events/history",
    )
    assert [e["seq"] for e in after["items"]] == [4, 5]


async def test_failed_resume_rules(client: httpx.AsyncClient, world: World, sync_engine: Any) -> None:
    run = check(await client.post("/runs", json=run_body(world)), "/runs", "POST")
    rid = uuid.UUID(run["id"])
    with Session(sync_engine) as s:
        s.execute(
            update(m.Run)
            .where(m.Run.id == rid)
            .values(status=m.RunStatus.FAILED, error_code="oom", infra_retries_used=1)
        )
        s.commit()
    problem(await client.post(f"/runs/{rid}/resume"), 409, "run_not_resumable")
    with Session(sync_engine) as s:
        s.add(
            m.Checkpoint(
                run_id=rid,
                step=100,
                storage_prefix="s3://x/",
                size_bytes=1,
                has_training_state=True,
                is_last=True,
            )
        )
        s.commit()
    r = check(await client.post(f"/runs/{rid}/resume"), "/runs/{run_id}/resume", "POST")
    assert r["status"] == "queued" and r["infra_retries_used"] == 0 and r["error_code"] is None
    with Session(sync_engine) as s:
        assert s.get(m.Run, rid).resume_checkpoint_step == 100  # type: ignore[union-attr]
    cks = check(await client.get(f"/runs/{rid}/checkpoints"), "/runs/{run_id}/checkpoints")
    assert [c["step"] for c in cks["items"]] == [100]


async def test_clone(client: httpx.AsyncClient, world: World) -> None:
    src = check(await client.post("/runs", json=run_body(world, name="base")), "/runs", "POST")
    cl = await client.post(f"/runs/{src['id']}/clone", json={"config": {"train": {"batch_size": 4}}})
    c = check(cl, "/runs/{run_id}/clone", "POST")
    assert cl.status_code == 201 and c["parent_run_id"] == src["id"] and c["name"] == "base (clone)"
    assert c["config"]["train"]["batch_size"] == 4
    assert (
        c["config"]["train"]["steps"] == 300 and c["config"]["policy"]["chunk_size"] == 50
    )  # kept from source
    cmp_ = check(await client.get("/runs/compare", params={"ids": f"{src['id']},{c['id']}"}), "/runs/compare")
    assert cmp_["config_diff"] == [{"path": "train.batch_size", "values": [8, 4]}]
    problem(await client.get("/runs/compare", params={"ids": src["id"]}), 422, "validation_failed")


async def test_metrics_lttb_csv_and_telemetry(
    client: httpx.AsyncClient, world: World, sync_engine: Any
) -> None:
    run = check(await client.post("/runs", json=run_body(world)), "/runs", "POST")
    rid = uuid.UUID(run["id"])
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    with Session(sync_engine) as s:
        for step in range(1, 301):
            s.add(m.RunMetric(run_id=rid, key="loss", step=step, value=1.0 / step, ts=now))
        s.add(m.RunMetric(run_id=rid, key="grad_norm", step=7, value=float("nan"), ts=now))
        for _ in range(60):
            s.add(
                m.GpuTelemetry(
                    gpu_node_id="cuda0",
                    run_id=rid,
                    ts=now,
                    util_pct=90.0,
                    mem_used_mb=1800,
                    mem_total_mb=12288,
                    temperature_c=60.0,
                    power_w=120.0,
                )
            )
        s.commit()
    body = check(
        await client.get(f"/runs/{rid}/metrics", params={"max_points": 50}), "/runs/{run_id}/metrics"
    )
    by = {x["key"]: x for x in body["series"]}
    assert by["loss"]["downsampled"] and len(by["loss"]["steps"]) == 50
    assert by["loss"]["steps"][0] == 1 and by["loss"]["steps"][-1] == 300
    assert by["grad_norm"]["values"] == [None] and by["grad_norm"]["has_nonfinite"]
    csv = await client.get(f"/runs/{rid}/metrics", params={"format": "csv", "keys": "grad_norm"})
    assert csv.text.splitlines()[0] == "step,key,value,ts" and ",grad_norm,nan," in csv.text
    tel = check(
        await client.get(f"/runs/{rid}/telemetry", params={"max_points": 50}), "/runs/{run_id}/telemetry"
    )
    assert 30 <= len(tel["items"]) <= 50


async def test_gpus_queue_jobs_admin(
    client: httpx.AsyncClient, world: World, holder: PrincipalHolder, sync_engine: Any
) -> None:
    a = check(await client.post("/runs", json=run_body(world)), "/runs", "POST")
    gpus = check(await client.get("/gpus"), "/gpus")
    assert [g["id"] for g in gpus["items"]] == ["cuda0", "cuda1"]
    assert all(g["status"] == "offline" for g in gpus["items"])  # no heartbeat yet
    with Session(sync_engine) as s:
        s.execute(
            text("UPDATE gpu_nodes SET last_heartbeat_at = now(), current_run_id = :r WHERE id='cuda0'"),
            {"r": a["id"]},
        )
        s.commit()
    gpus = check(await client.get("/gpus"), "/gpus")
    assert gpus["items"][0]["status"] == "online" and gpus["items"][0]["current_run"]["id"] == a["id"]
    q = check(await client.get("/queue"), "/queue")
    assert q["items"][0]["run_id"] == a["id"] and q["items"][0]["position"] == 1
    holder.p = make_principal(user_id=uuid.uuid4(), workspace_ids_roles={world.other_workspace_id: "owner"})
    q = check(await client.get("/queue"), "/queue")
    assert q["items"][0]["run_id"] is None  # anonymised
    assert check(await client.get("/gpus"), "/gpus")["items"][0]["current_run"]["id"] is None
    problem(await client.patch("/admin/gpus/cuda1", json={"status": "draining"}), 403, "forbidden")
    holder.p = make_principal(
        user_id=world.user_id,
        workspace_ids_roles={world.workspace_id: "member"},
        is_platform_admin=True,
        mfa_verified=True,
    )
    g = check(
        await client.patch("/admin/gpus/cuda1", json={"status": "draining"}), "/admin/gpus/{gpu_id}", "PATCH"
    )
    assert g["status"] == "draining"
    # jobs
    await client.post("/runs/preflight", json=run_body(world))
    jobs = check(await client.get("/jobs", params={"workspace_id": str(world.workspace_id)}), "/jobs")
    jid = jobs["items"][0]["id"]
    check(await client.get(f"/jobs/{jid}"), "/jobs/{job_id}")
    j = check(await client.post(f"/jobs/{jid}/cancel"), "/jobs/{job_id}/cancel", "POST")
    assert j["status"] == "cancelled"
    with Session(sync_engine) as s:
        s.execute(text("UPDATE jobs SET status='succeeded'"))
        s.commit()
    problem(await client.post(f"/jobs/{jid}/cancel"), 409, "job_not_cancellable")


async def test_reaper_requeues_then_fails(client: httpx.AsyncClient, world: World, sync_engine: Any) -> None:
    from app.runs.reaper import reap_once

    run = check(await client.post("/runs", json=run_body(world)), "/runs", "POST")
    rid = uuid.UUID(run["id"])
    with Session(sync_engine) as s:
        s.execute(
            text(
                "UPDATE runs SET status='running', lease_owner='dead', gpu_node_id='cuda0', attempt=1, "
                "lease_expires_at = now() - interval '1 second' WHERE id=:r"
            ),
            {"r": rid},
        )
        s.execute(text("UPDATE gpu_nodes SET current_run_id=:r WHERE id='cuda0'"), {"r": rid})
        s.add(
            m.Checkpoint(
                run_id=rid,
                step=100,
                storage_prefix="s3://x/",
                size_bytes=1,
                has_training_state=True,
                is_last=True,
            )
        )
        s.commit()
    st = client.app.state.runs  # type: ignore[attr-defined]
    done = await reap_once(st.sessionmaker, st.redis)
    assert done == [f"{rid}:queued"]
    with Session(sync_engine) as s:
        r = s.get(m.Run, rid)
        assert r is not None and r.infra_retries_used == 1 and r.resume_checkpoint_step == 100
        assert r.lease_owner is None and r.gpu_node_id is None
        assert s.scalar(text("SELECT current_run_id FROM gpu_nodes WHERE id='cuda0'")) is None
        s.execute(
            text(
                "UPDATE runs SET status='running', lease_owner='dead2', "
                "lease_expires_at = now() - interval '1 second' WHERE id=:r"
            ),
            {"r": rid},
        )
        s.commit()
    assert await reap_once(st.sessionmaker, st.redis) == [f"{rid}:failed"]
    hist = check(
        await client.get(f"/runs/{rid}/events/history", params={"types": "error,warning"}),
        "/runs/{run_id}/events/history",
    )
    assert [e["data"]["code"] for e in hist["items"]] == [
        "worker_lost",
        "retrying_after_infra_error",
        "worker_lost",
    ]
    got = check(await client.get(f"/runs/{rid}"), "/runs/{run_id}")
    assert (
        got["status"] == "failed"
        and got["error_code"] == "worker_lost"
        and "resume" in got["allowed_actions"]
    )


async def test_reaper_honours_user_intent_and_leader_lock(
    client: httpx.AsyncClient, world: World, sync_engine: Any
) -> None:
    import asyncio

    from app.runs.reaper import LOCK_ID, reap_once, reaper_loop

    a = check(await client.post("/runs", json=run_body(world)), "/runs", "POST")
    b = check(await client.post("/runs", json=run_body(world)), "/runs", "POST")
    with Session(sync_engine) as s:
        for rid, st in ((a["id"], "cancelling"), (b["id"], "pausing")):
            s.execute(
                text(
                    "UPDATE runs SET status=:st, lease_owner='dead', "
                    "lease_expires_at = now() - interval '1 s' "
                    "WHERE id=:r"
                ),
                {"r": rid, "st": st},
            )
        s.commit()
    st = client.app.state.runs  # type: ignore[attr-defined]
    done = sorted(await reap_once(st.sessionmaker, st.redis))
    assert done == sorted([f"{a['id']}:cancelled", f"{b['id']}:paused"])
    # leader election: while another session holds the advisory lock, the loop does nothing
    with sync_engine.connect() as holder_conn:
        assert holder_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_ID}).scalar()
        holder_conn.commit()
        c = check(await client.post("/runs", json=run_body(world)), "/runs", "POST")
        with Session(sync_engine) as s:
            s.execute(
                text(
                    "UPDATE runs SET status='running', lease_owner='x', "
                    "lease_expires_at = now() - interval '1 s' WHERE id=:r"
                ),
                {"r": c["id"]},
            )
            s.commit()
        # a one-connection pool: the leader must not keep its lock connection in it
        from sqlalchemy.ext.asyncio import create_async_engine

        app_engine = create_async_engine(st.engine.url, pool_size=1, max_overflow=0, pool_timeout=2)
        task = asyncio.create_task(reaper_loop(app_engine, st.sessionmaker, st.redis, 0.2))
        await asyncio.sleep(1.0)
        with Session(sync_engine) as s:
            assert s.scalar(text("SELECT status FROM runs WHERE id=:r"), {"r": c["id"]}) == "running"
        holder_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_ID})
        holder_conn.commit()
    for _ in range(50):
        await asyncio.sleep(0.2)
        with Session(sync_engine) as s:
            if s.scalar(text("SELECT status FROM runs WHERE id=:r"), {"r": c["id"]}) == "queued":
                break
    # the leader's lock connection is its own, not one of the API pool's connections
    assert app_engine.sync_engine.pool.checkedout() == 0  # type: ignore[attr-defined]
    async with app_engine.connect() as conn:  # would time out if the reaper held the only slot
        assert (await conn.execute(text("SELECT 1"))).scalar() == 1
    task.cancel()
    await app_engine.dispose()
    with Session(sync_engine) as s:
        assert s.scalar(text("SELECT status FROM runs WHERE id=:r"), {"r": c["id"]}) == "queued"
