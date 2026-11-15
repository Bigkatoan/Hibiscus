"""Request bodies (pydantic v2, unknown fields rejected) - OpenAPI components of the same name."""

from __future__ import annotations

import re
import uuid
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.db.models import ArchiveFormat

MIB = 1024 * 1024
MIN_PART = 5 * MIB
MAX_PART = 64 * MIB
MAX_UPLOAD = 10000 * MAX_PART  # 625 GiB hard cap

ResourceName = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f]+$")]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
HF_URI_RE = re.compile(
    r"^hf://[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}(@[A-Za-z0-9_./-]{1,128})?$"
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Target(_Strict):
    """Exactly one of ``dataset_id`` / ``new_dataset_name``."""

    workspace_id: uuid.UUID
    dataset_id: uuid.UUID | None = None
    new_dataset_name: ResourceName | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.dataset_id is None) == (self.new_dataset_name is None):
            raise ValueError("exactly one of dataset_id / new_dataset_name is required")
        return self


class DatasetCreate(_Strict):
    workspace_id: uuid.UUID
    name: ResourceName
    description: Annotated[str, StringConstraints(max_length=2000)] = ""


class DatasetUpdate(_Strict):
    name: ResourceName | None = None
    description: Annotated[str, StringConstraints(max_length=2000)] | None = None

    @model_validator(mode="after")
    def _non_empty(self) -> Self:
        if self.name is None and self.description is None:
            raise ValueError("at least one property is required")
        return self


class UploadInit(_Target):
    filename: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    size: Annotated[int, Field(ge=1, le=MAX_UPLOAD)]
    sha256: Sha256Hex
    archive_format: ArchiveFormat | None = None
    part_size: Annotated[int, Field(ge=MIN_PART, le=MAX_PART)] = MAX_PART


class HfImportRequest(_Target):
    hf_uri: Annotated[str, StringConstraints(max_length=300)]


class MergeRequest(_Target):
    source_version_ids: Annotated[list[uuid.UUID], Field(min_length=2, max_length=20)]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        if len(set(self.source_version_ids)) != len(self.source_version_ids):
            raise ValueError("source_version_ids must be unique")
        return self
