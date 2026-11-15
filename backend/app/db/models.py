"""Hibiscus database schema v0.1 (FROZEN contract, owner A1). PostgreSQL 16 only.

SQLAlchemy 2.0 typed declarative models. Every agent imports these; nobody edits them without a
contract change request (docs/CONTRACT_NOTES.md). Narrative description: docs/db-schema.md.

Conventions
-----------
* Primary keys: UUID (v4, generated in Python) except append-only high-volume tables
  (audit_events, run_events, gpu_telemetry) which use BIGINT identity.
* Every table has ``created_at``/``updated_at`` (timestamptz, server defaults). Append-only tables
  keep the columns for uniformity; ``updated_at`` never changes there.
* Soft delete (``deleted_at``) for workspaces, datasets, dataset_versions and models (PLAN §4).
* Enumerations are stored as VARCHAR + CHECK constraint (``native_enum=False``) so adding a value is
  a plain migration. The Python ``StrEnum`` classes below are the single source of truth and the
  OpenAPI enums use exactly the same values.
* All timestamps are timezone-aware UTC.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# --------------------------------------------------------------------------------------------------
# Base
# --------------------------------------------------------------------------------------------------
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
    }


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(
        cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


# --------------------------------------------------------------------------------------------------
# Enumerations (shared with OpenAPI components.schemas.*)
# --------------------------------------------------------------------------------------------------
class WorkspaceRole(enum.StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class OneTimeTokenPurpose(enum.StrEnum):
    EMAIL_VERIFY = "email_verify"
    PASSWORD_RESET = "password_reset"  # noqa: S105 - enum label, not a secret
    MFA_CHALLENGE = "mfa_challenge"  # short-lived (5 min) token between password step and TOTP step
    EMAIL_CHANGE = "email_change"


class SessionRevokeReason(enum.StrEnum):
    LOGOUT = "logout"
    USER_REVOKED = "user_revoked"
    ADMIN_REVOKED = "admin_revoked"
    REFRESH_REUSE = "refresh_reuse"
    PASSWORD_CHANGED = "password_changed"  # noqa: S105
    EXPIRED = "expired"


class PatScope(enum.StrEnum):
    DATASETS_READ = "datasets:read"
    DATASETS_WRITE = "datasets:write"
    RUNS_READ = "runs:read"
    RUNS_WRITE = "runs:write"
    MODELS_READ = "models:read"


class ArchiveFormat(enum.StrEnum):
    ZIP = "zip"
    TAR = "tar"
    TAR_GZ = "tar.gz"
    TAR_ZST = "tar.zst"
    RAR = "rar"


class UploadStatus(enum.StrEnum):
    ACTIVE = "active"
    COMPLETING = "completing"
    COMPLETED = "completed"
    ABORTED = "aborted"
    EXPIRED = "expired"
    FAILED = "failed"


class DatasetSource(enum.StrEnum):
    UPLOAD = "upload"
    HF_IMPORT = "hf_import"
    MERGE = "merge"


class DatasetVersionStatus(enum.StrEnum):
    PENDING = "pending"  # row created at upload completion / import request
    UNPACKING = "unpacking"
    VALIDATING = "validating"
    READY = "ready"
    INVALID = "invalid"  # validation ran and found blocking problems (user-fixable)
    FAILED = "failed"  # infrastructure error during unpack/validate (retryable)


class RunStatus(enum.StrEnum):
    """State machine: docs/spec/run-lifecycle.md."""

    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    EXPORTING = "exporting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


RUN_TERMINAL_STATUSES = frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED})


class MixedPrecision(enum.StrEnum):
    NO = "no"
    FP16 = "fp16"
    BF16 = "bf16"


class JobKind(enum.StrEnum):
    VALIDATE_DATASET = "validate_dataset"  # unpack + validate + preview (A3, worker/validate)
    IMPORT_HF_DATASET = "import_hf_dataset"  # A3
    MERGE_DATASETS = "merge_datasets"  # A3
    EXPORT_MODEL = "export_model"  # bundle + ONNX + parity (A5, worker/export)
    EVAL_CHECKPOINT = "eval_checkpoint"  # offline held-out eval (A5, worker/eval)
    PUSH_MODEL_HUB = "push_model_hub"  # A5
    ESTIMATE_RESOURCES = "estimate_resources"  # 20-step dry run (A4, worker/train)


class JobResource(enum.StrEnum):
    CPU = "cpu"
    GPU = "gpu"


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OnnxStatus(enum.StrEnum):
    NOT_SUPPORTED = "not_supported"
    PENDING = "pending"
    EXPORTING = "exporting"
    PASSED = "passed"
    FAILED = "failed"


class ModelStatus(enum.StrEnum):
    PENDING = "pending"
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"


class GpuNodeStatus(enum.StrEnum):
    ONLINE = "online"
    DRAINING = "draining"
    OFFLINE = "offline"
    DISABLED = "disabled"


class NotificationChannelKind(enum.StrEnum):
    EMAIL = "email"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    WEBHOOK = "webhook"


class UserSecretKind(enum.StrEnum):
    HF_TOKEN = "hf_token"  # noqa: S105


# --------------------------------------------------------------------------------------------------
# Identity, auth
# --------------------------------------------------------------------------------------------------
class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), nullable=False)  # stored lower-cased
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # argon2id PHC string
    password_changed_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column()
    locale: Mapped[str] = mapped_column(String(5), server_default="vi", nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    # TOTP secret encrypted with the app data key (AES-256-GCM, nonce||ciphertext||tag).
    totp_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    totp_enabled_at: Mapped[datetime | None] = mapped_column()
    totp_last_used_step: Mapped[int | None] = mapped_column(BigInteger)  # replay protection
    failed_login_count: Mapped[int] = mapped_column(SmallInteger, server_default="0", nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column()
    last_login_at: Mapped[datetime | None] = mapped_column()

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", foreign_keys="Membership.user_id"
    )

    __table_args__ = (
        Index("uq_users_email_lower", func.lower(email), unique=True),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("locale IN ('vi','en')", name="locale_supported"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_nonneg"),
    )


class RecoveryCode(TimestampMixin, Base):
    __tablename__ = "recovery_codes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # argon2id
    used_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (Index(None, "user_id"),)


class OneTimeToken(TimestampMixin, Base):
    """Email verification / password reset / MFA challenge tokens (single use, hashed)."""

    __tablename__ = "one_time_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    purpose: Mapped[OneTimeTokenPurpose] = mapped_column(_enum(OneTimeTokenPurpose, "one_time_token_purpose"))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)  # sha256(token)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None] = mapped_column()
    payload: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"), nullable=False)

    __table_args__ = (
        UniqueConstraint("token_hash"),
        Index(None, "user_id", "purpose"),
    )


class Session(TimestampMixin, Base):
    """One row per refresh token. Rotation creates a new row in the same family; presenting a
    rotated (``rotated_at`` not null) token again => revoke the whole family (reuse detection)."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    refresh_token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"))
    rotated_at: Mapped[datetime | None] = mapped_column()
    expires_at: Mapped[datetime] = mapped_column(nullable=False)  # absolute: family start + 30 d
    idle_expires_at: Mapped[datetime] = mapped_column(nullable=False)  # sliding: last use + 7 d
    last_used_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    mfa_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    revoked_at: Mapped[datetime | None] = mapped_column()
    revoked_reason: Mapped[SessionRevokeReason | None] = mapped_column(
        _enum(SessionRevokeReason, "session_revoke_reason")
    )

    __table_args__ = (
        UniqueConstraint("refresh_token_hash"),
        Index(None, "user_id", "revoked_at"),
        Index(None, "family_id"),
    )


