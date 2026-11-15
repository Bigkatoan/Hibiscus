"""Request bodies (pydantic v2, ``extra='forbid'``) mirroring api/openapi.yaml components.

Responses are built as plain dicts by ``app.runs.serialize`` and validated against the OpenAPI
document in tests (``tests/runs/openapi_check.py``).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

PolicyType = Literal["act", "diffusion", "vqbet", "tdmpc", "smolvla", "pi0", "pi05"]
ResourceName = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f]+$")]
HF_REPO = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunConfig(_Strict):
    policy: dict[str, Any] = Field(default_factory=dict)
    train: dict[str, Any] = Field(default_factory=dict)


class InitFrom(_Strict):
    model_id: uuid.UUID | None = None
    checkpoint_id: uuid.UUID | None = None
    hf_repo_id: Annotated[str, StringConstraints(pattern=HF_REPO)] | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> InitFrom:
        n = sum(x is not None for x in (self.model_id, self.checkpoint_id, self.hf_repo_id))
        if n != 1:
            raise ValueError("exactly one of model_id, checkpoint_id, hf_repo_id is required")
        return self


class ExportOptions(_Strict):
    onnx: bool = True
    onnx_fp16: bool = False
    eval: bool = True
    model_name: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")] | None = None


class RunCreate(_Strict):
    workspace_id: uuid.UUID
    name: ResourceName | None = None
    dataset_version_id: uuid.UUID
    policy_type: PolicyType
    preset: Literal["quick", "standard", "finetune"] | None = None
    config: RunConfig
    heldout_fraction: Annotated[float, Field(ge=0, le=0.49)] = 0.1
    heldout_episodes: list[Annotated[int, Field(ge=0)]] | None = None
    gpu: Annotated[str, StringConstraints(max_length=32)] = "auto"
    priority: Annotated[int, Field(ge=-10, le=10)] = 0
    init_from: InitFrom | None = None
    export: ExportOptions | None = None
    seed: Annotated[int, Field(ge=0, le=4294967295)] | None = None


class RunUpdate(_Strict):
    name: ResourceName | None = None
    priority: Annotated[int, Field(ge=-10, le=10)] | None = None
    gpu: Annotated[str, StringConstraints(max_length=32)] | None = None

    @model_validator(mode="after")
    def _min_one(self) -> RunUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one property is required")
        return self


class RunPauseRequest(_Strict):
    mode: Literal["next_checkpoint", "now"] = "next_checkpoint"


class RunResumeRequest(_Strict):
    gpu: Annotated[str, StringConstraints(max_length=32)] | None = None
    total_steps: Annotated[int, Field(ge=1)] | None = None


class RunCloneRequest(_Strict):
    name: ResourceName | None = None
    dataset_version_id: uuid.UUID | None = None
    config: dict[str, Any] | None = None
    heldout_fraction: Annotated[float, Field(ge=0, le=0.49)] | None = None
    gpu: Annotated[str, StringConstraints(max_length=32)] | None = None
    priority: Annotated[int, Field(ge=-10, le=10)] | None = None
    init_from: InitFrom | None = None
    export: ExportOptions | None = None


class HubPushRequest(_Strict):
    repo_id: Annotated[str, StringConstraints(pattern=HF_REPO)]
    private: bool = True
    include_onnx: bool = False


class ModelUpdate(_Strict):
    name: ResourceName


class AdminGpuUpdate(_Strict):
    status: Literal["online", "draining", "disabled"]
