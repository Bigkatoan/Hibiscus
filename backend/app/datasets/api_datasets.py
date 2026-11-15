"""Datasets, versions, validation, preview, episodes, media, archive, HF import, merge."""

from __future__ import annotations

import json
import re
import tarfile
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Path, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.audit import AuditAction
from app.core.deps import Principal, current_principal, get_db
from app.core.errors import ErrorCode, ProblemError
from app.core.pagination import decode_cursor, encode_cursor
from app.core.storage import BUCKET_DATASETS
from app.datasets import service as svc
from app.datasets.access import at_least, require_cookie, require_workspace
from app.datasets.quota import storage_headroom
from app.datasets.schemas import HF_URI_RE, DatasetCreate, DatasetUpdate, HfImportRequest, MergeRequest
from app.datasets.storage import DatasetStorage, ObjectNotFoundError, get_storage
from app.datasets.storage_layout import dataset_key, derived_key, manifest_key
from app.db.models import (
    Dataset,
    DatasetSource,
    DatasetVersion,
    DatasetVersionStatus,
    JobKind,
    User,
    WorkspaceRole,
)

router = APIRouter(tags=["datasets"])

Db = Annotated[AsyncSession, Depends(get_db)]
Me = Annotated[Principal, Depends(current_principal)]
Storage = Annotated[DatasetStorage, Depends(get_storage)]
Limit = Annotated[int, Query(ge=1, le=200)]
CACHE_IMMUTABLE = "private, max-age=31536000, immutable"
PREVIEW_STATUSES = (DatasetVersionStatus.READY, DatasetVersionStatus.INVALID)


def _json(body: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status)


async def parse_body(request: Request, model: type[Any]) -> Any:
    """Parse a JSON body with a pydantic model, mapping failures to 422 ``validation_failed``."""
    raw = await request.body()
    if len(raw) > 1024 * 1024:
        raise ProblemError(413, ErrorCode.PAYLOAD_TOO_LARGE)
    try:
        return model.model_validate_json(raw or b"null")
    except ValidationError as exc:
        errors = [
            {"loc": ["body", *e["loc"]], "code": str(e["type"]), "message": str(e["msg"])}
            for e in exc.errors()
        ]
        raise ProblemError(
            422, ErrorCode.VALIDATION_FAILED, "request body is invalid", errors=errors
        ) from exc


