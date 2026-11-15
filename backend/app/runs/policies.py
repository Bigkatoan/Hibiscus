"""``listPolicies`` / ``getPolicy`` (api/policy-schemas served verbatim, D5).

PATs need ``runs:read`` (``runs:write`` implies it), like ``listGpus`` / ``getQueue``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.core.errors import ErrorCode, ProblemError
from app.db.models import GpuNode
from app.runs.catalog import POLICY_TYPES, get_catalog, summary
from app.runs.deps import DB, CurrentPrincipal, require_scope

router = APIRouter(tags=["policies"])


async def _gpus(db: DB) -> list[tuple[str, int]]:
    rows = (await db.execute(select(GpuNode.name, GpuNode.total_vram_mb).order_by(GpuNode.id))).all()
    return [(str(n), int(v)) for n, v in rows]


@router.get("/policies", operation_id="listPolicies")
async def list_policies(db: DB, principal: CurrentPrincipal) -> dict[str, Any]:
    require_scope(principal, "runs:read")
    cat = get_catalog()
    gpus = await _gpus(db)
    return {"lerobot_version": cat.lerobot_version, "items": [summary(cat, p, gpus) for p in POLICY_TYPES]}


@router.get("/policies/{policy_type}", operation_id="getPolicy")
async def get_policy(
    policy_type: str, request: Request, response: Response, db: DB, principal: CurrentPrincipal
) -> Any:
    require_scope(principal, "runs:read")
    cat = get_catalog()
    if policy_type not in cat.schemas:
        raise ProblemError(404, ErrorCode.POLICY_UNKNOWN, f"unknown policy {policy_type}")
    etag = cat.etags[policy_type]
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    body = summary(cat, policy_type, await _gpus(db))
    body["policy_schema"] = cat.policy_schema(policy_type)
    body["train_schema"] = cat.train_schema
    body["presets"] = cat.presets_for(policy_type)
    return body
