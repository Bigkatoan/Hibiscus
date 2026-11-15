"""Input / output types of the export pipeline (the API surface A4's worker calls)."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from export.logs import MetricRow

ManifestOnnxStatus = Literal["not_supported", "passed", "failed", "skipped"]
MixedPrecision = Literal["no", "fp16", "bf16"]
_NAME_RE = re.compile(r"[^a-z0-9_-]+")


class ExportOptions(BaseModel):
    """Mirror of OpenAPI ``components.schemas.ExportOptions``."""

    model_config = ConfigDict(extra="forbid")

    onnx: bool = True
    onnx_fp16: bool = False
    eval: bool = True
    model_name: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class RunInfo:
    id: str  # uuid
    number: int
    name: str
    workspace_id: str  # uuid


@dataclass(frozen=True)
class DatasetInfo:
    """Dataset version the run trained on. ``root`` = local LeRobot v3 directory (worker cache)."""

    dataset_id: str
    version_id: str
    version: int
    name: str
    content_hash: str  # sha256 hex
    repo_id: str
    root: Path


@dataclass(frozen=True)
class TrainingInfo:
    seed: int
    total_steps: int
    batch_size: int
    mixed_precision: MixedPrecision
    gpu_name: str
    heldout_episodes: list[int]
    train_episodes: list[int]
    gpu_seconds: float
    final_loss: float | None = None


@dataclass
class BundleRequest:
    """Everything :func:`export.bundle.build_bundle` needs. All paths are local to the worker."""

    model_id: str
    run: RunInfo
    dataset: DatasetInfo
    training: TrainingInfo
    pretrained_dir: Path  # checkpoints/<NNNNNN>/pretrained_model (copied byte-identical)
    checkpoint_step: int
    work_dir: Path  # bundle dir and zip are created here
    options: ExportOptions = field(default_factory=ExportOptions)
    train_logs: list[Path] = field(default_factory=list)  # one file per attempt, in order
    metrics: list[MetricRow] = field(default_factory=list)
    image_digest: str = "sha256:" + "0" * 64
    hibiscus_version: str = "0.1.0"
    eval_device: str = "cpu"  # e.g. "cuda:0" on a GPU worker; parity always runs on CPU
    load_check_python: str | None = None  # interpreter for the fresh-process load check
    #: Raises (``core.export_api.ExportAbortedError``) when the export must stop; called between stages.
    abort_check: Callable[[], None] | None = None
    parity_samples: int = 32
    created_at: datetime | None = None


@dataclass
class Verification:
    """OpenAPI ``components.schemas.Verification`` (models.verification)."""

    load_ok: bool
    parity_ok: bool | None
    manifest_ok: bool
    checked_at: str
    parity: dict[str, Any] | None = None
    details: str | None = None
    #: QC-ml-1: loads in the LeLab venv without extra packages (``None`` = not checked).
    lelab_compatible: bool | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "load_ok": self.load_ok,
            "lelab_compatible": self.lelab_compatible,
            "parity_ok": self.parity_ok,
            "manifest_ok": self.manifest_ok,
            "parity": self.parity,
            "checked_at": self.checked_at,
            "details": self.details,
        }


@dataclass
class BundleResult:
    bundle_name: str
    bundle_dir: Path
    zip_path: Path
    zip_sha256: str
    zip_size: int
    manifest: dict[str, Any]
    onnx_status: ManifestOnnxStatus  # MANIFEST value; see api_onnx_status for the DB/API enum
    onnx_detail: str | None
    verification: Verification
    verified: bool
    eval_metrics: dict[str, Any] | None
    parity_report: dict[str, Any] | None
    timings: dict[str, float] = field(default_factory=dict)

    @property
    def api_onnx_status(self) -> str:
        """OpenAPI ``OnnxStatus`` has no ``skipped``; CR-A5-1 proposes adding it (fallback: not_supported)."""
        return "not_supported" if self.onnx_status == "skipped" else self.onnx_status

    @property
    def eval_summary(self) -> dict[str, float] | None:
        if not self.eval_metrics:
            return None
        o = self.eval_metrics["overall"]
        return {"action_mae": float(o["mae"]), "action_mse": float(o["mse"])}


def default_model_name(dataset_name: str, policy_type: str) -> str:
    """``<dataset_slug>_<policy_type>`` lower-case ``[a-z0-9_-]``, ≤ 64 chars (spec §1)."""
    slug = _NAME_RE.sub("_", dataset_name.lower()).strip("_-") or "model"
    suffix = f"_{policy_type}"
    slug = slug[: 64 - len(suffix)].rstrip("_-") or "model"
    if not slug[0].isalnum():
        slug = "m" + slug[1:]
    return f"{slug}{suffix}"


def bundle_name(model_name: str, run_number: int, step: int) -> str:
    return f"{model_name}-r{int(run_number)}-step{int(step)}"


def is_verified(
    *, load_ok: bool, manifest_ok: bool, parity_ok: bool | None, onnx_support: str, onnx_requested: bool
) -> bool:
    """docs/spec/bundle.md §10.

    ``load_ok ∧ manifest_ok ∧ (parity_ok if onnx_support ≠ none and ONNX was requested)``.
    """
    if not (load_ok and manifest_ok):
        return False
    if onnx_support != "none" and onnx_requested:
        return parity_ok is True
    return True
