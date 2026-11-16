"""Shared dataset/version logic and JSON serializers (shapes = OpenAPI components)."""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.core.errors import ErrorCode, ProblemError
from app.datasets.access import require_workspace
from app.db.models import (
    RUN_TERMINAL_STATUSES,
    Dataset,
    DatasetSource,
    DatasetVersion,
    DatasetVersionStatus,
    Job,
    JobKind,
    JobResource,
    Run,
    User,
    WorkspaceRole,
)

DATASET_JOB_KINDS = (JobKind.VALIDATE_DATASET, JobKind.IMPORT_HF_DATASET, JobKind.MERGE_DATASETS)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def slugify(name: str) -> str:
    name = name.replace("đ", "d").replace("Đ", "D")  # Vietnamese d-stroke has no NFKD decomposition
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9_.-]+", "-", s).strip("-._")
    s = re.sub(r"-{2,}", "-", s)[:100].rstrip("-._")
    return s or "dataset"


# --------------------------------------------------------------------------------------------------
# lookups with access control
# --------------------------------------------------------------------------------------------------
async def load_dataset(
    db: AsyncSession,
    p: Principal,
    dataset_id: uuid.UUID,
    min_role: WorkspaceRole,
    *,
    write: bool = False,
    for_update: bool = False,
) -> tuple[Dataset, WorkspaceRole]:
    q = select(Dataset).where(Dataset.id == dataset_id, Dataset.deleted_at.is_(None))
    if for_update:
        q = q.with_for_update()
    ds = (await db.execute(q)).scalar_one_or_none()
    if ds is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    role = require_workspace(
        p, ds.workspace_id, min_role, "datasets:write" if write else "datasets:read", item=True
    )
    return ds, role


