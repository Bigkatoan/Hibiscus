from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="EvalMetricsOverall")


@_attrs_define
class EvalMetricsOverall:
    """
    Attributes:
        mae (float):
        mse (float):
        mae_normalized (float | Unset):
    """

    mae: float
    mse: float
    mae_normalized: float | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        mae = self.mae

        mse = self.mse

        mae_normalized = self.mae_normalized

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "mae": mae,
                "mse": mse,
            }
        )
        if mae_normalized is not UNSET:
            field_dict["mae_normalized"] = mae_normalized

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        mae = d.pop("mae")

        mse = d.pop("mse")

        mae_normalized = d.pop("mae_normalized", UNSET)

        eval_metrics_overall = cls(
            mae=mae,
            mse=mse,
            mae_normalized=mae_normalized,
        )

        eval_metrics_overall.additional_properties = d
        return eval_metrics_overall

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
