from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MetricSeries")


@_attrs_define
class MetricSeries:
    """
    Attributes:
        key (str):
        steps (list[int]):
        values (list[Union[None, float]]):
        has_nonfinite (Union[Unset, bool]):
        downsampled (Union[Unset, bool]):
    """

    key: str
    steps: list[int]
    values: list[Union[None, float]]
    has_nonfinite: Union[Unset, bool] = UNSET
    downsampled: Union[Unset, bool] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        key = self.key

        steps = self.steps

        values = []
        for values_item_data in self.values:
            values_item: Union[None, float]
            values_item = values_item_data
            values.append(values_item)

        has_nonfinite = self.has_nonfinite

        downsampled = self.downsampled

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "key": key,
                "steps": steps,
                "values": values,
            }
        )
        if has_nonfinite is not UNSET:
            field_dict["has_nonfinite"] = has_nonfinite
        if downsampled is not UNSET:
            field_dict["downsampled"] = downsampled

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        key = d.pop("key")

        steps = cast(list[int], d.pop("steps"))

        values = []
        _values = d.pop("values")
        for values_item_data in _values:

            def _parse_values_item(data: object) -> Union[None, float]:
                if data is None:
                    return data
                return cast(Union[None, float], data)

            values_item = _parse_values_item(values_item_data)

            values.append(values_item)

        has_nonfinite = d.pop("has_nonfinite", UNSET)

        downsampled = d.pop("downsampled", UNSET)

        metric_series = cls(
            key=key,
            steps=steps,
            values=values,
            has_nonfinite=has_nonfinite,
            downsampled=downsampled,
        )

        metric_series.additional_properties = d
        return metric_series

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
