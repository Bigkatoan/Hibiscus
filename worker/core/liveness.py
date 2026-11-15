"""Liveness file for the worker image's Docker HEALTHCHECK (QC-e2e-08).

deploy/docker/worker.Dockerfile sets ``HIBISCUS_WORKER_HEARTBEAT_FILE=/tmp/hibiscus-worker.alive``
and the HEALTHCHECK passes while that file was modified within the last 2 minutes. Workers call
:func:`touch` from their main loop and after every successful lease / job heartbeat, so a busy
worker (training, exporting, validating) stays healthy and a wedged one goes unhealthy.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)
ENV_NAME = "HIBISCUS_WORKER_HEARTBEAT_FILE"


def heartbeat_path(configured: Path | str | None = None) -> Path | None:
    value = configured if configured is not None else os.environ.get(ENV_NAME)
    return Path(value) if value else None


def touch(path: Path | str | None) -> None:
    """Create or refresh ``path``; never raises (liveness must not break the worker)."""
    if not path:
        return
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
        os.utime(p, None)
    except OSError as exc:
        log.warning("cannot touch heartbeat file %s: %s", path, exc)