class ApiToken(TimestampMixin, Base):
    """Personal Access Token. Plaintext format ``hbp_<8-char prefix>_<32 bytes base62>`` shown once."""

    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)  # sha256(full token)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column()  # null = never (UI default 90 d)
    last_used_at: Mapped[datetime | None] = mapped_column()
    last_used_ip: Mapped[str | None] = mapped_column(INET)
    revoked_at: Mapped[datetime | None] = mapped_column()
    # Minted from a 2FA-verified session (SEC-auth-01 residual). A PAT without it never acts
    # with owner/admin power, see ``core.deps._pat_principal``.
    mfa_verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)

    __table_args__ = (
        UniqueConstraint("token_hash"),
        UniqueConstraint("prefix"),
        Index(None, "user_id"),
        CheckConstraint("cardinality(scopes) >= 1", name="scopes_nonempty"),
        CheckConstraint(
            "scopes <@ ARRAY['datasets:read','datasets:write','runs:read','runs:write',"
            "'models:read']::varchar[]",
            name="scopes_known",
        ),
    )


class AuditEvent(Base):
    """Append-only. Immutability: the initial migration installs a trigger that raises on UPDATE /
    DELETE, and rows are hash-chained (hash = sha256(prev_hash || canonical_json(row)))."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_token_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("api_tokens.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # catalog: docs/db-schema.md §Audit
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(16), server_default="success", nullable=False)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    request_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"), nullable=False)
    prev_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)

    __table_args__ = (
        Index(None, "workspace_id", "created_at"),
        Index(None, "actor_user_id", "created_at"),
        Index(None, "action", "created_at"),
        CheckConstraint("outcome IN ('success','failure','denied')", name="outcome_known"),
    )


# --------------------------------------------------------------------------------------------------
# Workspaces & RBAC
# --------------------------------------------------------------------------------------------------
class Role(TimestampMixin, Base):
    """Lookup table of workspace roles (seeded: owner, admin, member, viewer). PLAN §4 ``roles``."""

    __tablename__ = "roles"

    name: Mapped[WorkspaceRole] = mapped_column(_enum(WorkspaceRole, "workspace_role"), primary_key=True)
    rank: Mapped[int] = mapped_column(
        SmallInteger, nullable=False
    )  # owner 40 > admin 30 > member 20 > viewer 10
    requires_mfa: Mapped[bool] = mapped_column(Boolean, nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)

    __table_args__ = (UniqueConstraint("rank"),)


class Workspace(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    settings: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"), nullable=False)

    __table_args__ = (
        Index("uq_workspaces_slug_live", "slug", unique=True, postgresql_where=text("deleted_at IS NULL")),
        CheckConstraint("slug ~ '^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$'", name="slug_format"),
    )


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[WorkspaceRole] = mapped_column(
        _enum(WorkspaceRole, "workspace_role"), ForeignKey("roles.name"), nullable=False
    )
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    user: Mapped[User] = relationship(back_populates="memberships", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id"),
        Index(None, "user_id"),
    )


class Invite(TimestampMixin, Base):
    """Single-use, 72 h. Accepting creates the user (if new) + membership (register-invite flow)."""

    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[WorkspaceRole] = mapped_column(
        _enum(WorkspaceRole, "workspace_role"), ForeignKey("roles.name"), nullable=False
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column()
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    revoked_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        UniqueConstraint("token_hash"),
        Index(None, "workspace_id", "email"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("role <> 'owner'", name="cannot_invite_owner"),
    )


class Quota(TimestampMixin, Base):
    """``user_id IS NULL`` = workspace-wide limit; a row with user_id overrides per member."""

    __tablename__ = "quotas"

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    max_concurrent_runs: Mapped[int] = mapped_column(SmallInteger, server_default="1", nullable=False)
    max_queued_runs: Mapped[int] = mapped_column(SmallInteger, server_default="10", nullable=False)
    gpu_hours_per_month: Mapped[float] = mapped_column(Double, server_default="200", nullable=False)
    storage_bytes: Mapped[int] = mapped_column(BigInteger, server_default=str(200 * 1024**3), nullable=False)
    max_upload_bytes: Mapped[int] = mapped_column(
        BigInteger, server_default=str(50 * 1024**3), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_quotas_workspace_user",
            "workspace_id",
            "user_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("max_concurrent_runs >= 0 AND max_queued_runs >= 0", name="runs_nonneg"),
        CheckConstraint(
            "gpu_hours_per_month >= 0 AND storage_bytes >= 0 AND max_upload_bytes >= 0", name="limits_nonneg"
        ),
    )


class UserSecret(TimestampMixin, Base):
    __tablename__ = "user_secrets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[UserSecretKind] = mapped_column(_enum(UserSecretKind, "user_secret_kind"), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # AES-256-GCM
    hint: Mapped[str] = mapped_column(String(16), nullable=False)  # last 4 chars, for UI

    __table_args__ = (UniqueConstraint("user_id", "kind"),)


# --------------------------------------------------------------------------------------------------
# Datasets
# --------------------------------------------------------------------------------------------------
class Dataset(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, server_default="", nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    latest_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL", use_alter=True)
    )

    versions: Mapped[list[DatasetVersion]] = relationship(
        back_populates="dataset", foreign_keys="DatasetVersion.dataset_id", order_by="DatasetVersion.version"
    )

    __table_args__ = (
        Index(
            "uq_datasets_ws_slug_live",
            "workspace_id",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("slug ~ '^[a-z0-9][a-z0-9_.-]{0,99}$'", name="slug_format"),
    )


class DatasetVersion(TimestampMixin, SoftDeleteMixin, Base):
    """Immutable once status=ready. ``content_hash`` = sha256 over the sorted list of
    ``<relative path>\\0<sha256 of file>\\n`` for every file of the unpacked LeRobot dataset."""

    __tablename__ = "dataset_versions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3 ... per dataset
    status: Mapped[DatasetVersionStatus] = mapped_column(
        _enum(DatasetVersionStatus, "dataset_version_status"), server_default="pending", nullable=False
    )
    source: Mapped[DatasetSource] = mapped_column(_enum(DatasetSource, "dataset_source"), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(512))  # upload id | hf://org/repo@rev | merge
    merged_from: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(Uuid))
    content_hash: Mapped[str | None] = mapped_column(String(64))  # set after unpack
    storage_prefix: Mapped[str | None] = mapped_column(String(512))  # s3://hibiscus-datasets/<ws>/<ds>/<ver>/
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    codebase_version: Mapped[str | None] = mapped_column(String(16))  # "v3.0"
    converted_from: Mapped[str | None] = mapped_column(String(16))  # "v2.1" when auto-converted
    robot_type: Mapped[str | None] = mapped_column(String(64))
    fps: Mapped[float | None] = mapped_column(Double)
    total_episodes: Mapped[int | None] = mapped_column(Integer)
    total_frames: Mapped[int | None] = mapped_column(BigInteger)
    camera_keys: Mapped[list[str] | None] = mapped_column(ARRAY(String(128)))
    features: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # meta/info.json "features" verbatim
    info: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # meta/info.json verbatim
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # meta/stats.json (as stored)
    validate_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # schema: openapi ValidationReport
    preview: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # schema: openapi DatasetPreview
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    ready_at: Mapped[datetime | None] = mapped_column()

    dataset: Mapped[Dataset] = relationship(back_populates="versions", foreign_keys=[dataset_id])

    __table_args__ = (
        UniqueConstraint("dataset_id", "version"),
        Index(
            "uq_dataset_versions_content_live",
            "dataset_id",
            "content_hash",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND content_hash IS NOT NULL"),
        ),
        Index(None, "status"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "status <> 'ready' OR (content_hash IS NOT NULL AND storage_prefix IS NOT NULL "
            "AND total_episodes IS NOT NULL AND features IS NOT NULL)",
            name="ready_complete",
        ),
    )


class UploadSession(TimestampMixin, Base):
    """Chunked upload through the API (ADR-10). One S3 multipart upload per session; part N of the
    API == part N of S3. Expires 7 days after the last part (``expires_at`` slides)."""

    __tablename__ = "upload_sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"))
    new_dataset_name: Mapped[str | None] = mapped_column(String(100))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    archive_format: Mapped[ArchiveFormat] = mapped_column(
        _enum(ArchiveFormat, "archive_format"), nullable=False
    )
    total_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    part_size: Mapped[int] = mapped_column(Integer, nullable=False)
    part_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)  # expected whole-file digest (hex)
    s3_bucket: Mapped[str] = mapped_column(String(63), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
    s3_upload_id: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[UploadStatus] = mapped_column(
        _enum(UploadStatus, "upload_status"), server_default="active", nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column()
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL")
    )

    parts: Mapped[list[UploadPart]] = relationship(
        back_populates="upload", order_by="UploadPart.part_number", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(None, "workspace_id", "status"),
        Index(None, "status", "expires_at"),
        CheckConstraint("part_size BETWEEN 5242880 AND 67108864", name="part_size_range"),  # 5 MiB..64 MiB
        CheckConstraint("total_size > 0", name="total_size_positive"),
        CheckConstraint("part_count BETWEEN 1 AND 10000", name="part_count_range"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
        CheckConstraint("(dataset_id IS NULL) <> (new_dataset_name IS NULL)", name="target_exactly_one"),
    )


class UploadPart(TimestampMixin, Base):
    __tablename__ = "upload_parts"

    upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("upload_sessions.id", ondelete="CASCADE"))
    part_number: Mapped[int] = mapped_column(Integer)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    etag: Mapped[str] = mapped_column(String(128), nullable=False)

    upload: Mapped[UploadSession] = relationship(back_populates="parts")

    __table_args__ = (
        PrimaryKeyConstraint("upload_id", "part_number"),
        CheckConstraint("part_number BETWEEN 1 AND 10000", name="part_number_range"),
        CheckConstraint("size > 0 AND size <= 67108864", name="size_range"),
    )


# --------------------------------------------------------------------------------------------------
# GPUs, runs, metrics, checkpoints
# --------------------------------------------------------------------------------------------------
class GpuNode(TimestampMixin, Base):
    """One row per physical GPU (= one worker container, ADR-2). ``id`` is stable: 'cuda0', 'cuda1'."""

    __tablename__ = "gpu_nodes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    host: Mapped[str] = mapped_column(String(64), nullable=False)
    device_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    gpu_uuid: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(64), nullable=False)  # "NVIDIA GeForce RTX 3060"
    total_vram_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    compute_capability: Mapped[str] = mapped_column(String(8), nullable=False)  # "8.6", "6.1"
    supports_bf16: Mapped[bool] = mapped_column(Boolean, nullable=False)
    supports_fast_fp16: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[GpuNodeStatus] = mapped_column(
        _enum(GpuNodeStatus, "gpu_node_status"), server_default="offline", nullable=False
    )
    worker_id: Mapped[str | None] = mapped_column(String(128))  # "<hostname>:<pid>:<boot uuid>"
    worker_version: Mapped[str | None] = mapped_column(String(64))
    image_digest: Mapped[str | None] = mapped_column(String(80))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column()
    current_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL", use_alter=True)
    )

    __table_args__ = (UniqueConstraint("host", "device_index"),)


class Run(TimestampMixin, Base):
    """A training run; also the GPU job queue row (ADR-2). Lifecycle: docs/spec/run-lifecycle.md."""

    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)  # per-workspace, human "#42"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"), nullable=False
    )
    policy_type: Mapped[str] = mapped_column(String(32), nullable=False)
    preset: Mapped[str | None] = mapped_column(String(32))
    # Validated user input: {"policy": {...}, "train": {...}} (api/policy-schemas/*.json).
    config: Mapped[dict[str, Any]] = mapped_column(nullable=False)
    # Effective argv passed to lerobot-train for the current attempt (audit/repro).
    resolved_args: Mapped[list[Any] | None] = mapped_column(JSONB)
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL")
    )  # clone
    init_from_model_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL", use_alter=True)
    )
    init_from_checkpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("checkpoints.id", ondelete="SET NULL", use_alter=True)
    )
    heldout_fraction: Mapped[float] = mapped_column(Double, server_default="0.1", nullable=False)
    heldout_episodes: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    train_episodes: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    current_step: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    # --- scheduling ---
    status: Mapped[RunStatus] = mapped_column(
        _enum(RunStatus, "run_status"), server_default="queued", nullable=False
    )
    status_changed_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))  # catalog: run-lifecycle.md §6
    error_message: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(SmallInteger, server_default="0", nullable=False)  # -10..10
    requested_gpu_id: Mapped[str | None] = mapped_column(
        ForeignKey("gpu_nodes.id", ondelete="SET NULL")
    )  # null=auto
    gpu_node_id: Mapped[str | None] = mapped_column(
        ForeignKey("gpu_nodes.id", ondelete="SET NULL")
    )  # assigned
    required_vram_mb: Mapped[int | None] = mapped_column(Integer)
    mixed_precision_requested: Mapped[MixedPrecision] = mapped_column(
        _enum(MixedPrecision, "mixed_precision_requested"), server_default="no", nullable=False
    )
    mixed_precision_effective: Mapped[MixedPrecision | None] = mapped_column(
        _enum(MixedPrecision, "mixed_precision_effective")
    )
    # run | pause (at next scheduled checkpoint) | pause_now (stop immediately) | cancel
    desired_state: Mapped[str] = mapped_column(String(16), server_default="run", nullable=False)
    last_event_seq: Mapped[int] = mapped_column(BigInteger, server_default="0", nullable=False)
    attempt: Mapped[int] = mapped_column(SmallInteger, server_default="0", nullable=False)
    infra_retries_used: Mapped[int] = mapped_column(SmallInteger, server_default="0", nullable=False)
    resume_checkpoint_step: Mapped[int | None] = mapped_column(Integer)  # set when next attempt resumes
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column()
    heartbeat_at: Mapped[datetime | None] = mapped_column()
    last_log_at: Mapped[datetime | None] = mapped_column()  # hang detection (5 min)
    queued_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()
    gpu_seconds: Mapped[float] = mapped_column(Double, server_default="0", nullable=False)
    # --- outputs ---
    manifest: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # reproducibility manifest (spec)
    log_uri: Mapped[str | None] = mapped_column(String(512))  # s3://hibiscus-artifacts/runs/<id>/train.log
    output_prefix: Mapped[str | None] = mapped_column(String(512))
    latest_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # denormalised for list views
    estimate: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # {vram_mb, sec_per_step, source}
    # ``Idempotency-Key`` of the createRun request (QC-backend-06 / SEC-auth-05): unique per
    # (workspace, creator) while set; cleared when a replay window (24 h) has passed and the key is
    # reused.
    idempotency_key: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("workspace_id", "number"),
        Index(
            "uq_runs_idempotency_key",
            "workspace_id",
            "created_by",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("ix_runs_queue", "priority", "queued_at", postgresql_where=text("status = 'queued'")),
        Index(
            "ix_runs_lease",
            "lease_expires_at",
            postgresql_where=text("status IN ('preparing','running','pausing','exporting','cancelling')"),
        ),
        Index(None, "workspace_id", "created_at"),
        Index(None, "workspace_id", "status"),
        Index(None, "created_by", "status"),
        Index(None, "dataset_version_id"),
        CheckConstraint("priority BETWEEN -10 AND 10", name="priority_range"),
        CheckConstraint("desired_state IN ('run','pause','pause_now','cancel')", name="desired_state_known"),
        CheckConstraint("heldout_fraction >= 0 AND heldout_fraction < 0.5", name="heldout_range"),
        CheckConstraint("total_steps >= 1", name="total_steps_positive"),
        CheckConstraint("current_step >= 0 AND current_step <= total_steps", name="current_step_range"),
        CheckConstraint("infra_retries_used BETWEEN 0 AND 1", name="infra_retry_max_one"),
        CheckConstraint(
            "init_from_model_id IS NULL OR init_from_checkpoint_id IS NULL", name="single_init_source"
        ),
    )


class RunEvent(Base):
    """Append-only event log per run; ``seq`` is the SSE ``id`` (monotonic per run, from 1)."""

    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # SSE event names, openapi RunEvent*
    level: Mapped[str] = mapped_column(String(8), server_default="info", nullable=False)
    attempt: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("run_id", "seq"),
        CheckConstraint("level IN ('debug','info','warning','error')", name="level_known"),
    )


class RunMetric(Base):
    """One scalar per (run, key, step). Keys: log-parsing.md §5. Upsert on conflict (resume replays)."""

    __tablename__ = "run_metrics"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(64))
    step: Mapped[int] = mapped_column(Integer)
    value: Mapped[float] = mapped_column(Double, nullable=False)  # NaN/Inf allowed (PG double)
    ts: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("run_id", "key", "step"),
        Index(None, "run_id", "step"),
        CheckConstraint("key ~ '^[a-z][a-z0-9_]{0,63}$'", name="key_format"),
    )


class GpuTelemetry(Base):
    """NVML sample every 5 s per GPU (kept 30 days)."""

    __tablename__ = "gpu_telemetry"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    gpu_node_id: Mapped[str] = mapped_column(ForeignKey("gpu_nodes.id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    ts: Mapped[datetime] = mapped_column(nullable=False)
    util_pct: Mapped[float] = mapped_column(Double, nullable=False)
    mem_used_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    mem_total_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    temperature_c: Mapped[float] = mapped_column(Double, nullable=False)
    power_w: Mapped[float] = mapped_column(Double, nullable=False)

    __table_args__ = (
        Index(None, "gpu_node_id", "ts"),
        Index(None, "run_id", "ts"),
    )


class Checkpoint(TimestampMixin, Base):
    __tablename__ = "checkpoints"

    id: Mapped[uuid.UUID] = _uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_prefix: Mapped[str] = mapped_column(String(512), nullable=False)  # .../checkpoints/<NNNNNN>/
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    has_training_state: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_last: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    eval_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # schema: bundle.md eval/metrics.json

    __table_args__ = (
        UniqueConstraint("run_id", "step"),
        Index("uq_checkpoints_last", "run_id", unique=True, postgresql_where=text("is_last")),
        CheckConstraint("step >= 1", name="step_positive"),
    )


class Model(TimestampMixin, SoftDeleteMixin, Base):
    """An exported bundle of one checkpoint (docs/spec/bundle.md)."""

    __tablename__ = "models"

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="RESTRICT"), nullable=False)
    checkpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("checkpoints.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)  # <model_name>-<run_no>-step<N>
    policy_type: Mapped[str] = mapped_column(String(32), nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ModelStatus] = mapped_column(
        _enum(ModelStatus, "model_status"), server_default="pending", nullable=False
    )
    bundle_uri: Mapped[str | None] = mapped_column(
        String(512)
    )  # s3://hibiscus-artifacts/models/<id>/bundle.zip
    bundle_sha256: Mapped[str | None] = mapped_column(String(64))
    bundle_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    manifest: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # MANIFEST.json verbatim
    verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    verification: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB
    )  # {load_ok, parity_ok, manifest_ok, ...}
    onnx_status: Mapped[OnnxStatus] = mapped_column(
        _enum(OnnxStatus, "onnx_status"), server_default="pending", nullable=False
    )
    onnx_detail: Mapped[str | None] = mapped_column(Text)
    eval_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    hub_repo_id: Mapped[str | None] = mapped_column(String(200))
    hub_pushed_at: Mapped[datetime | None] = mapped_column()
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        Index(
            "uq_models_checkpoint_live",
            "checkpoint_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(None, "workspace_id", "created_at"),
        Index(None, "run_id"),
        CheckConstraint("NOT verified OR status = 'ready'", name="verified_requires_ready"),
    )


class Job(TimestampMixin, Base):
    """Non-training background jobs (validate, export, eval, import, hub push, estimate).
    Same claim/lease protocol as runs (run-lifecycle.md §7) on table ``jobs``."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[JobKind] = mapped_column(_enum(JobKind, "job_kind"), nullable=False)
    resource: Mapped[JobResource] = mapped_column(_enum(JobResource, "job_resource"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status"), server_default="queued", nullable=False
    )
    priority: Mapped[int] = mapped_column(SmallInteger, server_default="0", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(nullable=False)  # e.g. {"dataset_version_id": ...}
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    progress: Mapped[float] = mapped_column(Double, server_default="0", nullable=False)  # 0..1
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default="0", nullable=False)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, server_default="2", nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE")
    )
    model_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column()
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        Index(
            "ix_jobs_queue", "resource", "priority", "created_at", postgresql_where=text("status = 'queued'")
        ),
        Index(None, "workspace_id", "kind", "created_at"),
        Index(None, "dataset_version_id"),
        Index(None, "model_id"),
        CheckConstraint("progress >= 0 AND progress <= 1", name="progress_range"),
    )