# --------------------------------------------------------------------------------------------------
# datasets
# --------------------------------------------------------------------------------------------------
@router.get("/datasets", operation_id="listDatasets")
async def list_datasets(
    db: Db,
    me: Me,
    workspace_id: uuid.UUID,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Limit = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> JSONResponse:
    require_workspace(me, workspace_id, WorkspaceRole.VIEWER, "datasets:read", item=False)
    stmt = select(Dataset).where(Dataset.workspace_id == workspace_id, Dataset.deleted_at.is_(None))
    if q:
        stmt = stmt.where(
            Dataset.name.ilike("%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
        )
    if cursor:
        c = decode_cursor(cursor)
        ts, cid = datetime.fromisoformat(str(c["u"])), uuid.UUID(str(c["i"]))
        stmt = stmt.where(or_(Dataset.updated_at < ts, (Dataset.updated_at == ts) & (Dataset.id < cid)))
    rows = (
        (await db.execute(stmt.order_by(Dataset.updated_at.desc(), Dataset.id.desc()).limit(limit + 1)))
        .scalars()
        .all()
    )
    page, more = rows[:limit], len(rows) > limit
    ids = [d.id for d in page]
    counts: dict[uuid.UUID, int] = {}
    if ids:
        for did, n in (
            await db.execute(
                select(DatasetVersion.dataset_id, func.count())
                .where(DatasetVersion.dataset_id.in_(ids), DatasetVersion.deleted_at.is_(None))
                .group_by(DatasetVersion.dataset_id)
            )
        ).all():
            counts[did] = int(n)
    latest_ids = [d.latest_version_id for d in page if d.latest_version_id]
    latest = (
        {
            v.id: v
            for v in (
                await db.execute(
                    select(DatasetVersion).where(
                        DatasetVersion.id.in_(latest_ids), DatasetVersion.deleted_at.is_(None)
                    )
                )
            ).scalars()
        }
        if latest_ids
        else {}
    )
    creator_ids = [d.created_by for d in page if d.created_by]
    users = (
        {u.id: u for u in (await db.execute(select(User).where(User.id.in_(creator_ids)))).scalars()}
        if creator_ids
        else {}
    )
    items = [
        svc.dataset_json(
            d,
            counts.get(d.id, 0),
            latest.get(d.latest_version_id) if d.latest_version_id else None,
            users.get(d.created_by) if d.created_by else None,
        )
        for d in page
    ]
    nxt = (
        encode_cursor({"u": page[-1].updated_at.isoformat(), "i": str(page[-1].id)})
        if more and page
        else None
    )
    return _json({"items": items, "next_cursor": nxt})


@router.post("/datasets", operation_id="createDataset", status_code=201)
async def create_dataset(request: Request, db: Db, me: Me) -> JSONResponse:
    body: DatasetCreate = await parse_body(request, DatasetCreate)
    require_workspace(me, body.workspace_id, WorkspaceRole.MEMBER, "datasets:write", item=False)
    ds = await svc.create_dataset(db, body.workspace_id, body.name, body.description, me.user_id)
    await audit.record(
        AuditAction.DATASET_CREATED,
        db=db,
        actor=me,
        workspace_id=ds.workspace_id,
        target_type="dataset",
        target_id=str(ds.id),
        details={"name": ds.name},
    )
    await db.commit()
    return _json(await svc.dataset_full(db, ds), 201)


@router.get("/datasets/{dataset_id}", operation_id="getDataset")
async def get_dataset(dataset_id: uuid.UUID, db: Db, me: Me) -> JSONResponse:
    ds, _ = await svc.load_dataset(db, me, dataset_id, WorkspaceRole.VIEWER)
    return _json(await svc.dataset_full(db, ds))


@router.patch("/datasets/{dataset_id}", operation_id="updateDataset")
async def update_dataset(dataset_id: uuid.UUID, request: Request, db: Db, me: Me) -> JSONResponse:
    ds, _ = await svc.load_dataset(db, me, dataset_id, WorkspaceRole.MEMBER, write=True, for_update=True)
    body: DatasetUpdate = await parse_body(request, DatasetUpdate)
    if body.name is not None and body.name != ds.name:
        slug = svc.slugify(body.name)
        if await svc.name_taken(db, ds.workspace_id, slug, exclude=ds.id):
            raise ProblemError(409, ErrorCode.DATASET_NAME_TAKEN)
        ds.name, ds.slug = body.name, slug
    if body.description is not None:
        ds.description = body.description
    ds.updated_at = func.now()
    await db.commit()
    return _json(await svc.dataset_full(db, ds))


@router.delete("/datasets/{dataset_id}", operation_id="deleteDataset", status_code=204)
async def delete_dataset(dataset_id: uuid.UUID, db: Db, me: Me) -> Response:
    require_cookie(me)
    ds, role = await svc.load_dataset(db, me, dataset_id, WorkspaceRole.MEMBER, write=True, for_update=True)
    if not at_least(role, WorkspaceRole.ADMIN) and ds.created_by != me.user_id:
        raise ProblemError(
            403, ErrorCode.FORBIDDEN, "only the creator or a workspace admin may delete a dataset"
        )
    vids = select(DatasetVersion.id).where(DatasetVersion.dataset_id == ds.id)
    if (await db.execute(select(svc.version_in_use_clause(vids)))).scalar():
        raise ProblemError(409, ErrorCode.DATASET_IN_USE, "a run that is not finished uses this dataset")
    now = func.now()
    await db.execute(
        update(DatasetVersion)
        .where(DatasetVersion.dataset_id == ds.id, DatasetVersion.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    ds.deleted_at = now
    await audit.record(
        AuditAction.DATASET_DELETED,
        db=db,
        actor=me,
        workspace_id=ds.workspace_id,
        target_type="dataset",
        target_id=str(ds.id),
    )
    await db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------------------------------
# versions
# --------------------------------------------------------------------------------------------------
@router.get("/datasets/{dataset_id}/versions", operation_id="listDatasetVersions")
async def list_versions(
    dataset_id: uuid.UUID,
    db: Db,
    me: Me,
    limit: Limit = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> JSONResponse:
    ds, _ = await svc.load_dataset(db, me, dataset_id, WorkspaceRole.VIEWER)
    stmt = select(DatasetVersion).where(
        DatasetVersion.dataset_id == ds.id, DatasetVersion.deleted_at.is_(None)
    )
    if cursor:
        stmt = stmt.where(DatasetVersion.version < int(decode_cursor(cursor)["v"]))
    rows = (await db.execute(stmt.order_by(DatasetVersion.version.desc()).limit(limit + 1))).scalars().all()
    page = rows[:limit]
    nxt = encode_cursor({"v": page[-1].version}) if len(rows) > limit and page else None
    return _json({"items": [svc.version_summary(v) for v in page], "next_cursor": nxt})


@router.get("/dataset-versions/{version_id}", operation_id="getDatasetVersion")
async def get_version(version_id: uuid.UUID, db: Db, me: Me) -> JSONResponse:
    v, _, _ = await svc.load_version(db, me, version_id, WorkspaceRole.VIEWER)
    return _json(svc.version_detail(v, await svc.latest_job_error(db, v.id)))


@router.delete("/dataset-versions/{version_id}", operation_id="deleteDatasetVersion", status_code=204)
async def delete_version(version_id: uuid.UUID, db: Db, me: Me) -> Response:
    require_cookie(me)
    v, ds, role = await svc.load_version(db, me, version_id, WorkspaceRole.MEMBER, write=True)
    if not at_least(role, WorkspaceRole.ADMIN) and v.created_by != me.user_id and ds.created_by != me.user_id:
        raise ProblemError(
            403, ErrorCode.FORBIDDEN, "only the creator or a workspace admin may delete a version"
        )
    if (
        await db.execute(
            select(svc.version_in_use_clause(select(DatasetVersion.id).where(DatasetVersion.id == v.id)))
        )
    ).scalar():
        raise ProblemError(409, ErrorCode.DATASET_IN_USE, "a run that is not finished uses this version")
    await db.execute(select(Dataset.id).where(Dataset.id == ds.id).with_for_update())
    v.deleted_at = func.now()
    await db.flush()
    ds.latest_version_id = await svc.latest_live_version_id(db, ds.id)
    ds.updated_at = func.now()
    await audit.record(
        AuditAction.DATASET_VERSION_DELETED,
        db=db,
        actor=me,
        workspace_id=ds.workspace_id,
        target_type="dataset_version",
        target_id=str(v.id),
        details={"version": v.version},
    )
    await db.commit()
    return Response(status_code=204)


@router.get("/dataset-versions/{version_id}/validation", operation_id="getValidationReport")
async def get_validation(version_id: uuid.UUID, db: Db, me: Me) -> JSONResponse:
    v, _, _ = await svc.load_version(db, me, version_id, WorkspaceRole.VIEWER)
    if not v.validate_report:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "validation has not started")
    return _json(v.validate_report)


@router.post(
    "/dataset-versions/{version_id}/validation", operation_id="revalidateDatasetVersion", status_code=202
)
async def revalidate(version_id: uuid.UUID, db: Db, me: Me) -> JSONResponse:
    v, ds, _ = await svc.load_version(db, me, version_id, WorkspaceRole.MEMBER, write=True)
    allowed = (DatasetVersionStatus.INVALID, DatasetVersionStatus.FAILED, DatasetVersionStatus.READY)
    if v.status not in allowed or await svc.active_job_exists(db, v.id):
        raise ProblemError(
            409, ErrorCode.CONFLICT, f"version is {v.status.value}; validation already queued or running"
        )
    payload: dict[str, Any] = {}
    kind = JobKind.VALIDATE_DATASET
    if not v.storage_prefix and v.source == DatasetSource.HF_IMPORT:
        kind, payload = JobKind.IMPORT_HF_DATASET, {"hf_uri": v.source_ref}
    elif not v.storage_prefix and v.source == DatasetSource.MERGE:
        kind, payload = JobKind.MERGE_DATASETS, {"source_version_ids": [str(x) for x in v.merged_from or []]}
    job = svc.new_job(ds.workspace_id, kind, v.id, me.user_id, payload)
    db.add(job)
    v.status = DatasetVersionStatus.PENDING
    await db.commit()
    await db.refresh(job)
    return _json(svc.job_json(job), 202)


# --------------------------------------------------------------------------------------------------
# preview, episodes, media, archive
# --------------------------------------------------------------------------------------------------
@router.get("/dataset-versions/{version_id}/preview", operation_id="getDatasetPreview")
async def get_preview(version_id: uuid.UUID, db: Db, me: Me) -> JSONResponse:
    v, _, _ = await svc.load_version(db, me, version_id, WorkspaceRole.VIEWER)
    if v.status not in PREVIEW_STATUSES or not v.preview:
        raise ProblemError(
            409, ErrorCode.DATASET_VERSION_NOT_READY, f"preview not available (status {v.status.value})"
        )
    return _json(v.preview)


def downsample(detail: dict[str, Any], max_points: int) -> dict[str, Any]:
    ts = detail.get("timestamps") or []
    n = len(ts)
    if n <= max_points:
        return detail
    idx = sorted({round(i * (n - 1) / (max_points - 1)) for i in range(max_points)})
    out = dict(detail)
    out["timestamps"] = [ts[i] for i in idx]
    out["series"] = [{**s, "values": [s["values"][i] for i in idx]} for s in detail.get("series", [])]
    return out


@router.get("/dataset-versions/{version_id}/episodes/{episode_index}", operation_id="getEpisode")
async def get_episode(
    version_id: uuid.UUID,
    episode_index: Annotated[int, Path(ge=0)],
    db: Db,
    me: Me,
    s3: Storage,
    max_points: Annotated[int, Query(ge=50, le=5000)] = 1000,
) -> JSONResponse:
    v, ds, _ = await svc.load_version(db, me, version_id, WorkspaceRole.VIEWER)
    if (
        episode_index < 0
        or v.status not in PREVIEW_STATUSES
        or v.total_episodes is None
        or episode_index >= v.total_episodes
    ):
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    key = derived_key(ds.workspace_id, ds.id, v.id, f"episodes/episode_{episode_index:06d}.json")
    try:
        detail = json.loads(await s3.get_bytes(BUCKET_DATASETS, key))
    except ObjectNotFoundError as exc:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "episode detail not generated") from exc
    return _json(downsample(detail, max_points))


_MEDIA_RE = re.compile(r"^(videos/[^\x00]+\.mp4|meta/[^\x00]+|previews/[^\x00]+)$")
_CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".json": "application/json",
}
_RANGE_RE = re.compile(r"^bytes=(\d+)-(\d*)$")


def media_object_key(ds: Dataset, v: DatasetVersion, rel: str) -> str:
    parts = rel.split("/")
    if not _MEDIA_RE.match(rel) or any(p in ("", ".", "..") for p in parts) or "\\" in rel or len(rel) > 512:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    if parts[0] == "previews":
        return derived_key(ds.workspace_id, ds.id, v.id, rel)
    return dataset_key(ds.workspace_id, ds.id, v.id, rel)


class RangeNotSatisfiableError(Exception):
    def __init__(self, size: int) -> None:
        super().__init__(size)
        self.size = size


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    if header is None:
        return None
    m = _RANGE_RE.match(header.strip())
    if m is None:
        return None  # unsupported/multi range: serve the whole file (RFC 9110 allows ignoring)
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else size - 1
    if start >= size or end < start:
        raise RangeNotSatisfiableError(size)
    return start, min(end, size - 1)


async def _stream(
    s3: DatasetStorage, bucket: str, key: str, rng: tuple[int, int] | None
) -> AsyncIterator[bytes]:
    async for chunk in s3.iter_object(bucket, key, rng):
        yield chunk


@router.get("/dataset-versions/{version_id}/media/{path:path}", operation_id="getDatasetMedia")
async def get_media(
    version_id: uuid.UUID,
    path: str,
    request: Request,
    db: Db,
    me: Me,
    s3: Storage,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> Response:
    v, ds, _ = await svc.load_version(db, me, version_id, WorkspaceRole.VIEWER)
    if not v.storage_prefix:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    key = media_object_key(ds, v, path)
    try:
        meta = await s3.head(BUCKET_DATASETS, key)
    except ObjectNotFoundError as exc:
        raise ProblemError(404, ErrorCode.NOT_FOUND) from exc
    try:
        rng = parse_range(range_header, meta.size)
    except RangeNotSatisfiableError as exc:
        raise ProblemError(
            416, ErrorCode.RANGE_NOT_SATISFIABLE, headers={"Content-Range": f"bytes */{exc.size}"}
        ) from exc
    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    ctype = _CONTENT_TYPES.get(ext, "application/octet-stream")
    headers = {"ETag": f'"{meta.etag}"', "Accept-Ranges": "bytes", "Cache-Control": CACHE_IMMUTABLE}
    if rng is None:
        headers["Content-Length"] = str(meta.size)
        return StreamingResponse(
            _stream(s3, BUCKET_DATASETS, key, None), 200, headers=headers, media_type=ctype
        )
    start, end = rng
    headers["Content-Range"] = f"bytes {start}-{end}/{meta.size}"
    headers["Content-Length"] = str(end - start + 1)
    return StreamingResponse(_stream(s3, BUCKET_DATASETS, key, rng), 206, headers=headers, media_type=ctype)


async def _tar_stream(
    s3: DatasetStorage, ds: Dataset, v: DatasetVersion, files: list[dict[str, Any]], top: str
) -> AsyncIterator[bytes]:
    mtime = (v.ready_at or v.created_at).timestamp()
    for f in files:
        info = tarfile.TarInfo(f"{top}/{f['path']}")
        info.size = int(f["size"])
        info.mode = 0o644
        info.mtime = int(mtime)
        yield info.tobuf(format=tarfile.PAX_FORMAT)
        sent = 0
        async for chunk in s3.iter_object(
            BUCKET_DATASETS, dataset_key(ds.workspace_id, ds.id, v.id, str(f["path"]))
        ):
            sent += len(chunk)
            yield chunk
        if sent != info.size:
            raise RuntimeError(f"size changed for {f['path']}")
        pad = (-info.size) % tarfile.BLOCKSIZE
        if pad:
            yield b"\0" * pad
    yield b"\0" * (tarfile.BLOCKSIZE * 2)


@router.get("/dataset-versions/{version_id}/archive", operation_id="downloadDatasetVersion")
async def download_archive(version_id: uuid.UUID, db: Db, me: Me, s3: Storage) -> Response:
    v, ds, _ = await svc.load_version(db, me, version_id, WorkspaceRole.VIEWER)
    if v.status != DatasetVersionStatus.READY:
        raise ProblemError(409, ErrorCode.DATASET_VERSION_NOT_READY)
    manifest = json.loads(await s3.get_bytes(BUCKET_DATASETS, manifest_key(ds.workspace_id, ds.id, v.id)))
    files = list(manifest["files"])
    top = f"{ds.slug}-v{v.version}"
    headers = {"Content-Disposition": f'attachment; filename="{top}.tar"'}
    return StreamingResponse(
        _tar_stream(s3, ds, v, files, top), 200, headers=headers, media_type="application/x-tar"
    )


# --------------------------------------------------------------------------------------------------
# HF import & merge
# --------------------------------------------------------------------------------------------------
async def _target_dataset(
    db: AsyncSession,
    me: Principal,
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID | None,
    new_name: str | None,
) -> tuple[Dataset, bool]:
    require_workspace(me, workspace_id, WorkspaceRole.MEMBER, "datasets:write", item=False)
    if dataset_id is not None:
        ds, _ = await svc.load_dataset(db, me, dataset_id, WorkspaceRole.MEMBER, write=True)
        if ds.workspace_id != workspace_id:
            raise ProblemError(404, ErrorCode.NOT_FOUND)
        return ds, False
    assert new_name is not None  # noqa: S101 - guaranteed by the schema validator
    return await svc.create_dataset(db, workspace_id, new_name, "", me.user_id), True


async def _accepted(db: AsyncSession, ds: Dataset, v: DatasetVersion, job: Any) -> JSONResponse:
    await db.refresh(v)
    await db.refresh(job)
    body = {
        "dataset": await svc.dataset_full(db, ds),
        "version": svc.version_summary(v),
        "job": svc.job_json(job),
    }
    return _json(body, 202)


@router.post("/datasets/import-hf", operation_id="importHfDataset", status_code=202)
async def import_hf(request: Request, db: Db, me: Me) -> JSONResponse:
    body: HfImportRequest = await parse_body(request, HfImportRequest)
    if not HF_URI_RE.match(body.hf_uri) or ".." in body.hf_uri:
        raise ProblemError(422, ErrorCode.HF_URI_INVALID, "expected hf://<org>/<repo>[@<revision>]")
    require_workspace(me, body.workspace_id, WorkspaceRole.MEMBER, "datasets:write", item=False)
    # SEC-input-3: the repo size is unknown here; refuse when the quota is already used up and hand
    # the worker the bytes left as a hard download/store cap.
    max_bytes = await storage_headroom(db, body.workspace_id, me.user_id)
    ds, created = await _target_dataset(db, me, body.workspace_id, body.dataset_id, body.new_dataset_name)
    v = await svc.new_version(db, ds, DatasetSource.HF_IMPORT, body.hf_uri, me.user_id)
    job = svc.new_job(
        ds.workspace_id,
        JobKind.IMPORT_HF_DATASET,
        v.id,
        me.user_id,
        {"hf_uri": body.hf_uri, "max_bytes": max_bytes},
    )
    db.add(job)
    if created:
        await audit.record(
            AuditAction.DATASET_CREATED,
            db=db,
            actor=me,
            workspace_id=ds.workspace_id,
            target_type="dataset",
            target_id=str(ds.id),
        )
    await audit.record(
        AuditAction.DATASET_VERSION_CREATED,
        db=db,
        actor=me,
        workspace_id=ds.workspace_id,
        target_type="dataset_version",
        target_id=str(v.id),
        details={"source": "hf_import"},
    )
    await db.commit()
    return await _accepted(db, ds, v, job)


@router.post("/datasets/merge", operation_id="mergeDatasets", status_code=202)
async def merge(request: Request, db: Db, me: Me) -> JSONResponse:
    body: MergeRequest = await parse_body(request, MergeRequest)
    require_workspace(me, body.workspace_id, WorkspaceRole.MEMBER, "datasets:write", item=False)
    rows = (
        await db.execute(
            select(DatasetVersion, Dataset)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(
                DatasetVersion.id.in_(body.source_version_ids),
                DatasetVersion.deleted_at.is_(None),
                Dataset.deleted_at.is_(None),
                Dataset.workspace_id == body.workspace_id,
            )
        )
    ).all()
    found = {r[0].id: r[0] for r in rows}
    missing = [str(x) for x in body.source_version_ids if x not in found]
    if missing:
        raise ProblemError(404, ErrorCode.NOT_FOUND, "source version not found", params={"missing": missing})
    srcs = [found[x] for x in body.source_version_ids]
    not_ready = [str(s.id) for s in srcs if s.status != DatasetVersionStatus.READY]
    if not_ready:
        raise ProblemError(
            409,
            ErrorCode.DATASET_VERSION_NOT_READY,
            "all sources must be ready",
            params={"versions": not_ready},
        )
    first = srcs[0]
    for s in srcs[1:]:
        if s.features != first.features or s.fps != first.fps or s.robot_type != first.robot_type:
            raise ProblemError(
                422,
                ErrorCode.DATASET_SCHEMA_MISMATCH,
                "sources differ in features / fps / robot_type",
                params={"version": str(s.id), "reference": str(first.id)},
            )
    # SEC-input-3: a merge stores (about) the sum of its sources; refuse it up front when that does
    # not fit, and cap the worker at the quota left.
    expected = sum(int(x.size_bytes or 0) for x in srcs)
    max_bytes = await storage_headroom(db, body.workspace_id, me.user_id, adding=expected)
    ds, created = await _target_dataset(db, me, body.workspace_id, body.dataset_id, body.new_dataset_name)
    v = await svc.new_version(
        db, ds, DatasetSource.MERGE, "merge", me.user_id, merged_from=list(body.source_version_ids)
    )
    job = svc.new_job(
        ds.workspace_id,
        JobKind.MERGE_DATASETS,
        v.id,
        me.user_id,
        {
            "source_version_ids": [str(x) for x in body.source_version_ids],
            "max_bytes": max_bytes,
        },
    )
    db.add(job)
    if created:
        await audit.record(
            AuditAction.DATASET_CREATED,
            db=db,
            actor=me,
            workspace_id=ds.workspace_id,
            target_type="dataset",
            target_id=str(ds.id),
        )
    await audit.record(
        AuditAction.DATASET_VERSION_CREATED,
        db=db,
        actor=me,
        workspace_id=ds.workspace_id,
        target_type="dataset_version",
        target_id=str(v.id),
        details={"source": "merge"},
    )
    await db.commit()
    return await _accepted(db, ds, v, job)
