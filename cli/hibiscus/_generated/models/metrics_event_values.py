from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="MetricsEventValues")


@_attrs_define
class MetricsEventValues:
    """Canonical keys (log-parsing.md §5): loss, grad_norm, lr, data_s, prep_s, update_s, step_s, samples_per_s,
    gpu_mem_gb, grad_scale, <policy sub-losses>; NaN/Inf => null

    """

    additional_properties: dict[str, Union[None, float]] = _attrs_field(
        init=False, factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        field_dict: dict[str, Any] = {}
        for prop_name, prop in self.additional_properties.items():
            field_dict[prop_name] = prop

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        metrics_event_values = cls()

        additional_properties = {}
        for prop_name, prop_dict in d.items():

            def _parse_additional_property(data: object) -> Union[None, float]:
                if data is None:
                    return data
                return cast(Union[None, float], data)

            additional_property = _parse_additional_property(prop_dict)

            additional_properties[prop_name] = additional_property

        metrics_event_values.additional_properties = additional_properties
        return metrics_event_values

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Union[None, float]:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Union[None, float]) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
