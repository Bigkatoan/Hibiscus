from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="EvalMetricsPerJointItem")


@_attrs_define
class EvalMetricsPerJointItem:
    """
    Attributes:
        name (str):
        mae (float):
        mse (float):
    """

    name: str
    mae: float
    mse: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        mae = self.mae

        mse = self.mse

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "mae": mae,
                "mse": mse,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        mae = d.pop("mae")

        mse = d.pop("mse")

        eval_metrics_per_joint_item = cls(
            name=name,
            mae=mae,
            mse=mse,
        )

        eval_metrics_per_joint_item.additional_properties = d
        return eval_metrics_per_joint_item

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