class ResourceEstimate(TimestampMixin, Base):
    """Cache of 20-step dry-run measurements (PLAN §3.3)."""

    __tablename__ = "resource_estimates"

    id: Mapped[uuid.UUID] = _uuid_pk()
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 of canonical key below
    policy_type: Mapped[str] = mapped_column(String(32), nullable=False)
    gpu_name: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mixed_precision: Mapped[MixedPrecision] = mapped_column(
        _enum(MixedPrecision, "mixed_precision"), nullable=False
    )
    image_shapes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)  # [[3,360,640], ...]
    policy_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    peak_vram_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    sec_per_step: Mapped[float] = mapped_column(Double, nullable=False)
    lerobot_version: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (UniqueConstraint("cache_key"),)


# --------------------------------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------------------------------
class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(
        String(48), nullable=False
    )  # e.g. run.succeeded, run.failed, run.stalled
    params: Mapped[dict[str, Any]] = mapped_column(
        server_default=text("'{}'::jsonb"), nullable=False
    )  # i18n params
    link: Mapped[str | None] = mapped_column(String(512))  # SPA path
    read_at: Mapped[datetime | None] = mapped_column()
    # Set by the API dispatcher once the row was fanned out to the user's external channels
    # (``notification_deliveries``). NULL = not yet looked at. Migration 0002 (CR-BE-N1).
    dispatched_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        Index(None, "user_id", "created_at"),
        Index("ix_notifications_unread", "user_id", postgresql_where=text("read_at IS NULL")),
        Index("ix_notifications_undispatched", "created_at", postgresql_where=text("dispatched_at IS NULL")),
    )


class NotificationChannel(TimestampMixin, Base):
    __tablename__ = "notification_channels"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[NotificationChannelKind] = mapped_column(
        _enum(NotificationChannelKind, "notification_channel_kind")
    )
    config_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # webhook URL / chat id, encrypted
    events: Mapped[list[str]] = mapped_column(ARRAY(String(48)), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)

    __table_args__ = (Index(None, "user_id"),)


class NotificationDelivery(TimestampMixin, Base):
    """One notification x one external channel: delivery state, retries with backoff (0002)."""

    __tablename__ = "notification_deliveries"

    id: Mapped[uuid.UUID] = _uuid_pk()
    notification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notification_channels.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), server_default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default="0", nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        UniqueConstraint("notification_id", "channel_id"),
        CheckConstraint("status IN ('pending', 'sent', 'failed')", name="status_valid"),
        Index(None, "channel_id"),
        Index(
            "ix_notification_deliveries_due",
            "next_attempt_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )


__all__ = [name for name in dir() if not name.startswith("_")]
