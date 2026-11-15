"""SQLAlchemy Core mirror of the frozen tables the workers touch (``backend/app/db/models.py``).

The worker image does not ship the API package, so this module declares *only* the columns the
workers read or write. ``core/tests/test_tables_drift.py`` asserts that every column declared here
exists in the contract models with the same SQL type family, so drift is caught in CI.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Double,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

metadata = MetaData()

TS = DateTime(timezone=True)

runs = Table(
    "runs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("workspace_id", Uuid),
    Column("number", Integer),
    Column("name", String(100)),
    Column("created_by", Uuid),
    Column("dataset_version_id", Uuid),
    Column("policy_type", String(32)),
    Column("config", JSONB),
    Column("resolved_args", JSONB),
    Column("init_from_model_id", Uuid),
    Column("init_from_checkpoint_id", Uuid),
    Column("heldout_episodes", ARRAY(Integer)),
    Column("train_episodes", ARRAY(Integer)),
    Column("seed", BigInteger),
    Column("total_steps", Integer),
    Column("current_step", Integer),
    Column("status", String(32)),
    Column("status_changed_at", TS),
    Column("error_code", String(64)),
    Column("error_message", Text),
    Column("priority", SmallInteger),
    Column("requested_gpu_id", String(32)),
    Column("gpu_node_id", String(32)),
    Column("required_vram_mb", Integer),
    Column("mixed_precision_requested", String(32)),
    Column("mixed_precision_effective", String(32)),
    Column("desired_state", String(16)),
    Column("last_event_seq", BigInteger),
    Column("attempt", SmallInteger),
    Column("infra_retries_used", SmallInteger),
    Column("resume_checkpoint_step", Integer),
    Column("lease_owner", String(128)),
    Column("lease_expires_at", TS),
    Column("heartbeat_at", TS),
    Column("last_log_at", TS),
    Column("queued_at", TS),
    Column("started_at", TS),
    Column("finished_at", TS),
    Column("gpu_seconds", Double),
    Column("manifest", JSONB),
    Column("log_uri", String(512)),
    Column("output_prefix", String(512)),
    Column("latest_metrics", JSONB),
    Column("estimate", JSONB),
    Column("updated_at", TS),
)

run_events = Table(
    "run_events",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("run_id", Uuid),
    Column("seq", BigInteger),
    Column("type", String(32)),
    Column("level", String(8)),
    Column("attempt", SmallInteger),
    Column("data", JSONB),
    Column("created_at", TS),
)

run_metrics = Table(
    "run_metrics",
    metadata,
    Column("run_id", Uuid, primary_key=True),
    Column("key", String(64), primary_key=True),
    Column("step", Integer, primary_key=True),
    Column("value", Double),
    Column("ts", TS),
    Column("updated_at", TS),
)

gpu_nodes = Table(
    "gpu_nodes",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("host", String(64)),
    Column("device_index", SmallInteger),
    Column("gpu_uuid", String(64)),
    Column("name", String(64)),
    Column("total_vram_mb", Integer),
    Column("compute_capability", String(8)),
    Column("supports_bf16", Boolean),
    Column("supports_fast_fp16", Boolean),
    Column("status", String(32)),
    Column("worker_id", String(128)),
    Column("worker_version", String(64)),
    Column("image_digest", String(80)),
    Column("last_heartbeat_at", TS),
    Column("current_run_id", Uuid),
    Column("updated_at", TS),
)

gpu_telemetry = Table(
    "gpu_telemetry",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("gpu_node_id", String(32)),
    Column("run_id", Uuid),
    Column("ts", TS),
    Column("util_pct", Double),
    Column("mem_used_mb", Integer),
    Column("mem_total_mb", Integer),
    Column("temperature_c", Double),
    Column("power_w", Double),
)

checkpoints = Table(
    "checkpoints",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("run_id", Uuid),
    Column("step", Integer),
    Column("storage_prefix", String(512)),
    Column("size_bytes", BigInteger),
    Column("has_training_state", Boolean),
    Column("is_last", Boolean),
    Column("eval_metrics", JSONB),
    Column("created_at", TS),
    Column("updated_at", TS),
)

dataset_versions = Table(
    "dataset_versions",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("dataset_id", Uuid),
    Column("version", Integer),
    Column("status", String(32)),
    Column("content_hash", String(64)),
    Column("storage_prefix", String(512)),
    Column("size_bytes", BigInteger),
    Column("features", JSONB),
    Column("camera_keys", ARRAY(String(128))),
    Column("total_episodes", Integer),
)

datasets = Table(
    "datasets",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("workspace_id", Uuid),
    Column("slug", String(100)),
    Column("name", String(100)),
)

models = Table(
    "models",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("workspace_id", Uuid),
    Column("run_id", Uuid),
    Column("checkpoint_id", Uuid),
    Column("name", String(160)),
    Column("policy_type", String(32)),
    Column("step", Integer),
    Column("status", String(32)),
    Column("bundle_uri", String(512)),
    Column("bundle_sha256", String(64)),
    Column("bundle_size_bytes", BigInteger),
    Column("manifest", JSONB),
    Column("verified", Boolean),
    Column("verification", JSONB),
    Column("onnx_status", String(32)),
    Column("onnx_detail", Text),
    Column("eval_metrics", JSONB),
    Column("hub_repo_id", String(200)),
    Column("hub_pushed_at", TS),
    Column("created_by", Uuid),
    Column("updated_at", TS),
    Column("deleted_at", TS),
)

jobs = Table(
    "jobs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("workspace_id", Uuid),
    Column("kind", String(32)),
    Column("resource", String(32)),
    Column("status", String(32)),
    Column("priority", SmallInteger),
    Column("payload", JSONB),
    Column("result", JSONB),
    Column("progress", Double),
    Column("error_code", String(64)),
    Column("error_message", Text),
    Column("attempts", SmallInteger),
    Column("max_attempts", SmallInteger),
    Column("run_id", Uuid),
    Column("dataset_version_id", Uuid),
    Column("model_id", Uuid),
    Column("created_by", Uuid),
    Column("lease_owner", String(128)),
    Column("lease_expires_at", TS),
    Column("started_at", TS),
    Column("finished_at", TS),
    Column("created_at", TS),
    Column("updated_at", TS),
)

quotas = Table(
    "quotas",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("workspace_id", Uuid),
    Column("user_id", Uuid),
    Column("max_concurrent_runs", SmallInteger),
    Column("max_queued_runs", SmallInteger),
    Column("gpu_hours_per_month", Double),
)

resource_estimates = Table(
    "resource_estimates",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("cache_key", String(64)),
    Column("policy_type", String(32)),
    Column("gpu_name", String(64)),
    Column("batch_size", Integer),
    Column("mixed_precision", String(32)),
    Column("image_shapes", JSONB),
    Column("policy_config_hash", String(64)),
    Column("peak_vram_mb", Integer),
    Column("sec_per_step", Double),
    Column("lerobot_version", String(16)),
    Column("updated_at", TS),
)

notifications = Table(
    "notifications",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid),
    Column("workspace_id", Uuid),
    Column("kind", String(48)),
    Column("params", JSONB),
    Column("link", String(512)),
)
