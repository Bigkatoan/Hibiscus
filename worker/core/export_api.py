"""Hook interface between the train worker (A4) and the export pipeline (A5, ``worker/export``).

After ``lerobot-train`` exits 0 and the final checkpoint is uploaded, the train worker (same
lease, same GPU, status ``exporting``) creates the ``models`` row (``status=building``) and calls::

    export.pipeline.run_export(ctx: ExportContext) -> ExportOutcome

if the module ``export.pipeline`` defines ``run_export``. The exporter owns everything about the
bundle (eval, ONNX, parity, verification, zip upload, filling ``models`` columns). It must not
change ``runs.status``; the train worker applies run-lifecycle §5 from the returned outcome:

* ``ExportOutcome.infra_error = True``  -> §6 retry rules (re-runs only the export).
* otherwise                             -> run ``succeeded`` (model ready or failed, D3).

The train worker keeps the run lease alive in a background thread for the whole export
(QC-backend-01). The exporter calls ``ctx.check_abort()`` between its stages; it raises
:class:`ExportAbortedError` once the run was cancelled, the lease was lost or the worker is shutting
down (QC-backend-05), and the train worker then applies T11 (``cancelling -> cancelled``).

When ``export.pipeline`` is missing (A5 not merged yet) the worker marks the model ``failed`` with
``onnx_detail='exporter not installed'`` and the run still succeeds.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import Engine

from core.bus import Bus
from core.s3 import ObjectStore
from core.settings import WorkerSettings


class ExportAbortedError(Exception):
    """The export was stopped on request (cancel / lost lease / shutdown); nothing was published."""


@dataclass(slots=True)
class ExportContext:
    run_id: uuid.UUID
    workspace_id: uuid.UUID
    run_number: int
    model_id: uuid.UUID
    checkpoint_id: uuid.UUID
    step: int
    policy_type: str
    #: Local ``.../checkpoints/<NNNNNN>/pretrained_model`` directory of the final checkpoint.
    pretrained_model_dir: Path
    #: Local LeRobot dataset root (``/cache/datasets/<version_id>``).
    dataset_root: Path
    dataset_repo_id: str
    heldout_episodes: list[int]
    train_episodes: list[int]
    #: ``RunCreate.export`` (ExportOptions) with defaults applied.
    options: dict[str, Any]
    #: ``runs.manifest`` (RunManifest) - embed in MANIFEST.json.
    run_manifest: dict[str, Any]
    #: Directory under ``/scratch/exports/<model_id>`` reserved for the bundle build.
    work_dir: Path
    #: Raw log of the attempts (for ``logs/train.log``).
    log_files: list[Path] = field(default_factory=list)
    model_name: str = ""
    #: ``() -> True`` once the export must stop (run cancelled, lease lost, worker shutdown).
    should_abort: Callable[[], bool] | None = None
    #: Interpreter for the bundle load check (``None`` = worker Python with LeLab extras blocked).
    load_check_python: str | None = None

    def check_abort(self) -> None:
        if self.should_abort is not None and self.should_abort():
            raise ExportAbortedError("export aborted")


@dataclass(slots=True)
class ExportOutcome:
    model_status: str  # "ready" | "failed"
    verified: bool = False
    onnx_status: str = "not_supported"
    error_message: str | None = None
    infra_error: bool = False


class ExportFn(Protocol):
    def __call__(
        self,
        ctx: ExportContext,
        *,
        engine: Engine,
        store: ObjectStore,
        bus: Bus | None,
        settings: WorkerSettings,
    ) -> ExportOutcome: ...
