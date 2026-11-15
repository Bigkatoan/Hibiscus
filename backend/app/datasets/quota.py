"""Workspace storage quota accounting shared by uploads, HF import and merge (SEC-input-3)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, ProblemError
from app.db.models import (
    Dataset,
    DatasetVersion,
    Job,
    JobKind,
    JobStatus,
    Quota,
    UploadSession,
    UploadStatus,
)

DEFAULT_MAX_UPLOAD = 50 * 1024**3
DEFAULT_STORAGE = 200 * 1024**3


async def workspace_quota(db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID) -> tuple[int, int]:
    rows = (
        (
            await db.execute(
                select(Quota).where(
                    Quota.workspace_id == workspace_id, (Quota.user_id == user_id) | (Quota.user_id.is_(None))
                )
            )
        )
        .scalars()
        .all()
    )
    user_row = next((q for q in rows if q.user_id == user_id), None)
    ws_row = next((q for q in rows if q.user_id is None), None)
    row = user_row or ws_row
    max_upload = row.max_upload_bytes if row else DEFAULT_MAX_UPLOAD
    if ws_row is not None:
        storage = ws_row.storage_bytes
    else:
        storage = row.storage_bytes if row is not None else DEFAULT_STORAGE
    return int(max_upload), int(storage)


async def storage_used(db: AsyncSession, workspace_id: uuid.UUID) -> int:
    stored = (
        await db.execute(
            select(func.coalesce(func.sum(DatasetVersion.size_bytes), 0))
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(Dataset.workspace_id == workspace_id, DatasetVersion.deleted_at.is_(None))
        )
    ).scalar_one()
    pending = (
        await db.execute(
            select(func.coalesce(func.sum(UploadSession.total_size), 0)).where(
                UploadSession.workspace_id == workspace_id,
                UploadSession.status == UploadStatus.ACTIVE,
                UploadSession.expires_at > func.now(),
            )
        )
    ).scalar_one()
    return int(stored or 0) + int(pending or 0) + await reserved_bytes(db, workspace_id)


#: Jobs whose ``payload.max_bytes`` is a storage reservation until their version has a size.
RESERVING_KINDS = (JobKind.IMPORT_HF_DATASET, JobKind.MERGE_DATASETS)


async def reserved_bytes(db: AsyncSession, workspace_id: uuid.UUID) -> int:
    """Bytes reserved by queued/running HF imports and merges (phase-5 re-verify, SEC-input-3).

    Each such job may store up to its ``max_bytes`` cap. The cap is reserved at enqueue time, so
    concurrent imports split the remaining quota instead of each getting all of it. The reservation
    ends when the job leaves queued/running or its version records a size (then counted above).
    """
    val = (
        await db.execute(
            select(func.coalesce(func.sum(Job.payload["max_bytes"].as_integer()), 0))
            .join(DatasetVersion, DatasetVersion.id == Job.dataset_version_id)
            .where(
                Job.workspace_id == workspace_id,
                Job.kind.in_(RESERVING_KINDS),
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                DatasetVersion.deleted_at.is_(None),
                DatasetVersion.size_bytes.is_(None),
            )
        )
    ).scalar_one()
    return int(val or 0)


async def lock_workspace_storage(db: AsyncSession, workspace_id: uuid.UUID) -> None:
    """Serialise quota check + reservation per workspace until the transaction ends."""
    await db.execute(text("SELECT pg_advisory_xact_lock(7004, hashtext(:w))"), {"w": str(workspace_id)})


def storage_quota_problem(storage: int) -> ProblemError:
    return ProblemError(
        403,
        ErrorCode.QUOTA_EXCEEDED,
        "workspace storage quota exceeded",
        params={"limit_gb": round(storage / 1024**3, 1), "kind": "storage_bytes"},
    )


async def storage_headroom(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID, *, adding: int = 0
) -> int:
    """Bytes still free in the workspace storage quota (SEC-input-3).

    Raises 403 ``quota_exceeded`` when nothing is free, or when ``adding`` known bytes do not fit.
    Takes the per-workspace storage lock: the caller reserves what it gets (a job's ``max_bytes``)
    in the same transaction, so concurrent requests cannot both be handed the same bytes.
    """
    await lock_workspace_storage(db, workspace_id)
    _, storage = await workspace_quota(db, workspace_id, user_id)
    remaining = storage - await storage_used(db, workspace_id)
    if remaining <= 0 or remaining < adding:
        raise storage_quota_problem(storage)
    return remaining
