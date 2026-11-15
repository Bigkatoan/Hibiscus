"""Regression tests for the phase-5 re-verification residuals (docs/security/phase5-reverify.md):
N5 (Hub model references outside an allow-list) and N6 (user-requested GPU jobs vs quota)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import models as m
from app.runs.settings import RunsSettings, hub_model_allowed
from tests.runs.conftest import World, check, problem, run_body


def _hub_errors(pf: dict[str, Any]) -> list[dict[str, Any]]:
    checks = pf["params"]["checks"] if "params" in pf else pf["checks"]
    return [c for c in checks if c.get("params", {}).get("reason") == "hub_model_not_allowed"]


def _smolvla(world: World, vlm: str | None) -> dict[str, Any]:
    policy: dict[str, Any] = {} if vlm is None else {"vlm_model_name": vlm}
    return run_body(
        world,
        policy_type="smolvla",
        config={"policy": policy, "train": {"steps": 300, "save_freq": 100}},
    )


@pytest.mark.parametrize(
    "vlm",
    [
        "attacker/evil-vlm",
        "/models/SmolVLM2-500M-Video-Instruct",
        "./HuggingFaceTB/SmolVLM2-500M-Video-Instruct",
        "../../etc",
        "HuggingFaceTB/../evil",
        "https://evil.example.com/HuggingFaceTB/SmolVLM2-500M-Video-Instruct",
    ],
)
async def test_smolvla_vlm_model_name_outside_allow_list_is_refused(
    client: httpx.AsyncClient, world: World, vlm: str
) -> None:
    body = _smolvla(world, vlm)
    pf = check(await client.post("/runs/preflight", json=body), "/runs/preflight", "POST")
    assert pf["ok"] is False
    (err,) = _hub_errors(pf)
    assert err["severity"] == "error" and err["params"]["field"] == "policy.vlm_model_name"
    r = await client.post("/runs", json=body)
    assert r.status_code in (400, 422), r.text


async def test_smolvla_default_vlm_is_allowed(client: httpx.AsyncClient, world: World) -> None:
    for vlm in (
        None,
        "HuggingFaceTB/SmolVLM2-500M-Video-Instruct",
        "huggingfacetb/smolvlm2-500m-video-instruct",
    ):
        pf = check(await client.post("/runs/preflight", json=_smolvla(world, vlm)), "/runs/preflight", "POST")
        assert _hub_errors(pf) == []


async def test_platform_allow_list_extends_vlm_models(client: httpx.AsyncClient, world: World) -> None:
    client.app.state.runs.settings.vlm_model_allowlist = frozenset({"myorg/vlm"})  # type: ignore[attr-defined]
    pf = check(
        await client.post("/runs/preflight", json=_smolvla(world, "MyOrg/vlm")), "/runs/preflight", "POST"
    )
    assert _hub_errors(pf) == []


async def test_resume_of_stored_run_with_bad_vlm_is_refused(
    client: httpx.AsyncClient, world: World, sync_engine: Any
) -> None:
    run = check(await client.post("/runs", json=run_body(world)), "/runs", "POST")
    with Session(sync_engine) as s:
        s.execute(
            text(
                "UPDATE runs SET status = 'paused', "
                "config = jsonb_set(config, '{policy,vlm_model_name}', '\"attacker/evil\"') WHERE id = :i"
            ),
            {"i": run["id"]},
        )
        s.commit()
    err = problem(await client.post(f"/runs/{run['id']}/resume"), 403, "forbidden")
    assert err["params"]["reason"] == "hub_model_not_allowed"


def test_hub_model_allowed_and_env_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    allow = frozenset({"huggingfacetb/smolvlm2-500m-video-instruct"})
    assert hub_model_allowed("HuggingFaceTB/SmolVLM2-500M-Video-Instruct", allow)
    for bad in ("/abs/path", "~/x", "a/b/c", "a", "C:\\models\\x", "a/..", 42, None):
        assert not hub_model_allowed(bad, allow)
    monkeypatch.setenv("HIBISCUS_VLM_MODEL_ALLOWLIST", "Org/One, org/two")
    assert RunsSettings().vlm_model_allowlist == frozenset({"org/one", "org/two"})
    monkeypatch.delenv("HIBISCUS_VLM_MODEL_ALLOWLIST")
    assert "huggingfacetb/smolvlm2-500m-video-instruct" in RunsSettings().vlm_model_allowlist


# ---------------------------------------------------------------------------------------------
# N6: user-requested export / eval GPU jobs obey the quota
# ---------------------------------------------------------------------------------------------
async def _run_with_checkpoints(client: httpx.AsyncClient, world: World, sync_engine: Any) -> str:
    run = check(await client.post("/runs", json=run_body(world)), "/runs", "POST")
    with Session(sync_engine) as s:
        for step in (100, 200, 300):
            s.add(
                m.Checkpoint(
                    run_id=uuid.UUID(run["id"]),
                    step=step,
                    storage_prefix="s3://x/",
                    size_bytes=1,
                    has_training_state=True,
                )
            )
        s.commit()
    return str(run["id"])


def _set_quota(sync_engine: Any, world: World, **vals: Any) -> None:
    with Session(sync_engine) as s:
        s.add(m.Quota(workspace_id=world.workspace_id, user_id=world.user_id, **vals))
        s.commit()


async def test_export_and_eval_refused_when_gpu_hours_exhausted(
    client: httpx.AsyncClient, world: World, sync_engine: Any
) -> None:
    rid = await _run_with_checkpoints(client, world, sync_engine)
    _set_quota(sync_engine, world, gpu_hours_per_month=0.0)
    for url in (f"/runs/{rid}/checkpoints/100/export", f"/runs/{rid}/checkpoints/100/eval"):
        err = problem(await client.post(url), 403, "quota_exceeded")
        assert err["params"]["reason"] == "gpu_hours"
    with Session(sync_engine) as s:
        assert s.scalar(text("SELECT count(*) FROM jobs WHERE run_id = :r"), {"r": rid}) == 0
        assert s.scalar(text("SELECT count(*) FROM models WHERE run_id = :r"), {"r": rid}) == 0


async def test_export_and_eval_jobs_capped_by_max_concurrent(
    client: httpx.AsyncClient, world: World, sync_engine: Any
) -> None:
    rid = await _run_with_checkpoints(client, world, sync_engine)
    _set_quota(sync_engine, world, max_concurrent_runs=2)
    assert (await client.post(f"/runs/{rid}/checkpoints/100/export")).status_code == 202
    assert (await client.post(f"/runs/{rid}/checkpoints/200/eval")).status_code == 202
    err = problem(await client.post(f"/runs/{rid}/checkpoints/300/eval"), 403, "quota_exceeded")
    assert err["params"] == {"reason": "concurrent_jobs", "limit": 2}
    problem(await client.post(f"/runs/{rid}/checkpoints/300/export"), 403, "quota_exceeded")
    # once a job finishes, the slot is free again
    with Session(sync_engine) as s:
        s.execute(
            text("UPDATE jobs SET status = 'succeeded' WHERE run_id = :r AND kind = 'eval_checkpoint'"),
            {"r": rid},
        )
        s.commit()
    assert (await client.post(f"/runs/{rid}/checkpoints/300/eval")).status_code == 202


async def test_user_requested_job_time_counts_toward_gpu_hours(
    client: httpx.AsyncClient, world: World, sync_engine: Any
) -> None:
    rid = await _run_with_checkpoints(client, world, sync_engine)
    _set_quota(sync_engine, world, gpu_hours_per_month=0.0001, max_concurrent_runs=5)
    assert (await client.post(f"/runs/{rid}/checkpoints/100/eval")).status_code == 202
    # the eval ran for 2 h on the GPU (clamped to this month's start)
    with Session(sync_engine) as s:
        s.execute(
            text(
                "UPDATE jobs SET status = 'succeeded', finished_at = now(), started_at = greatest("
                "now() - interval '2 hours', date_trunc('month', now())) WHERE run_id = :r"
            ),
            {"r": rid},
        )
        s.commit()
    err = problem(await client.post(f"/runs/{rid}/checkpoints/200/eval"), 403, "quota_exceeded")
    assert err["params"]["reason"] == "gpu_hours"