async def load_version(
    db: AsyncSession, p: Principal, version_id: uuid.UUID, min_role: WorkspaceRole, *, write: bool = False
) -> tuple[DatasetVersion, Dataset, WorkspaceRole]:
    row = (
        await db.execute(
            select(DatasetVersion, Dataset)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(
                DatasetVersion.id == version_id,
                DatasetVersion.deleted_at.is_(None),
                Dataset.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    v, ds = row._tuple()
    role = require_workspace(
        p, ds.workspace_id, min_role, "datasets:write" if write else "datasets:read", item=True
    )
    return v, ds, role


async def name_taken(
    db: AsyncSession, workspace_id: uuid.UUID, slug: str, exclude: uuid.UUID | None = None
) -> bool:
    q = select(Dataset.id).where(
        Dataset.workspace_id == workspace_id, Dataset.slug == slug, Dataset.deleted_at.is_(None)
    )
    if exclude is not None:
        q = q.where(Dataset.id != exclude)
    return (await db.execute(q.limit(1))).first() is not None


async def create_dataset(
    db: AsyncSession, workspace_id: uuid.UUID, name: str, description: str, user_id: uuid.UUID
) -> Dataset:
    slug = slugify(name)
    if await name_taken(db, workspace_id, slug):
        raise ProblemError(409, ErrorCode.DATASET_NAME_TAKEN, f"a dataset named like '{name}' already exists")
    ds = Dataset(workspace_id=workspace_id, name=name, slug=slug, description=description, created_by=user_id)
    db.add(ds)
    await db.flush()
    return ds


async def new_version(
    db: AsyncSession,
    ds: Dataset,
    source: DatasetSource,
    source_ref: str | None,
    user_id: uuid.UUID,
    merged_from: list[uuid.UUID] | None = None,
) -> DatasetVersion:
    """Allocate the next version number (dataset row locked) and make it the latest version."""
    await db.execute(select(Dataset.id).where(Dataset.id == ds.id).with_for_update())
    n = (
        await db.execute(
            select(func.coalesce(func.max(DatasetVersion.version), 0)).where(
                DatasetVersion.dataset_id == ds.id
            )
        )
    ).scalar_one()
    v = DatasetVersion(
        dataset_id=ds.id,
        version=int(n) + 1,
        status=DatasetVersionStatus.PENDING,
        source=source,
        source_ref=source_ref,
        merged_from=merged_from,
        created_by=user_id,
    )
    db.add(v)
    await db.flush()
    ds.latest_version_id = v.id
    ds.updated_at = func.now()
    return v


def new_job(
    workspace_id: uuid.UUID, kind: JobKind, version_id: uuid.UUID, user_id: uuid.UUID, payload: dict[str, Any]
) -> Job:
    return Job(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        kind=kind,
        resource=JobResource.CPU,
        payload={"dataset_version_id": str(version_id), **payload},
        dataset_version_id=version_id,
        created_by=user_id,
        max_attempts=2,
    )


def version_in_use_clause(version_ids: Select[Any]) -> Any:
    return exists().where(
        Run.dataset_version_id.in_(version_ids), Run.status.not_in(list(RUN_TERMINAL_STATUSES))
    )


async def latest_live_version_id(db: AsyncSession, dataset_id: uuid.UUID) -> uuid.UUID | None:
    return (
        await db.execute(
            select(DatasetVersion.id)
            .where(DatasetVersion.dataset_id == dataset_id, DatasetVersion.deleted_at.is_(None))
            .order_by(DatasetVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def latest_job_error(db: AsyncSession, version_id: uuid.UUID) -> str | None:
    return (
        await db.execute(
            select(Job.error_code)
            .where(Job.dataset_version_id == version_id, Job.kind.in_(DATASET_JOB_KINDS))
            .order_by(Job.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def active_job_exists(db: AsyncSession, version_id: uuid.UUID) -> bool:
    q = select(Job.id).where(
        and_(Job.dataset_version_id == version_id, Job.status.in_(["queued", "running"]))
    )
    return (await db.execute(q.limit(1))).first() is not None


# --------------------------------------------------------------------------------------------------
# serializers
# --------------------------------------------------------------------------------------------------
def version_summary(v: DatasetVersion) -> dict[str, Any]:
    return {
        "id": str(v.id),
        "dataset_id": str(v.dataset_id),
        "version": v.version,
        "status": v.status.value,
        "source": v.source.value,
        "total_episodes": v.total_episodes,
        "total_frames": v.total_frames,
        "fps": v.fps,
        "size_bytes": v.size_bytes,
        "created_at": iso(v.created_at),
    }


def _names(spec: Any) -> list[str]:
    if isinstance(spec, dict):
        names = spec.get("names")
        if isinstance(names, list) and all(isinstance(n, str) for n in names):
            return list(names)
        if isinstance(names, dict):
            first = next(iter(names.values()), None)
            if isinstance(first, list):
                return [str(n) for n in first]
    return []


def _dim(spec: Any) -> int | None:
    if isinstance(spec, dict):
        shape = spec.get("shape")
        if isinstance(shape, list) and len(shape) == 1 and isinstance(shape[0], int):
            return shape[0]
    return None


def version_detail(v: DatasetVersion, error_code: str | None) -> dict[str, Any]:
    feats = v.features or {}
    report = v.validate_report
    summary = report.get("summary") if isinstance(report, dict) else None
    tasks: list[str] = []
    if v.preview:
        seen: dict[str, None] = {}
        for ep in v.preview.get("episodes", []):
            for t in ep.get("tasks", []):
                seen.setdefault(str(t), None)
        tasks = list(seen)
    return {
        **version_summary(v),
        "content_hash": v.content_hash,
        "source_ref": v.source_ref,
        "merged_from": [str(x) for x in v.merged_from] if v.merged_from else None,
        "codebase_version": v.codebase_version,
        "converted_from": v.converted_from,
        "robot_type": v.robot_type,
        "camera_keys": list(v.camera_keys or []),
        "features": feats or None,
        "state_dim": _dim(feats.get("observation.state")),
        "action_dim": _dim(feats.get("action")),
        "joint_names": _names(feats.get("observation.state")) or _names(feats.get("action")),
        "tasks": tasks,
        "validation_summary": summary,
        "error_code": error_code
        if v.status in (DatasetVersionStatus.FAILED, DatasetVersionStatus.INVALID)
        else None,
        "ready_at": iso(v.ready_at),
    }


def user_ref(u: User | None) -> dict[str, Any] | None:
    return None if u is None else {"id": str(u.id), "display_name": u.display_name}


def dataset_json(
    ds: Dataset, version_count: int, latest: DatasetVersion | None, creator: User | None
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(ds.id),
        "workspace_id": str(ds.workspace_id),
        "name": ds.name,
        "slug": ds.slug,
        "description": ds.description,
        "version_count": version_count,
        "latest_version": version_summary(latest) if latest is not None else None,
        "created_at": iso(ds.created_at),
        "updated_at": iso(ds.updated_at),
    }
    ref = user_ref(creator)
    if ref is not None:
        out["created_by"] = ref
    return out


async def dataset_full(db: AsyncSession, ds: Dataset) -> dict[str, Any]:
    await db.refresh(ds)
    count = (
        await db.execute(
            select(func.count()).where(
                DatasetVersion.dataset_id == ds.id, DatasetVersion.deleted_at.is_(None)
            )
        )
    ).scalar_one()
    latest = None
    if ds.latest_version_id is not None:
        latest = await db.get(DatasetVersion, ds.latest_version_id)
        if latest is not None and latest.deleted_at is not None:
            latest = None
    creator = await db.get(User, ds.created_by) if ds.created_by else None
    return dataset_json(ds, int(count), latest, creator)


def job_json(j: Job) -> dict[str, Any]:
    result = j.result if isinstance(j.result, dict) else None
    return {
        "id": str(j.id),
        "workspace_id": str(j.workspace_id),
        "kind": j.kind.value,
        "status": j.status.value,
        "progress": float(j.progress or 0.0),
        "stage": (result or {}).get("stage"),
        "error_code": j.error_code,
        "error_message": j.error_message,
        "result": result,
        "run_id": str(j.run_id) if j.run_id else None,
        "dataset_version_id": str(j.dataset_version_id) if j.dataset_version_id else None,
        "model_id": str(j.model_id) if j.model_id else None,
        "created_at": iso(j.created_at),
        "started_at": iso(j.started_at),
        "finished_at": iso(j.finished_at),
    }
