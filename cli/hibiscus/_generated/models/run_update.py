from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
)

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="RunUpdate")


@_attrs_define
class RunUpdate:
    """
    Attributes:
        name (Union[Unset, str]):
        priority (Union[Unset, int]):
        gpu (Union[Unset, str]):
    """

    name: Union[Unset, str] = UNSET
    priority: Union[Unset, int] = UNSET
    gpu: Union[Unset, str] = UNSET

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        priority = self.priority

        gpu = self.gpu

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if priority is not UNSET:
            field_dict["priority"] = priority
        if gpu is not UNSET:
            field_dict["gpu"] = gpu

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name", UNSET)

        priority = d.pop("priority", UNSET)

        gpu = d.pop("gpu", UNSET)

        run_update = cls(
            name=name,
            priority=priority,
            gpu=gpu,
        )

        return run_update
