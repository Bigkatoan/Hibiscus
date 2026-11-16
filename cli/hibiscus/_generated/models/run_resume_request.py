from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="RunResumeRequest")


@_attrs_define
class RunResumeRequest:
    """
    Attributes:
        gpu (str | Unset): Override GPU for the next attempt
        total_steps (int | Unset): Extend training (must be > current_step)
    """

    gpu: str | Unset = UNSET
    total_steps: int | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        gpu = self.gpu

        total_steps = self.total_steps

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if gpu is not UNSET:
            field_dict["gpu"] = gpu
        if total_steps is not UNSET:
            field_dict["total_steps"] = total_steps

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        gpu = d.pop("gpu", UNSET)

        total_steps = d.pop("total_steps", UNSET)

        run_resume_request = cls(
            gpu=gpu,
            total_steps=total_steps,
        )

        return run_resume_request
