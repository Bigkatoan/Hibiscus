"""Models API: listModels, getModel, updateModel, deleteModel, downloadModel, listModelFiles,
getModelFile, pushModelToHub, reverifyModel. Bundle *contents* are produced by A5 (worker/export).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Path, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select

from app.core import audit
from app.core.audit import AuditAction
from app.core.errors import ErrorCode, ProblemError
from app.core.pagination import decode_cursor, encode_cursor
from app.db.models import (
    Dataset,
    DatasetVersion,
    Job,
    JobKind,
    JobResource,
    JobStatus,
    Model,
    ModelStatus,
    Run,
    User,
    UserSecret,
    UserSecretKind,
)
from app.models.zipindex import ZipError, read_index, stream_member
from app.runs.deps import (
    DB,
    CurrentPrincipal,
    Principal,
    forbid_pat,
    require_scope,
    role_at_least,
    workspace_role,
)
from app.runs.serialize import job_to_dict, model_to_dict
from app.runs.storage import parse_s3_uri

router = APIRouter(tags=["models"])
RANGE_RE = re.compile(r"^bytes=(\d+)-(\d*)$")


async def _load(db: DB, p: Principal, model_id: uuid.UUID) -> tuple[Model, str]:
    m = await db.get(Model, model_id)
    if m is None or m.deleted_at is not None:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "model not found")
    role = workspace_role(p, m.workspace_id)
    return m, role


async def _dict(db: DB, m: Model) -> dict[str, Any]:
    run = await db.get(Run, m.run_id)
    if run is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "run of model not found")
    dv = await db.get(DatasetVersion, run.dataset_version_id)
    ds = await db.get(Dataset, dv.dataset_id) if dv else None
    creator = await db.get(User, m.created_by or run.created_by)
    return model_to_dict(m, run=run, dataset=ds, version=dv, creator=creator)


def _parse_range(range_: str | None, size: int) -> tuple[int, int, bool]:
    if not range_:
        return 0, size - 1, False
    mt = RANGE_RE.match(range_)
    if mt is None:
        raise ProblemError(416, ErrorCode.RANGE_NOT_SATISFIABLE, "unsupported Range")
    start = int(mt.group(1))
    end = min(int(mt.group(2)), size - 1) if mt.group(2) else size - 1
    if start >= size or start > end:
        raise ProblemError(
            416, ErrorCode.RANGE_NOT_SATISFIABLE, f"resource has {size} bytes", params={"size": size}
        )
    return start, end, True


@router.get("/models", operation_id="listModels")
async def list_models(
    db: DB,
    principal: CurrentPrincipal,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID | None = None,
    policy_type: str | None = None,
    verified: bool | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> dict[str, Any]:
    workspace_role(principal, workspace_id, for_list=True)
    require_scope(principal, "models:read")
    stmt = select(Model).where(Model.workspace_id == workspace_id, Model.deleted_at.is_(None))
    if run_id:
        stmt = stmt.where(Model.run_id == run_id)
    if policy_type:
        stmt = stmt.where(Model.policy_type == policy_type)
    if verified is not None:
        stmt = stmt.where(Model.verified.is_(verified))
    if q:
        stmt = stmt.where(Model.name.ilike("%" + q.replace("%", r"\%").replace("_", r"\_") + "%"))
    if cursor:
        c = decode_cursor(cursor)
        ts = datetime.fromisoformat(c["t"])
        stmt = stmt.where(
            (Model.created_at < ts) | ((Model.created_at == ts) & (Model.id < uuid.UUID(c["i"])))
        )
    rows = list(
        (await db.execute(stmt.order_by(Model.created_at.desc(), Model.id.desc()).limit(limit + 1))).scalars()
    )
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        nxt = encode_cursor({"t": rows[-1].created_at.isoformat(), "i": str(rows[-1].id)})
    return {"items": [await _dict(db, m) for m in rows], "next_cursor": nxt}


@router.get("/models/{model_id}", operation_id="getModel")
async def get_model(model_id: uuid.UUID, db: DB, principal: CurrentPrincipal) -> dict[str, Any]:
    m, _ = await _load(db, principal, model_id)
    require_scope(principal, "models:read")
    return await _dict(db, m)


def _require_writer(m: Model, p: Principal, role: str) -> None:
    forbid_pat(p)
    if not role_at_least(role, "member") or (m.created_by != p.user_id and not role_at_least(role, "admin")):
        raise ProblemError(403, ErrorCode.FORBIDDEN, "cannot modify this model")


@router.patch("/models/{model_id}", operation_id="updateModel")
async def update_model(
    model_id: uuid.UUID, body: dict[str, Any], db: DB, principal: CurrentPrincipal
) -> dict[str, Any]:
    from app.runs.schemas import ModelUpdate

    upd = ModelUpdate.model_validate(body)
    m, role = await _load(db, principal, model_id)
    _require_writer(m, principal, role)
    m.name = upd.name
    await db.commit()
    await db.refresh(m)
    return await _dict(db, m)


@router.delete("/models/{model_id}", operation_id="deleteModel", status_code=204)
async def delete_model(model_id: uuid.UUID, db: DB, principal: CurrentPrincipal) -> Response:
    m, role = await _load(db, principal, model_id)
    _require_writer(m, principal, role)
    m.deleted_at = datetime.now(UTC)
    await audit.record(
        AuditAction.MODEL_DELETED,
        db=db,
        actor=principal,
        workspace_id=m.workspace_id,
        target_type="model",
        target_id=str(m.id),
    )
    await db.commit()
    return Response(status_code=204)


@router.get("/models/{model_id}/download", operation_id="downloadModel", response_model=None)
async def download_model(
    model_id: uuid.UUID,
    request: Request,
    db: DB,
    principal: CurrentPrincipal,
    range_: Annotated[str | None, Header(alias="Range")] = None,
    if_range: Annotated[str | None, Header(alias="If-Range")] = None,
) -> Response:
    m, _ = await _load(db, principal, model_id)
    require_scope(principal, "models:read")
    if m.status != ModelStatus.READY or not m.bundle_uri:
        raise ProblemError(409, ErrorCode.MODEL_NOT_READY, f"model is {m.status.value}")
    st = request.app.state.runs
    bucket, key = parse_s3_uri(m.bundle_uri)
    info = await st.store.head(bucket, key)
    if info is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "bundle object missing")
    etag = f'"{m.bundle_sha256 or info.etag}"'
    if if_range is not None and if_range != etag:
        range_ = None
    start, end, partial = _parse_range(range_, info.size)
    headers = {
        "ETag": etag,
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'attachment; filename="{key.rsplit("/", 1)[-1]}"',
        "Content-Length": str(end - start + 1),
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{info.size}"
    await audit.record(
        AuditAction.MODEL_DOWNLOADED,
        db=db,
        actor=principal,
        workspace_id=m.workspace_id,
        target_type="model",
        target_id=str(m.id),
        details={"bytes": end - start + 1, "range": range_},
    )
    await db.commit()
    return StreamingResponse(
        st.store.stream(bucket, key, start, end),
        status_code=206 if partial else 200,
        media_type="application/zip",
        headers=headers,
    )


@router.get("/models/{model_id}/files", operation_id="listModelFiles")
async def list_model_files(model_id: uuid.UUID, db: DB, principal: CurrentPrincipal) -> Any:
    m, _ = await _load(db, principal, model_id)
    require_scope(principal, "models:read")
    if m.status != ModelStatus.READY or not m.manifest:
        raise ProblemError(409, ErrorCode.MODEL_NOT_READY, f"model is {m.status.value}")
    return m.manifest


@router.get("/models/{model_id}/files/{path:path}", operation_id="getModelFile", response_model=None)
async def get_model_file(
    model_id: uuid.UUID,
    path: Annotated[str, Path(max_length=512)],
    request: Request,
    db: DB,
    principal: CurrentPrincipal,
    range_: Annotated[str | None, Header(alias="Range")] = None,
) -> Response:
    m, _ = await _load(db, principal, model_id)
    require_scope(principal, "models:read")
    if m.status != ModelStatus.READY or not m.manifest or not m.bundle_uri:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "file not found")
    entry = next((f for f in m.manifest.get("files", []) if f.get("path") == path), None)
    if entry is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "file not listed in MANIFEST.json")
    st = request.app.state.runs
    bucket, key = parse_s3_uri(m.bundle_uri)
    info = await st.store.head(bucket, key)
    if info is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "bundle object missing")

    async def fetch(lo: int, hi: int) -> bytes:
        data: bytes = await st.store.get_bytes(bucket, key, lo, hi)
        return data

    try:
        index = await read_index(fetch, info.size)
    except ZipError as exc:
        raise ProblemError(500, ErrorCode.INTERNAL_ERROR, f"bundle unreadable: {exc}") from exc
    bundle_name = str(m.manifest.get("bundle_name", ""))
    member = index.get(f"{bundle_name}/{path}") or index.get(path)
    if member is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "file missing from bundle")
    if member.size == 0:
        return Response(b"", media_type="application/octet-stream", headers={"ETag": f'"{entry["sha256"]}"'})
    start, end, partial = _parse_range(range_, member.size)
    headers = {
        "ETag": f'"{entry["sha256"]}"',
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{member.size}"
    await audit.record(
        AuditAction.MODEL_FILE_DOWNLOADED,
        db=db,
        actor=principal,
        workspace_id=m.workspace_id,
        target_type="model",
        target_id=str(m.id),
        details={"path": path, "range": range_},
    )
    await db.commit()
    return StreamingResponse(
        stream_member(fetch, member, start, end),
        status_code=206 if partial else 200,
        media_type="application/octet-stream",
        headers=headers,
    )


@router.post("/models/{model_id}/push-hub", operation_id="pushModelToHub", status_code=202)
async def push_model_hub(
    model_id: uuid.UUID, body: dict[str, Any], request: Request, db: DB, principal: CurrentPrincipal
) -> JSONResponse:
    from app.runs.schemas import HubPushRequest

    try:
        req = HubPushRequest.model_validate(body)
    except ValueError as exc:
        raise ProblemError(422, ErrorCode.HUB_REPO_INVALID, "invalid Hub repository id") from exc
    m, role = await _load(db, principal, model_id)
    _require_writer(m, principal, role)
    if not request.app.state.runs.settings.hub_push_enabled:
        # QC-backend-02: no worker runs push_model_hub jobs in this deployment; do not enqueue a job
        # (and audit a push) that nobody will ever process.
        raise ProblemError(
            501,
            ErrorCode.SERVICE_UNAVAILABLE,
            "pushing models to the Hugging Face Hub is not enabled on this server",
            params={"feature": "push_model_hub", "reason": "feature_disabled"},
        )
    if m.status != ModelStatus.READY:
        raise ProblemError(409, ErrorCode.MODEL_NOT_READY, f"model is {m.status.value}")
    has_token = await db.scalar(
        select(UserSecret.id).where(
            UserSecret.user_id == principal.user_id, UserSecret.kind == UserSecretKind.HF_TOKEN
        )
    )
    if has_token is None:
        raise ProblemError(409, ErrorCode.HF_TOKEN_MISSING, "store a Hugging Face token first")
    job = Job(
        workspace_id=m.workspace_id,
        kind=JobKind.PUSH_MODEL_HUB,
        resource=JobResource.CPU,
        payload=req.model_dump(),
        model_id=m.id,
        run_id=m.run_id,
        created_by=principal.user_id,
    )
    db.add(job)
    await db.flush()
    await audit.record(
        AuditAction.MODEL_PUSHED_HUB,
        db=db,
        actor=principal,
        workspace_id=m.workspace_id,
        target_type="model",
        target_id=str(m.id),
        details={"repo_id": req.repo_id, "job_id": str(job.id)},
    )
    await db.commit()
    await db.refresh(job)
    return JSONResponse(job_to_dict(job), status_code=202)


@router.post("/models/{model_id}/verify", operation_id="reverifyModel", status_code=202)
async def reverify_model(model_id: uuid.UUID, db: DB, principal: CurrentPrincipal) -> JSONResponse:
    m, role = await _load(db, principal, model_id)
    _require_writer(m, principal, role)
    if m.status != ModelStatus.READY:
        raise ProblemError(409, ErrorCode.MODEL_NOT_READY, f"model is {m.status.value}")
    busy = await db.scalar(
        select(Job.id).where(
            Job.model_id == m.id,
            Job.kind == JobKind.EXPORT_MODEL,
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    )
    if busy is not None:
        raise ProblemError(409, ErrorCode.CONFLICT, "a job for this model is already queued")
    job = Job(
        workspace_id=m.workspace_id,
        kind=JobKind.EXPORT_MODEL,
        resource=JobResource.GPU,
        payload={
            "verify_only": True,
            "checkpoint_id": str(m.checkpoint_id),
            "step": m.step,
            "user_requested": True,
        },
        model_id=m.id,
        run_id=m.run_id,
        created_by=principal.user_id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return JSONResponse(job_to_dict(job), status_code=202)
