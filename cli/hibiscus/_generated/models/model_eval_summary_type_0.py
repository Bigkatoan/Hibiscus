from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ModelEvalSummaryType0")


@_attrs_define
class ModelEvalSummaryType0:
    """
    Attributes:
        action_mae (Union[Unset, float]):
        action_mse (Union[Unset, float]):
    """

    action_mae: Union[Unset, float] = UNSET
    action_mse: Union[Unset, float] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        action_mae = self.action_mae

        action_mse = self.action_mse

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if action_mae is not UNSET:
            field_dict["action_mae"] = action_mae
        if action_mse is not UNSET:
            field_dict["action_mse"] = action_mse

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        action_mae = d.pop("action_mae", UNSET)

        action_mse = d.pop("action_mse", UNSET)

        model_eval_summary_type_0 = cls(
            action_mae=action_mae,
            action_mse=action_mse,
        )

        model_eval_summary_type_0.additional_properties = d
        return model_eval_summary_type_0

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
