"""Generic job endpoints: ``listJobs``, ``getJob``, ``cancelJob`` (all job kinds)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.errors import ErrorCode, ProblemError
from app.core.pagination import decode_cursor, encode_cursor
from app.db.models import Job, JobKind, JobStatus
from app.runs.deps import (
    DB,
    CurrentPrincipal,
    Principal,
    has_scope,
    require_scope,
    role_at_least,
    workspace_role,
)
from app.runs.serialize import job_to_dict

router = APIRouter(tags=["jobs"])

DATASET_KINDS = {JobKind.VALIDATE_DATASET, JobKind.IMPORT_HF_DATASET, JobKind.MERGE_DATASETS}
MODEL_KINDS = {JobKind.EXPORT_MODEL, JobKind.PUSH_MODEL_HUB}


def _read_scope_ok(p: Principal, job: Job) -> bool:
    if job.kind in DATASET_KINDS:
        return has_scope(p, "datasets:read")
    if job.kind in MODEL_KINDS:
        return has_scope(p, "models:read") or has_scope(p, "runs:read")
    return has_scope(p, "runs:read")


async def _load(db: DB, p: Principal, job_id: uuid.UUID) -> tuple[Job, str]:
    job = await db.get(Job, job_id)
    if job is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "job not found")
    role = workspace_role(p, job.workspace_id)
    return job, role


@router.get("/jobs", operation_id="listJobs")
async def list_jobs(
    db: DB,
    principal: CurrentPrincipal,
    workspace_id: uuid.UUID,
    kind: JobKind | None = None,
    status: JobStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> dict[str, Any]:
    workspace_role(principal, workspace_id, for_list=True)
    require_scope(principal, "datasets:read")
    stmt = select(Job).where(Job.workspace_id == workspace_id)
    if kind is not None:
        stmt = stmt.where(Job.kind == kind)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    if cursor:
        c = decode_cursor(cursor)
        ts = datetime.fromisoformat(c["t"])
        stmt = stmt.where((Job.created_at < ts) | ((Job.created_at == ts) & (Job.id < uuid.UUID(c["i"]))))
    rows = list(
        (await db.execute(stmt.order_by(Job.created_at.desc(), Job.id.desc()).limit(limit + 1))).scalars()
    )
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        nxt = encode_cursor({"t": rows[-1].created_at.isoformat(), "i": str(rows[-1].id)})
    return {"items": [job_to_dict(j) for j in rows], "next_cursor": nxt}


@router.get("/jobs/{job_id}", operation_id="getJob")
async def get_job(job_id: uuid.UUID, db: DB, principal: CurrentPrincipal) -> dict[str, Any]:
    job, _ = await _load(db, principal, job_id)
    if not _read_scope_ok(principal, job):
        raise ProblemError(403, ErrorCode.INSUFFICIENT_SCOPE, "token lacks a scope for this job")
    return job_to_dict(job)


@router.post("/jobs/{job_id}/cancel", operation_id="cancelJob", status_code=202)
async def cancel_job(job_id: uuid.UUID, db: DB, principal: CurrentPrincipal) -> dict[str, Any]:
    if principal.auth_method == "pat":
        raise ProblemError(403, ErrorCode.INSUFFICIENT_SCOPE, "personal access tokens cannot cancel jobs")
    job, role = await _load(db, principal, job_id)
    if not role_at_least(role, "member") or (
        job.created_by != principal.user_id and not role_at_least(role, "admin")
    ):
        raise ProblemError(403, ErrorCode.FORBIDDEN, "cannot cancel this job")
    if job.status == JobStatus.CANCELLED:
        return job_to_dict(job)
    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise ProblemError(409, ErrorCode.JOB_NOT_CANCELLABLE, f"job is {job.status.value}")
    # A running job's worker sees the status change on its next heartbeat and aborts.
    job.status = JobStatus.CANCELLED
    job.finished_at = datetime.now(UTC)
    job.lease_owner = None
    job.lease_expires_at = None
    await db.commit()
    await db.refresh(job)
    return job_to_dict(job)
