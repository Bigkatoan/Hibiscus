"""Worker configuration (env vars prefixed ``HIBISCUS_``), shared by every worker package.

Public API (stable for A3/A5): :class:`WorkerSettings`, :func:`get_settings`.

Canonical environment variable names (QC-e2e-09). The first name of each item is canonical and
is what deploy/docker-compose.yml should set; the names after "also" are accepted too (compose
already sets some of them):

* ``gpu_index`` (host GPU index): ``HIBISCUS_GPU_INDEX``; also ``HIBISCUS_GPU_DEVICE_INDEX``
* ``gpu_node_id`` (``gpu_nodes.id``): ``HIBISCUS_GPU_NODE_ID``; default ``cuda<gpu_index>``
* ``nvml_index`` (index inside the container): ``HIBISCUS_NVML_INDEX``; default: ``gpu_index``,
  or 0 when NVML sees a single device
* ``s3_access_key``: ``HIBISCUS_S3_ACCESS_KEY``
* ``s3_secret_key``: ``HIBISCUS_S3_SECRET_KEY``
* ``bucket_<name>``: ``HIBISCUS_S3_BUCKET_<NAME>``; also ``HIBISCUS_BUCKET_<NAME>``
* ``heartbeat_interval_s``: ``HIBISCUS_WORKER_HEARTBEAT_SECONDS``; also ``HIBISCUS_HEARTBEAT_INTERVAL_S``
* ``lease_ttl_s``: ``HIBISCUS_WORKER_LEASE_TTL_SECONDS``; also ``HIBISCUS_LEASE_TTL_S``
* ``dataset_cache_max_bytes``: ``HIBISCUS_DATASET_CACHE_MAX_GB`` (GiB); also
  ``HIBISCUS_DATASET_CACHE_MAX_BYTES``
* ``worker_version``: ``HIBISCUS_VERSION``; also ``HIBISCUS_WORKER_VERSION``
* ``heartbeat_file``: ``HIBISCUS_WORKER_HEARTBEAT_FILE`` (set by deploy/docker/worker.Dockerfile)

Every other setting is ``HIBISCUS_<FIELD_NAME>`` (upper case).

In compose, ``worker-cuda1`` (P40) exposes only host GPU 1 to the container
(``device_ids: ["1"]``), so it needs ``HIBISCUS_GPU_INDEX=1`` (or ``HIBISCUS_GPU_DEVICE_INDEX=1``),
which gives the id ``cuda1``. NVML then sees a single device at index 0. When
``HIBISCUS_NVML_INDEX`` is unset and NVML reports exactly one device, the worker opens index 0.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env(*names: str) -> AliasChoices:
    return AliasChoices(*names)


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HIBISCUS_", extra="ignore", populate_by_name=True)

    # --- connections ---------------------------------------------------------------------------
    #: SQLAlchemy URL, sync psycopg 3 driver, e.g. ``postgresql+psycopg://hibiscus:...@postgres/hibiscus``.
    database_url: str = "postgresql+psycopg://hibiscus:hibiscus@postgres:5432/hibiscus"
    redis_url: str = "redis://redis:6379/0"
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = Field(
        default="",
        validation_alias=_env("HIBISCUS_S3_ACCESS_KEY"),
    )
    s3_secret_key: str = Field(
        default="",
        validation_alias=_env("HIBISCUS_S3_SECRET_KEY"),
    )
    s3_region: str = "us-east-1"
    bucket_datasets: str = Field(
        default="hibiscus-datasets",
        validation_alias=_env("HIBISCUS_S3_BUCKET_DATASETS", "HIBISCUS_BUCKET_DATASETS"),
    )
    bucket_artifacts: str = Field(
        default="hibiscus-artifacts",
        validation_alias=_env("HIBISCUS_S3_BUCKET_ARTIFACTS", "HIBISCUS_BUCKET_ARTIFACTS"),
    )
    bucket_uploads: str = Field(
        default="hibiscus-uploads",
        validation_alias=_env("HIBISCUS_S3_BUCKET_UPLOADS", "HIBISCUS_BUCKET_UPLOADS"),
    )

    # --- this worker ---------------------------------------------------------------------------
    #: Physical GPU index on the host (compose ``device_ids``); also the NVML index inside the
    #: container unless :attr:`nvml_index` is set (or NVML sees only one device, see module doc).
    gpu_index: int = Field(
        default=0, validation_alias=_env("HIBISCUS_GPU_INDEX", "HIBISCUS_GPU_DEVICE_INDEX")
    )
    #: ``gpu_nodes.id`` of this worker. Default ``cuda<gpu_index>``.
    gpu_node_id: str | None = Field(default=None, validation_alias=_env("HIBISCUS_GPU_NODE_ID"))
    #: NVML index inside the container (``CUDA_VISIBLE_DEVICES`` remaps to 0 in compose).
    nvml_index: int | None = None
    host_name: str | None = None
    worker_version: str = Field(
        default="0.1.1", validation_alias=_env("HIBISCUS_VERSION", "HIBISCUS_WORKER_VERSION")
    )
    image_digest: str | None = None
    #: Liveness file the image's HEALTHCHECK checks (``find -mmin -2``); touched by the main loop
    #: and by every successful lease/job heartbeat (QC-e2e-08). ``None`` = no file.
    heartbeat_file: Path | None = Field(default=None, validation_alias=_env("HIBISCUS_WORKER_HEARTBEAT_FILE"))

    #: Port of the Prometheus ``/metrics`` endpoint (``core.metrics``); 0 disables it.
    metrics_port: int = 9108

    # --- filesystem (run-lifecycle §10) ---------------------------------------------------------
    scratch_dir: Path = Path("/scratch")
    cache_dir: Path = Path("/cache")
    dataset_cache_max_bytes: int = 150 * 1024**3
    dataset_cache_max_gb: float | None = None

    # --- training process -------------------------------------------------------------------------
    #: argv[0] of the training command. In the worker image it is on PATH.
    lerobot_train_bin: str = "lerobot-train"
    #: Optional CUDA_VISIBLE_DEVICES for the child (None => inherit; compose already remaps).
    child_cuda_visible_devices: str | None = None
    max_num_workers: int = 4
    #: Extra env-var name prefixes passed to child processes on top of the allow-list in
    #: ``core.child_env`` (SEC-input-2). Never used for secrets; tests pass ``["FAKE_"]``.
    child_env_passthrough: list[str] = Field(default_factory=list)
    #: Hard cap on the files fetched for ``init_from.hf_repo_id`` (SEC-input-1).
    init_from_max_bytes: int = 20 * 1024**3

    # --- timing (seconds) -------------------------------------------------------------------------
    poll_interval_s: float = 2.0
    heartbeat_interval_s: float = Field(
        default=10.0,
        validation_alias=_env("HIBISCUS_WORKER_HEARTBEAT_SECONDS", "HIBISCUS_HEARTBEAT_INTERVAL_S"),
    )
    lease_ttl_s: int = Field(
        default=60,
        validation_alias=_env("HIBISCUS_WORKER_LEASE_TTL_SECONDS", "HIBISCUS_LEASE_TTL_S"),
    )
    telemetry_interval_s: float = 5.0
    log_upload_interval_s: float = 30.0
    log_silent_warn_s: float = 300.0
    log_silent_kill_s: float = 900.0
    checkpoint_complete_timeout_s: float = 600.0
    kill_grace_s: float = 30.0
    db_retry_budget_s: float = 50.0
    progress_throttle_s: float = 1.0
    log_batch_interval_s: float = 0.5
    gpu_job_max_wait_s: float = 300.0
    #: How often a running attempt re-checks the monthly GPU-hour quota (run-lifecycle §6).
    quota_check_interval_s: float = 60.0

    # --- export ------------------------------------------------------------------------------------
    #: Interpreter for the bundle load check. ``None`` = the worker's own Python, with the
    #: optional extras LeLab's base install lacks blocked (see ``export.load_check``).
    export_load_check_python: str | None = None

    #: Skip NVML entirely (tests on machines without a GPU); the fake_gpu_* values are then used.
    disable_nvml: bool = False
    fake_gpu_name: str = "Fake GPU"
    fake_gpu_vram_mb: int = 12288
    fake_gpu_cc: str = "8.6"
    s3_max_retries: int = Field(default=5, ge=1)

    def model_post_init(self, __context: Any) -> None:
        if self.dataset_cache_max_gb is not None:
            self.dataset_cache_max_bytes = int(self.dataset_cache_max_gb * 1024**3)

    @property
    def gpu_id(self) -> str:
        return self.gpu_node_id or f"cuda{self.gpu_index}"

    @property
    def nvml_device_index(self) -> int:
        return self.gpu_index if self.nvml_index is None else self.nvml_index


@lru_cache(maxsize=1)
def get_settings() -> WorkerSettings:
    return WorkerSettings()
