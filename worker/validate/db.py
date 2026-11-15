"""Postgres access for the CPU worker: ``jobs`` claim/lease protocol (run-lifecycle.md 7.3) and
``dataset_versions`` updates. Plain SQLAlchemy Core with bound parameters only.

Local adapter: the worker does not import the backend package; table/column names are those of
``backend/app/db/models.py`` (contract v0.1).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Double,
    Engine,
    Integer,
    Uuid,
    bindparam,
    column,
    create_engine,
    func,
    table,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.types import String

CPU_KINDS = ("validate_dataset", "import_hf_dataset", "merge_datasets", "push_model_hub")
DEFAULT_STORAGE_BYTES = 200 * 1024**3  # backend/app/datasets/api_uploads.py DEFAULT_STORAGE


@dataclass(slots=True)
class JobRow:
    id: uuid.UUID
    workspace_id: uuid.UUID
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    dataset_version_id: uuid.UUID | None
    created_by: uuid.UUID | None
    model_id: uuid.UUID | None = None


@dataclass(slots=True)
class VersionRow:
    id: uuid.UUID
    dataset_id: uuid.UUID
    workspace_id: uuid.UUID
    version: int
    status: str
    source: str
    source_ref: str | None
    content_hash: str | None
    storage_prefix: str | None
    merged_from: list[uuid.UUID] | None
    dataset_slug: str


@dataclass(slots=True)
class UploadRow:
    id: uuid.UUID
    s3_bucket: str
    s3_key: str
    sha256: str
    filename: str
    total_size: int


# Typed Core view of the columns the worker writes (names/types from backend/app/db/models.py).
_VERSIONS = table(
    "dataset_versions",
    column("id", Uuid()),
    column("status", String(32)),
    column("content_hash", String(64)),
    column("storage_prefix", String(512)),
    column("size_bytes", BigInteger()),
    column("codebase_version", String(16)),
    column("converted_from", String(16)),
    column("robot_type", String(64)),
    column("fps", Double()),
    column("total_episodes", Integer()),
    column("total_frames", BigInteger()),
    column("camera_keys", ARRAY(String(128))),
    column("features", JSONB()),
    column("info", JSONB()),
    column("stats", JSONB()),
    column("validate_report", JSONB()),
    column("preview", JSONB()),
    column("ready_at", DateTime(timezone=True)),
    column("updated_at", DateTime(timezone=True)),
    column("deleted_at", DateTime(timezone=True)),
)


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=2)


_CLAIM = text(
    """
    UPDATE jobs SET status = 'running', lease_owner = :me,
           lease_expires_at = now() + make_interval(secs => :lease),
           attempts = attempts + 1, started_at = coalesce(started_at, now()), updated_at = now()
    WHERE id = (
        SELECT id FROM jobs
        WHERE status = 'queued' AND resource = 'cpu' AND kind IN :kinds
        ORDER BY priority DESC, created_at ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING id, workspace_id, kind, payload, attempts, max_attempts, dataset_version_id, created_by,
              model_id
    """
).bindparams(bindparam("kinds", expanding=True))


class Db:
    def __init__(self, engine: Engine, worker_id: str, lease_s: int = 60) -> None:
        self.engine = engine
        self.me = worker_id
        self.lease_s = lease_s

    # ---- jobs --------------------------------------------------------------------------------
    def claim(self, kinds: tuple[str, ...] = CPU_KINDS) -> JobRow | None:
        with self.engine.begin() as c:
            row = (
                c.execute(_CLAIM, {"me": self.me, "lease": self.lease_s, "kinds": list(kinds)})
                .mappings()
                .first()
            )
        if row is None:
            return None
        return JobRow(
            id=row["id"],
            workspace_id=row["workspace_id"],
            kind=row["kind"],
            payload=dict(row["payload"] or {}),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            dataset_version_id=row["dataset_version_id"],
            created_by=row["created_by"],
            model_id=row["model_id"],
        )

    def heartbeat(self, job_id: uuid.UUID, progress: float, stage: str | None) -> bool:
        """Extend the lease; ``False`` => lease lost or job cancelled (stop work immediately)."""
        with self.engine.begin() as c:
            row = c.execute(
                text(
                    """
                    UPDATE jobs SET lease_expires_at = now() + make_interval(secs => :lease),
                           progress = :progress,
                           result = coalesce(result, '{}'::jsonb)
                                    || jsonb_build_object('stage', CAST(:stage AS text)),
                           updated_at = now()
                    WHERE id = :id AND lease_owner = :me AND status = 'running'
                    RETURNING id
                    """
                ),
                {
                    "lease": self.lease_s,
                    "progress": min(max(progress, 0.0), 1.0),
                    "stage": stage,
                    "id": job_id,
                    "me": self.me,
                },
            ).first()
        return row is not None

    def finish(
        self,
        job_id: uuid.UUID,
        status: str,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        with self.engine.begin() as c:
            row = c.execute(
                text(
                    """
                    UPDATE jobs SET status = :status, result = :result, error_code = :ec,
                           error_message = :em,
                           progress = CASE WHEN :done THEN 1 ELSE progress END,
                           finished_at = now(), lease_owner = NULL, lease_expires_at = NULL,
                           updated_at = now()
                    WHERE id = :id AND lease_owner = :me
                    RETURNING id
                    """
                ).bindparams(bindparam("result", type_=JSONB)),
                {
                    "status": status,
                    "done": status == "succeeded",
                    "result": result,
                    "ec": error_code,
                    "em": error_message,
                    "id": job_id,
                    "me": self.me,
                },
            ).first()
        return row is not None

    def requeue(self, job_id: uuid.UUID, error_code: str, error_message: str) -> bool:
        with self.engine.begin() as c:
            row = c.execute(
                text(
                    """
                    UPDATE jobs SET status = 'queued', lease_owner = NULL, lease_expires_at = NULL,
                           error_code = :ec, error_message = :em, updated_at = now()
                    WHERE id = :id AND lease_owner = :me
                    RETURNING id
                    """
                ),
                {"ec": error_code, "em": error_message, "id": job_id, "me": self.me},
            ).first()
        return row is not None

    # ---- models (push_model_hub) -----------------------------------------------------------------
    def get_model(self, model_id: uuid.UUID) -> dict[str, Any] | None:
        with self.engine.begin() as c:
            r = (
                c.execute(
                    text(
                        "SELECT id, name, policy_type, status, bundle_uri, deleted_at "
                        "FROM models WHERE id = :i"
                    ),
                    {"i": model_id},
                )
                .mappings()
                .first()
            )
        return None if r is None else dict(r)

    def mark_pushed(self, model_id: uuid.UUID, repo_id: str) -> None:
        with self.engine.begin() as c:
            c.execute(
                text(
                    "UPDATE models SET hub_repo_id = :r, hub_pushed_at = now(), updated_at = now() "
                    "WHERE id = :i"
                ),
                {"r": repo_id, "i": model_id},
            )

    # ---- storage quota (SEC-input-3) ----------------------------------------------------------
    def storage_remaining(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID | None, version_id: uuid.UUID
    ) -> int:
        """Bytes the workspace may still store for ``version_id``.

        Same rule as the API's upload check (``backend/app/datasets/api_uploads.py`` ``_quota`` /
        ``_storage_used``): limit = workspace quota row, else the user's row, else 200 GiB; used =
        every live dataset version of the workspace except ``version_id`` itself + active uploads +
        the ``max_bytes`` reserved by other queued/running HF imports and merges
        (``backend/app/datasets/quota.py`` ``reserved_bytes``).
        """
        with self.engine.begin() as c:
            rows = c.execute(
                text(
                    "SELECT user_id, storage_bytes FROM quotas WHERE workspace_id = :w "
                    "AND (user_id IS NULL OR user_id = :u)"
                ),
                {"w": workspace_id, "u": user_id},
            ).all()
            used = c.execute(
                text(
                    """
                    SELECT coalesce((SELECT sum(v.size_bytes) FROM dataset_versions v
                                     JOIN datasets d ON d.id = v.dataset_id
                                     WHERE d.workspace_id = :w AND v.deleted_at IS NULL AND v.id <> :v), 0)
                         + coalesce((SELECT sum(total_size) FROM upload_sessions
                                     WHERE workspace_id = :w AND status = 'active' AND expires_at > now()
                                       AND (dataset_version_id IS NULL OR dataset_version_id <> :v)), 0)
                         + coalesce((SELECT sum((j.payload->>'max_bytes')::bigint) FROM jobs j
                                     JOIN dataset_versions jv ON jv.id = j.dataset_version_id
                                     WHERE j.workspace_id = :w
                                       AND j.kind IN ('import_hf_dataset', 'merge_datasets')
                                       AND j.status IN ('queued', 'running')
                                       AND jv.deleted_at IS NULL AND jv.size_bytes IS NULL
                                       AND j.dataset_version_id <> :v), 0)
                    """
                ),
                {"w": workspace_id, "v": version_id},
            ).scalar_one()
        ws_row = next((r for r in rows if r[0] is None), None)
        user_row = next((r for r in rows if r[0] is not None), None)
        row = ws_row or user_row
        limit = int(row[1]) if row is not None else DEFAULT_STORAGE_BYTES
        return limit - int(used or 0)

    # ---- dataset versions -------------------------------------------------------------------
    def get_version(self, version_id: uuid.UUID) -> VersionRow | None:
        with self.engine.begin() as c:
            r = c.execute(
                text(
                    """
                    SELECT v.id, v.dataset_id, d.workspace_id, v.version, v.status, v.source, v.source_ref,
                           v.content_hash, v.storage_prefix, v.merged_from, d.slug
                    FROM dataset_versions v JOIN datasets d ON d.id = v.dataset_id
                    WHERE v.id = :id
                    """
                ),
                {"id": version_id},
            ).first()
        if r is None:
            return None
        return VersionRow(
            id=r[0],
            dataset_id=r[1],
            workspace_id=r[2],
            version=int(r[3]),
            status=r[4],
            source=r[5],
            source_ref=r[6],
            content_hash=r[7],
            storage_prefix=r[8],
            merged_from=list(r[9]) if r[9] else None,
            dataset_slug=r[10],
        )

    def get_upload_for_version(self, version_id: uuid.UUID) -> UploadRow | None:
        with self.engine.begin() as c:
            r = c.execute(
                text(
                    """
                    SELECT id, s3_bucket, s3_key, sha256, filename, total_size FROM upload_sessions
                    WHERE dataset_version_id = :v ORDER BY completed_at DESC NULLS LAST LIMIT 1
                    """
                ),
                {"v": version_id},
            ).first()
        if r is None:
            return None
        return UploadRow(
            id=r[0], s3_bucket=r[1], s3_key=r[2], sha256=r[3], filename=r[4], total_size=int(r[5])
        )

    def set_version_status(
        self, version_id: uuid.UUID, status: str, report: dict[str, Any] | None = None
    ) -> None:
        with self.engine.begin() as c:
            c.execute(
                text(
                    """
                    UPDATE dataset_versions SET status = :s,
                           validate_report = coalesce(:r, validate_report), updated_at = now()
                    WHERE id = :id AND deleted_at IS NULL
                    """
                ).bindparams(bindparam("r", type_=JSONB)),
                {"s": status, "r": report, "id": version_id},
            )

    def duplicate_of(
        self, dataset_id: uuid.UUID, version_id: uuid.UUID, content_hash: str
    ) -> uuid.UUID | None:
        with self.engine.begin() as c:
            r = c.execute(
                text(
                    """
                    SELECT id FROM dataset_versions
                    WHERE dataset_id = :d AND content_hash = :h AND id <> :v AND deleted_at IS NULL
                    LIMIT 1
                    """
                ),
                {"d": dataset_id, "h": content_hash, "v": version_id},
            ).first()
        return None if r is None else uuid.UUID(str(r[0]))

    def finalize_version(self, version_id: uuid.UUID, status: str, fields: dict[str, Any]) -> None:
        """Write the validation outcome. ``fields`` keys are dataset_versions column names."""
        allowed = {
            "content_hash",
            "storage_prefix",
            "size_bytes",
            "codebase_version",
            "converted_from",
            "robot_type",
            "fps",
            "total_episodes",
            "total_frames",
            "camera_keys",
            "features",
            "info",
            "stats",
            "validate_report",
            "preview",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown version fields {unknown}")
        values: dict[str, Any] = dict(fields)
        values["status"] = status
        values["updated_at"] = func.now()
        if status == "ready":
            values["ready_at"] = func.now()
        stmt = (
            update(_VERSIONS)
            .where(_VERSIONS.c.id == version_id, _VERSIONS.c.deleted_at.is_(None))
            .values(**values)
        )
        with self.engine.begin() as c:
            c.execute(stmt)


def to_json_safe(obj: Any) -> Any:
    """Round-trip through json to drop numpy scalars / NaN (stored JSONB must be strict JSON)."""
    return json.loads(json.dumps(obj, default=float, allow_nan=False))
