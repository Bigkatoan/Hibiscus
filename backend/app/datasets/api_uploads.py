"""Chunked, resumable uploads through the API (ADR-0010): init -> PUT parts -> complete | abort.

Each part body is streamed (never fully buffered in memory: ``SpooledTemporaryFile`` keeps at most
1 MiB in RAM, the rest on local disk) while its sha256 and length are computed; only a verified part
is sent to S3 ``UploadPart`` - so a corrupted re-upload can never replace a good part.
"""

from __future__ import annotations

import hashlib
import math
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Path, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.audit import AuditAction
from app.core.deps import Principal, current_principal, get_db
from app.core.errors import ErrorCode, ProblemError
from app.core.pagination import decode_cursor, encode_cursor
from app.core.storage import BUCKET_UPLOADS
from app.datasets import service as svc
from app.datasets.access import at_least, require_workspace
from app.datasets.api_datasets import parse_body
from app.datasets.quota import lock_workspace_storage, storage_quota_problem
from app.datasets.quota import storage_used as _storage_used
from app.datasets.quota import workspace_quota as _quota
from app.datasets.schemas import MAX_PART, MIB, MIN_PART, UploadInit
from app.datasets.storage import DatasetStorage, get_storage
from app.datasets.storage_layout import upload_key
from app.db.models import (
    ArchiveFormat,
    Dataset,
    DatasetSource,
    DatasetVersion,
    Job,
    JobKind,
    UploadPart,
    UploadSession,
    UploadStatus,
    WorkspaceRole,
)

router = APIRouter(tags=["uploads"])

Db = Annotated[AsyncSession, Depends(get_db)]
Me = Annotated[Principal, Depends(current_principal)]
Storage = Annotated[DatasetStorage, Depends(get_storage)]
SESSION_TTL = timedelta(days=7)
SPOOL_BYTES = 1 * MIB
READ_CHUNK = 1 * MIB

_EXTENSIONS: list[tuple[str, ArchiveFormat]] = [
    (".tar.gz", ArchiveFormat.TAR_GZ),
    (".tgz", ArchiveFormat.TAR_GZ),
    (".tar.zst", ArchiveFormat.TAR_ZST),
    (".tzst", ArchiveFormat.TAR_ZST),
    (".tar", ArchiveFormat.TAR),
    (".zip", ArchiveFormat.ZIP),
    (".rar", ArchiveFormat.RAR),
]


def detect_format(filename: str) -> ArchiveFormat | None:
    low = filename.lower()
    for ext, fmt in _EXTENSIONS:
        if low.endswith(ext):
            return fmt
    return None


def plan_parts(size: int, requested: int) -> tuple[int, int]:
    """(part_size, part_count): clamp to [5 MiB, 64 MiB]; grow (MiB-aligned) if > 10000 parts."""
    part = min(max(requested, MIN_PART), MAX_PART)
    if math.ceil(size / part) > 10000:
        part = min(MAX_PART, math.ceil(size / 10000 / MIB) * MIB)
    return part, max(1, math.ceil(size / part))


def expected_part_size(s: UploadSession, n: int) -> int:
    return s.part_size if n < s.part_count else s.total_size - s.part_size * (s.part_count - 1)


def _now() -> datetime:
    return datetime.now(UTC)


def upload_json(s: UploadSession, parts: list[UploadPart]) -> dict[str, Any]:
    status = s.status
    if status == UploadStatus.ACTIVE and s.expires_at < _now():
        status = UploadStatus.EXPIRED
    return {
        "id": str(s.id),
        "workspace_id": str(s.workspace_id),
        "dataset_id": str(s.dataset_id) if s.dataset_id else None,
        "new_dataset_name": s.new_dataset_name,
        "filename": s.filename,
        "size": s.total_size,
        "sha256": s.sha256,
        "archive_format": s.archive_format.value,
        "part_size": s.part_size,
        "part_count": s.part_count,
        "parts": [
            {
                "part_number": p.part_number,
                "size": p.size,
                "sha256": p.sha256,
                "received_at": svc.iso(p.updated_at),
            }
            for p in sorted(parts, key=lambda p: p.part_number)
        ],
        "bytes_received": sum(p.size for p in parts),
        "status": status.value,
        "error_code": s.error_code,
        "expires_at": svc.iso(s.expires_at),
        "created_at": svc.iso(s.created_at),
        "completed_at": svc.iso(s.completed_at),
        "dataset_version_id": str(s.dataset_version_id) if s.dataset_version_id else None,
    }


