"""Regression tests for the phase-4 QA findings fixed in phase 5 (docs/qa/phase4-findings.md):
SEC-input-1 (init_from.hf_repo_id allow-list), QC-backend-07 (concurrent checkpoint export),
QC-backend-02 (re-export of a failed model) and the runs-side tenancy rule (non-member => 404)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import models as m
from tests.runs.conftest import PrincipalHolder, World, check, make_principal, problem, run_body


def _init_check(body: dict[str, Any]) -> dict[str, Any]:
    checks = body["params"]["checks"] if "params" in body else body["checks"]
    return next(c for c in checks if c["id"] == "init_from" and c["severity"] == "error")


async def test_hf_init_from_is_refused_unless_allow_listed(
    client: httpx.AsyncClient, world: World, sync_engine: Any
) -> None:
    """SEC-input-1: an arbitrary Hub repo as init_from would run its processor code on the worker."""
    body = run_body(world, init_from={"hf_repo_id": "attacker/evil"})
    pf = check(await client.post("/runs/preflight", json=body), "/runs/preflight", "POST")
    assert pf["ok"] is False
    c = _init_check(pf)
    assert c["code"] == "forbidden" and c["params"]["reason"] == "hf_repo_not_allowed"
    err = problem(await client.post("/runs", json=body), 422, "preflight_failed")
    assert _init_check(err)["params"]["hf_repo_id"] == "attacker/evil"
    with Session(sync_engine) as s:
        assert (
            s.scalar(text("SELECT count(*) FROM runs WHERE workspace_id = :w"), {"w": world.workspace_id})
            == 0
        )

    # platform admin approves a repo (case-insensitive): accepted, still flagged as a hub download
    client.app.state.runs.settings.init_from_hf_allowlist = frozenset({"lerobot/act_base"})  # type: ignore[attr-defined]
    ok = run_body(world, init_from={"hf_repo_id": "LeRobot/act_base"})
    pf = check(await client.post("/runs/preflight", json=ok), "/runs/preflight", "POST")
    assert pf["ok"] is True and any(c["code"] == "hub_download" for c in pf["checks"])
    run = check(await client.post("/runs", json=ok), "/runs", "POST")
    # cloning keeps init_from and is checked again; still allowed while on the list ...
    check(await client.post(f"/runs/{run['id']}/clone", json={}), "/runs/{run_id}/clone", "POST")
    # ... and refused once the admin removes it (also resume of the existing run)
    client.app.state.runs.settings.init_from_hf_allowlist = frozenset()  # type: ignore[attr-defined]
    problem(await client.post(f"/runs/{run['id']}/clone", json={}), 422, "preflight_failed")
    with Session(sync_engine) as s:
        s.execute(text("UPDATE runs SET status = 'paused' WHERE id = :i"), {"i": run["id"]})
        s.commit()
    err = problem(await client.post(f"/runs/{run['id']}/resume"), 403, "forbidden")
    assert err["params"]["reason"] == "hf_repo_not_allowed"


async def _run_with_checkpoint(client: httpx.AsyncClient, world: World, sync_engine: Any) -> uuid.UUID:
    run = check(await client.post("/runs", json=run_body(world)), "/runs", "POST")
    rid = uuid.UUID(run["id"])
    with Session(sync_engine) as s:
        s.add(
            m.Checkpoint(
                run_id=rid, step=100, storage_prefix="s3://x/", size_bytes=1, has_training_state=True
            )
        )
        s.commit()
    return rid


async def test_concurrent_checkpoint_export_never_500(
    client: httpx.AsyncClient, world: World, sync_engine: Any
) -> None:
    """QC-backend-07: racing exports of one checkpoint give one 202 (+ 200s), one model, one job."""
    rid = await _run_with_checkpoint(client, world, sync_engine)
    url = f"/runs/{rid}/checkpoints/100/export"
    rs = await asyncio.gather(*(client.post(url) for _ in range(4)))
    codes = sorted(r.status_code for r in rs)
    assert codes == [200, 200, 200, 202], [r.text[:200] for r in rs]
    for r in rs:
        check(r, "/runs/{run_id}/checkpoints/{step}/export", "POST")
    assert len({r.json()["id"] for r in rs}) == 1
    with Session(sync_engine) as s:
        assert s.scalar(text("SELECT count(*) FROM models WHERE run_id = :r"), {"r": rid}) == 1
        assert (
            s.scalar(
                text("SELECT count(*) FROM jobs WHERE run_id = :r AND kind = 'export_model'"), {"r": rid}
            )
            == 1
        )


async def test_failed_export_can_be_retried(
    client: httpx.AsyncClient, world: World, sync_engine: Any
) -> None:
    """QC-backend-02: a failed model no longer blocks re-exporting its checkpoint."""
    rid = await _run_with_checkpoint(client, world, sync_engine)
    url = f"/runs/{rid}/checkpoints/100/export"
    first = await client.post(url)
    assert first.status_code == 202
    assert (await client.post(url)).status_code == 200  # pending: returned as is
    with Session(sync_engine) as s:
        s.execute(text("UPDATE models SET status = 'failed' WHERE id = :i"), {"i": first.json()["id"]})
        # the worker fails the export job together with its model (N6: a still-queued job would
        # occupy the requester's export/eval slot)
        s.execute(text("UPDATE jobs SET status = 'failed' WHERE model_id = :i"), {"i": first.json()["id"]})
        s.commit()
    again = await client.post(url)
    assert again.status_code == 202, again.text
    assert again.json()["id"] != first.json()["id"] and again.json()["status"] == "pending"
    with Session(sync_engine) as s:
        live = s.execute(
            text("SELECT id FROM models WHERE run_id = :r AND deleted_at IS NULL"), {"r": rid}
        ).all()
        assert [str(x[0]) for x in live] == [again.json()["id"]]
        assert (
            s.scalar(
                text("SELECT count(*) FROM jobs WHERE run_id = :r AND kind = 'export_model'"), {"r": rid}
            )
            == 2
        )


async def test_non_member_gets_404_on_workspace_scoped_endpoints(
    client: httpx.AsyncClient, world: World, holder: PrincipalHolder
) -> None:
    """Tenancy (D13, same as core ensure_role): naming a workspace you are not in => 404, not 403."""
    holder.p = make_principal(
        user_id=world.other_user_id, workspace_ids_roles={world.other_workspace_id: "owner"}
    )
    ws = str(world.workspace_id)
    for path, spec in (("/runs", "/runs"), ("/models", "/models"), ("/jobs", "/jobs")):
        r = await client.get(path, params={"workspace_id": ws})
        problem(r, 404, "not_found")
        check(r, spec)
    problem(await client.post("/runs", json=run_body(world)), 404, "not_found")
    problem(await client.post("/runs/preflight", json=run_body(world)), 404, "not_found")
    # a PAT naming another workspace still gets 403 (it knows its own workspace)
    holder.p = make_principal(
        user_id=world.user_id,
        workspace_ids_roles={world.workspace_id: "member"},
        auth_method="pat",
        token_scopes=frozenset({"runs:write"}),
        token_workspace_id=world.workspace_id,
    )
    problem(
        await client.get("/runs", params={"workspace_id": str(world.other_workspace_id)}), 403, "forbidden"
    )
