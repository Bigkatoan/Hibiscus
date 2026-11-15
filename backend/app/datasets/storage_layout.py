"""Object keys (must match worker/validate/store.py; documented in docs/handoff/A3-data.md)."""

from __future__ import annotations

import re
import uuid

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def upload_key(workspace_id: uuid.UUID, upload_id: uuid.UUID, filename: str) -> str:
    """``hibiscus-uploads/<ws>/uploads/<upload_id>/<sanitized filename>``."""
    name = _SAFE_NAME.sub("_", filename.replace("\\", "/").rsplit("/", 1)[-1]).strip("._") or "upload"
    return f"{workspace_id}/uploads/{upload_id}/{name[:200]}"


def dataset_key(workspace_id: uuid.UUID, dataset_id: uuid.UUID, version_id: uuid.UUID, rel: str) -> str:
    """``hibiscus-datasets/<ws>/<ds>/<ver>/<relpath>`` (the LeRobot dataset root, content-hashed)."""
    return f"{workspace_id}/{dataset_id}/{version_id}/{rel}"


def derived_key(workspace_id: uuid.UUID, dataset_id: uuid.UUID, version_id: uuid.UUID, rel: str) -> str:
    """``hibiscus-datasets/<ws>/<ds>/<ver>.derived/<relpath>`` (previews, episode series, manifest)."""
    return f"{workspace_id}/{dataset_id}/{version_id}.derived/{rel}"


def manifest_key(workspace_id: uuid.UUID, dataset_id: uuid.UUID, version_id: uuid.UUID) -> str:
    return derived_key(workspace_id, dataset_id, version_id, "manifest.json")
