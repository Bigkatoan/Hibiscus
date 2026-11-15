"""CPU worker settings (env). Local adapter until A4's ``worker/core`` settings are merged.

Variable names follow the ``HIBISCUS_`` convention of the backend settings.
"""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from validate.archive import UnpackLimits


def _env(name: str, default: str | None = None, *aliases: str) -> str:
    """First set variable of ``name`` + ``aliases`` (QC-e2e-03: compose and the apps disagreed
    on the S3 credential names; both spellings are accepted, the first one is canonical)."""
    for n in (name, *aliases):
        v = os.environ.get(n)
        if v is not None and v != "":
            return v
    if default is None:
        raise RuntimeError(f"missing environment variable {name}")
    return default


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    database_url: str  # SQLAlchemy URL, e.g. postgresql+psycopg://hibiscus:...@postgres:5432/hibiscus
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_region: str = "us-east-1"
    bucket_uploads: str = "hibiscus-uploads"
    bucket_datasets: str = "hibiscus-datasets"
    redis_url: str | None = None
    work_dir: Path = Path("/scratch/validate")
    hf_home: Path = Path("/cache/hf")
    worker_id: str = field(
        default_factory=lambda: f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    )
    poll_interval_s: float = 2.0
    lease_s: int = 60
    heartbeat_s: float = 10.0
    limits: UnpackLimits = field(default_factory=UnpackLimits)
    data_key_b64: str | None = None  # HIBISCUS_DATA_KEY, to decrypt the user's HF token
    #: Liveness file of the image HEALTHCHECK (QC-e2e-08); touched by the loop and job heartbeats.
    heartbeat_file: Path | None = None
    #: SEC-input-3: absolute cap on one HF import (on top of the workspace storage quota).
    hf_import_max_bytes: int = 200 * 1024**3
    bucket_artifacts: str = "hibiscus-artifacts"
    #: Port of the Prometheus ``/metrics`` endpoint (``core.metrics``); 0 disables it.
    metrics_port: int = 9108

    @classmethod
    def from_env(cls) -> WorkerSettings:
        hb = os.environ.get("HIBISCUS_WORKER_HEARTBEAT_FILE")
        return cls(
            database_url=_env("HIBISCUS_DATABASE_URL"),
            s3_endpoint_url=_env("HIBISCUS_S3_ENDPOINT_URL"),
            s3_access_key=_env("HIBISCUS_S3_ACCESS_KEY"),
            s3_secret_key=_env("HIBISCUS_S3_SECRET_KEY"),
            s3_region=_env("HIBISCUS_S3_REGION", "us-east-1"),
            bucket_uploads=_env("HIBISCUS_S3_BUCKET_UPLOADS", "hibiscus-uploads"),
            bucket_datasets=_env("HIBISCUS_S3_BUCKET_DATASETS", "hibiscus-datasets"),
            bucket_artifacts=_env("HIBISCUS_S3_BUCKET_ARTIFACTS", "hibiscus-artifacts"),
            redis_url=os.environ.get("HIBISCUS_REDIS_URL"),
            work_dir=Path(_env("HIBISCUS_VALIDATE_WORK_DIR", "/scratch/validate")),
            hf_home=Path(_env("HF_HOME", "/cache/hf")),
            lease_s=int(_env("HIBISCUS_WORKER_LEASE_TTL_SECONDS", "60")),
            heartbeat_s=float(_env("HIBISCUS_WORKER_HEARTBEAT_SECONDS", "10")),
            heartbeat_file=Path(hb) if hb else None,
            hf_import_max_bytes=int(_env("HIBISCUS_HF_IMPORT_MAX_BYTES", str(200 * 1024**3))),
            limits=UnpackLimits(
                max_total_bytes=int(_env("HIBISCUS_UNPACK_MAX_TOTAL_BYTES", str(200 * 1024**3))),
                max_file_bytes=int(_env("HIBISCUS_UNPACK_MAX_FILE_BYTES", str(64 * 1024**3))),
                max_entries=int(_env("HIBISCUS_UNPACK_MAX_ENTRIES", "200000")),
                max_ratio=float(_env("HIBISCUS_UNPACK_MAX_RATIO", "100")),
            ),
            data_key_b64=os.environ.get("HIBISCUS_DATA_KEY"),
            metrics_port=int(_env("HIBISCUS_METRICS_PORT", "9108")),
        )