async def _parts(db: AsyncSession, upload_id: uuid.UUID) -> list[UploadPart]:
    return list(
        (
            await db.execute(
                select(UploadPart).where(UploadPart.upload_id == upload_id).order_by(UploadPart.part_number)
            )
        )
        .scalars()
        .all()
    )


async def _load(
    db: AsyncSession, me: Principal, upload_id: uuid.UUID, *, for_update: bool = False
) -> UploadSession:
    q = select(UploadSession).where(UploadSession.id == upload_id)
    if for_update:
        q = q.with_for_update()
    s = (await db.execute(q)).scalar_one_or_none()
    if s is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    role = require_workspace(me, s.workspace_id, WorkspaceRole.MEMBER, "datasets:write", item=True)
    if s.created_by != me.user_id and not at_least(role, WorkspaceRole.ADMIN):
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    return s


# --------------------------------------------------------------------------------------------------
@router.get("/uploads", operation_id="listUploads")
async def list_uploads(
    db: Db,
    me: Me,
    workspace_id: uuid.UUID,
    status: UploadStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> JSONResponse:
    require_workspace(me, workspace_id, WorkspaceRole.MEMBER, "datasets:write", item=False)
    q = select(UploadSession).where(
        UploadSession.workspace_id == workspace_id, UploadSession.created_by == me.user_id
    )
    if status == UploadStatus.EXPIRED:
        q = q.where(
            (UploadSession.status == UploadStatus.EXPIRED)
            | ((UploadSession.status == UploadStatus.ACTIVE) & (UploadSession.expires_at < func.now()))
        )
    elif status == UploadStatus.ACTIVE:
        q = q.where(UploadSession.status == UploadStatus.ACTIVE, UploadSession.expires_at >= func.now())
    elif status is not None:
        q = q.where(UploadSession.status == status)
    if cursor:
        c = decode_cursor(cursor)
        ts, cid = datetime.fromisoformat(str(c["c"])), uuid.UUID(str(c["i"]))
        q = q.where(
            (UploadSession.created_at < ts) | ((UploadSession.created_at == ts) & (UploadSession.id < cid))
        )
    rows = (
        (
            await db.execute(
                q.order_by(UploadSession.created_at.desc(), UploadSession.id.desc()).limit(limit + 1)
            )
        )
        .scalars()
        .all()
    )
    page = rows[:limit]
    items = [upload_json(s, await _parts(db, s.id)) for s in page]
    nxt = (
        encode_cursor({"c": page[-1].created_at.isoformat(), "i": str(page[-1].id)})
        if len(rows) > limit and page
        else None
    )
    return JSONResponse({"items": items, "next_cursor": nxt})


@router.post("/uploads", operation_id="initUpload", status_code=201)
async def init_upload(request: Request, db: Db, me: Me, s3: Storage) -> JSONResponse:
    body: UploadInit = await parse_body(request, UploadInit)
    require_workspace(me, body.workspace_id, WorkspaceRole.MEMBER, "datasets:write", item=False)
    fmt = body.archive_format or detect_format(body.filename)
    if fmt is None:
        raise ProblemError(422, ErrorCode.ARCHIVE_FORMAT_UNSUPPORTED, "use zip, tar, tar.gz, tar.zst or rar")
    if body.dataset_id is not None:
        ds, _ = await svc.load_dataset(db, me, body.dataset_id, WorkspaceRole.MEMBER, write=True)
        if ds.workspace_id != body.workspace_id:
            raise ProblemError(404, ErrorCode.NOT_FOUND)
    else:
        assert body.new_dataset_name is not None  # noqa: S101 - schema guarantees exactly one target
        if await svc.name_taken(db, body.workspace_id, svc.slugify(body.new_dataset_name)):
            raise ProblemError(409, ErrorCode.DATASET_NAME_TAKEN)
    # Natural resume: same user / workspace / sha256 / size and still active.
    existing = (
        await db.execute(
            select(UploadSession)
            .where(
                UploadSession.workspace_id == body.workspace_id,
                UploadSession.created_by == me.user_id,
                UploadSession.sha256 == body.sha256,
                UploadSession.total_size == body.size,
                UploadSession.status == UploadStatus.ACTIVE,
                UploadSession.expires_at > func.now(),
            )
            .order_by(UploadSession.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return JSONResponse(upload_json(existing, await _parts(db, existing.id)), status_code=200)
    max_upload, storage = await _quota(db, body.workspace_id, me.user_id)
    if body.size > max_upload:
        raise ProblemError(
            403,
            ErrorCode.QUOTA_EXCEEDED,
            "file exceeds the per-upload limit",
            params={"limit_gb": round(max_upload / 1024**3, 1), "kind": "max_upload_bytes"},
        )
    await lock_workspace_storage(db, body.workspace_id)
    if await _storage_used(db, body.workspace_id) + body.size > storage:
        raise storage_quota_problem(storage)
    part_size, part_count = plan_parts(body.size, body.part_size)
    uid = uuid.uuid4()
    key = upload_key(body.workspace_id, uid, body.filename)
    s3_upload_id = await s3.create_multipart(BUCKET_UPLOADS, key)
    s = UploadSession(
        id=uid,
        workspace_id=body.workspace_id,
        created_by=me.user_id,
        dataset_id=body.dataset_id,
        new_dataset_name=body.new_dataset_name if body.dataset_id is None else None,
        filename=body.filename,
        archive_format=fmt,
        total_size=body.size,
        part_size=part_size,
        part_count=part_count,
        sha256=body.sha256,
        s3_bucket=BUCKET_UPLOADS,
        s3_key=key,
        s3_upload_id=s3_upload_id,
        status=UploadStatus.ACTIVE,
        expires_at=_now() + SESSION_TTL,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return JSONResponse(upload_json(s, []), status_code=201)


@router.get("/uploads/{upload_id}", operation_id="getUpload")
async def get_upload(upload_id: uuid.UUID, db: Db, me: Me) -> JSONResponse:
    s = await _load(db, me, upload_id)
    return JSONResponse(upload_json(s, await _parts(db, s.id)))


@router.delete("/uploads/{upload_id}", operation_id="abortUpload", status_code=204)
async def abort_upload(upload_id: uuid.UUID, db: Db, me: Me, s3: Storage) -> Response:
    s = await _load(db, me, upload_id, for_update=True)
    if s.status in (UploadStatus.ABORTED, UploadStatus.EXPIRED):
        return Response(status_code=204)
    if s.status != UploadStatus.ACTIVE:
        raise ProblemError(409, ErrorCode.UPLOAD_NOT_ACTIVE, f"upload is {s.status.value}")
    await s3.abort_multipart(s.s3_bucket, s.s3_key, s.s3_upload_id)
    s.status = UploadStatus.ABORTED
    await db.commit()
    return Response(status_code=204)


@router.put("/uploads/{upload_id}/parts/{part_number}", operation_id="uploadPart")
async def upload_part(
    upload_id: uuid.UUID,
    part_number: Annotated[int, Path(ge=1, le=10000)],
    request: Request,
    db: Db,
    me: Me,
    s3: Storage,
    x_content_sha256: Annotated[str | None, Header(alias="X-Content-SHA256")] = None,
    content_length: Annotated[str | None, Header(alias="Content-Length")] = None,
) -> JSONResponse:
    if content_length is None or not content_length.isdigit():
        raise ProblemError(411, ErrorCode.LENGTH_REQUIRED, "Content-Length is required")
    length = int(content_length)
    if length > MAX_PART:
        raise ProblemError(
            413, ErrorCode.UPLOAD_TOO_LARGE, "a part is at most 64 MiB", params={"max_bytes": MAX_PART}
        )
    sha = (x_content_sha256 or "").strip()
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ProblemError(
            422,
            ErrorCode.VALIDATION_FAILED,
            "X-Content-SHA256 must be the lower-case hex sha256 of the body",
            errors=[{"loc": ["header", "X-Content-SHA256"], "code": "pattern", "message": "^[0-9a-f]{64}$"}],
        )
    s = await _load(db, me, upload_id)
    if s.status != UploadStatus.ACTIVE or s.expires_at < _now():
        raise ProblemError(409, ErrorCode.UPLOAD_NOT_ACTIVE, f"upload is {upload_json(s, [])['status']}")
    if part_number > s.part_count:
        raise ProblemError(422, ErrorCode.UPLOAD_PART_OUT_OF_RANGE, params={"part_count": s.part_count})
    expected = expected_part_size(s, part_number)
    if length != expected:
        raise ProblemError(
            422, ErrorCode.UPLOAD_PART_SIZE_INVALID, params={"expected": expected, "actual": length}
        )
    # Release the DB connection while the (possibly slow) body streams in.
    bucket, key, s3_upload_id = s.s3_bucket, s.s3_key, s.s3_upload_id
    await db.rollback()
    h = hashlib.sha256()
    received = 0
    with tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES) as buf:
        async for chunk in request.stream():
            received += len(chunk)
            if received > length:
                raise ProblemError(422, ErrorCode.UPLOAD_PART_SIZE_INVALID, "body longer than Content-Length")
            h.update(chunk)
            buf.write(chunk)
        if received != length:
            raise ProblemError(
                422,
                ErrorCode.UPLOAD_PART_SIZE_INVALID,
                "body shorter than Content-Length",
                params={"expected": length, "actual": received},
            )
        if h.hexdigest() != sha:
            raise ProblemError(422, ErrorCode.UPLOAD_PART_CHECKSUM_MISMATCH, "part discarded; re-send it")
        buf.seek(0)
        etag = await s3.put_part_file(bucket, key, s3_upload_id, part_number, buf, length)
    # Re-check state (abort/complete may have raced) and record the part.
    s2 = await _load(db, me, upload_id, for_update=True)
    if s2.status != UploadStatus.ACTIVE:
        await db.rollback()
        raise ProblemError(409, ErrorCode.UPLOAD_NOT_ACTIVE)
    stmt = insert(UploadPart).values(
        upload_id=upload_id, part_number=part_number, size=length, sha256=sha, etag=etag
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[UploadPart.upload_id, UploadPart.part_number],
        set_={"size": length, "sha256": sha, "etag": etag, "updated_at": func.now()},
    )
    await db.execute(stmt)
    s2.expires_at = _now() + SESSION_TTL
    await db.commit()
    part = (
        await db.execute(
            select(UploadPart).where(UploadPart.upload_id == upload_id, UploadPart.part_number == part_number)
        )
    ).scalar_one()
    return JSONResponse(
        {
            "part_number": part.part_number,
            "size": part.size,
            "sha256": part.sha256,
            "received_at": svc.iso(part.updated_at),
        }
    )


async def _completed_body(db: AsyncSession, s: UploadSession) -> dict[str, Any]:
    assert s.dataset_version_id is not None  # noqa: S101 - completed sessions always reference a version
    v = await db.get(DatasetVersion, s.dataset_version_id)
    if v is None:
        raise ProblemError(404, ErrorCode.NOT_FOUND)
    ds = await db.get(Dataset, v.dataset_id)
    job = (
        await db.execute(
            select(Job)
            .where(Job.dataset_version_id == v.id, Job.kind == JobKind.VALIDATE_DATASET)
            .order_by(Job.created_at.asc())
            .limit(1)
        )
    ).scalar_one()
    assert ds is not None  # noqa: S101
    return {
        "upload": upload_json(s, await _parts(db, s.id)),
        "dataset": await svc.dataset_full(db, ds),
        "version": svc.version_summary(v),
        "job": svc.job_json(job),
    }


@router.post("/uploads/{upload_id}/complete", operation_id="completeUpload", status_code=202)
async def complete_upload(upload_id: uuid.UUID, db: Db, me: Me, s3: Storage) -> JSONResponse:
    s = await _load(db, me, upload_id, for_update=True)
    if s.status == UploadStatus.COMPLETED:
        return JSONResponse(await _completed_body(db, s), status_code=202)
    if s.status != UploadStatus.ACTIVE or s.expires_at < _now():
        raise ProblemError(409, ErrorCode.UPLOAD_NOT_ACTIVE, f"upload is {upload_json(s, [])['status']}")
    parts = await _parts(db, s.id)
    have = {p.part_number for p in parts}
    missing = [n for n in range(1, s.part_count + 1) if n not in have]
    if missing:
        raise ProblemError(
            409, ErrorCode.UPLOAD_INCOMPLETE, f"{len(missing)} part(s) missing", missing_parts=missing[:10000]
        )
    if sum(p.size for p in parts) != s.total_size:
        raise ProblemError(409, ErrorCode.UPLOAD_INCOMPLETE, "received bytes differ from the declared size")
    created = False
    if s.dataset_id is not None:
        ds = (
            await db.execute(select(Dataset).where(Dataset.id == s.dataset_id, Dataset.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if ds is None:
            raise ProblemError(404, ErrorCode.NOT_FOUND, "target dataset was deleted")
    else:
        assert s.new_dataset_name is not None  # noqa: S101 - check constraint target_exactly_one
        ds = await svc.create_dataset(db, s.workspace_id, s.new_dataset_name, "", me.user_id)
        created = True
    v = await svc.new_version(db, ds, DatasetSource.UPLOAD, str(s.id), me.user_id)
    # SEC-input-3: the archive may expand up to 100x; the worker caps extraction at what the
    # workspace quota still allows (this session's own bytes are counted as pending, add them back).
    _, storage = await _quota(db, s.workspace_id, me.user_id)
    cap = max(0, storage - await _storage_used(db, s.workspace_id) + int(s.total_size))
    job = svc.new_job(
        ds.workspace_id,
        JobKind.VALIDATE_DATASET,
        v.id,
        me.user_id,
        {"upload_id": str(s.id), "max_bytes": cap},
    )
    db.add(job)
    s.status = UploadStatus.COMPLETED
    s.completed_at = _now()
    s.dataset_version_id = v.id
    if created:
        await audit.record(
            AuditAction.DATASET_CREATED,
            db=db,
            actor=me,
            workspace_id=ds.workspace_id,
            target_type="dataset",
            target_id=str(ds.id),
            details={"name": ds.name},
        )
    await audit.record(
        AuditAction.DATASET_VERSION_CREATED,
        db=db,
        actor=me,
        workspace_id=ds.workspace_id,
        target_type="dataset_version",
        target_id=str(v.id),
        details={"source": "upload", "upload_id": str(s.id), "bytes": s.total_size},
    )
    await db.flush()
    # S3 completion last: if it fails the transaction rolls back and the client may retry.
    await s3.complete_multipart(
        s.s3_bucket, s.s3_key, s.s3_upload_id, [(p.part_number, p.etag) for p in parts]
    )
    await db.commit()
    await db.refresh(s)
    return JSONResponse(await _completed_body(db, s), status_code=202)


# --------------------------------------------------------------------------------------------------
# maintenance (called by the API maintenance loop, hourly; docs/db-schema.md "Retention")
# --------------------------------------------------------------------------------------------------
async def expire_stale_uploads(db: AsyncSession, s3: DatasetStorage, limit: int = 500) -> int:
    """Abort S3 multipart uploads of sessions past ``expires_at`` and mark them ``expired``."""
    rows = (
        (
            await db.execute(
                select(UploadSession)
                .where(UploadSession.status == UploadStatus.ACTIVE, UploadSession.expires_at < func.now())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for s in rows:
        await s3.abort_multipart(s.s3_bucket, s.s3_key, s.s3_upload_id)
        s.status = UploadStatus.EXPIRED
    await db.commit()
    return len(rows)
