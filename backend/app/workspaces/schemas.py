"""Workspace request bodies (api/openapi.yaml)."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from app.db.models import WorkspaceRole

ResourceName = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f]+$")]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$")]
NotifyEvent = Literal[
    "run.succeeded", "run.failed", "run.stalled", "model.ready", "dataset.ready", "dataset.invalid"
]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkspaceSettings(_Body):
    default_heldout_fraction: Annotated[float, Field(ge=0, le=0.49)] = 0.1
    default_gpu: Annotated[str, StringConstraints(pattern=r"^(auto|[a-z0-9_-]{1,32})$")] = "auto"
    notify_on: list[NotifyEvent] = Field(default_factory=list)


class WorkspaceCreate(_Body):
    name: ResourceName
    slug: Slug


class WorkspaceUpdate(_Body):
    name: ResourceName | None = None
    settings: WorkspaceSettings | None = None

    @model_validator(mode="after")
    def _non_empty(self) -> WorkspaceUpdate:
        if not self.model_fields_set or all(getattr(self, f) is None for f in self.model_fields_set):
            raise ValueError("at least one property is required")
        return self


class MemberRoleUpdate(_Body):
    role: WorkspaceRole


class InviteCreate(_Body):
    email: Annotated[EmailStr, StringConstraints(max_length=320)]
    role: Literal["admin", "member", "viewer"]


class QuotaUpsert(_Body):
    user_id: uuid.UUID | None
    max_concurrent_runs: Annotated[int, Field(ge=0, le=32767)]
    max_queued_runs: Annotated[int, Field(ge=0, le=32767)]
    gpu_hours_per_month: Annotated[float, Field(ge=0)]
    storage_bytes: Annotated[int, Field(ge=0)]
    max_upload_bytes: Annotated[int, Field(ge=0)]
