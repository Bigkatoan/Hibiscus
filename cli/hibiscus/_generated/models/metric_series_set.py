from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
)
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.metric_series import MetricSeries


T = TypeVar("T", bound="MetricSeriesSet")


@_attrs_define
class MetricSeriesSet:
    """
    Attributes:
        run_id (UUID):
        series (list['MetricSeries']):
    """

    run_id: UUID
    series: list["MetricSeries"]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        run_id = str(self.run_id)

        series = []
        for series_item_data in self.series:
            series_item = series_item_data.to_dict()
            series.append(series_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "run_id": run_id,
                "series": series,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.metric_series import MetricSeries

        d = dict(src_dict)
        run_id = UUID(d.pop("run_id"))

        series = []
        _series = d.pop("series")
        for series_item_data in _series:
            series_item = MetricSeries.from_dict(series_item_data)

            series.append(series_item)

        metric_series_set = cls(
            run_id=run_id,
            series=series,
        )

        metric_series_set.additional_properties = d
        return metric_series_set

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
