from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="EpisodeDetailSeriesItem")


@_attrs_define
class EpisodeDetailSeriesItem:
    """
    Attributes:
        feature (str):
        dim (int):
        name (str):
        values (list[float | None]):
    """

    feature: str
    dim: int
    name: str
    values: list[float | None]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        feature = self.feature

        dim = self.dim

        name = self.name

        values = []
        for values_item_data in self.values:
            values_item: float | None
            values_item = values_item_data
            values.append(values_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "feature": feature,
                "dim": dim,
                "name": name,
                "values": values,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        feature = d.pop("feature")

        dim = d.pop("dim")

        name = d.pop("name")

        values = []
        _values = d.pop("values")
        for values_item_data in _values:

            def _parse_values_item(data: object) -> float | None:
                if data is None:
                    return data
                return cast(float | None, data)

            values_item = _parse_values_item(values_item_data)

            values.append(values_item)

        episode_detail_series_item = cls(
            feature=feature,
            dim=dim,
            name=name,
            values=values,
        )

        episode_detail_series_item.additional_properties = d
        return episode_detail_series_item

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
