from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.metric_series_set import MetricSeriesSet
    from ..models.run import Run
    from ..models.run_comparison_config_diff_item import RunComparisonConfigDiffItem


T = TypeVar("T", bound="RunComparison")


@_attrs_define
class RunComparison:
    """
    Attributes:
        runs (list['Run']):
        series (list['MetricSeriesSet']):
        config_diff (list['RunComparisonConfigDiffItem']): Only paths whose values differ between runs
    """

    runs: list["Run"]
    series: list["MetricSeriesSet"]
    config_diff: list["RunComparisonConfigDiffItem"]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        runs = []
        for runs_item_data in self.runs:
            runs_item = runs_item_data.to_dict()
            runs.append(runs_item)

        series = []
        for series_item_data in self.series:
            series_item = series_item_data.to_dict()
            series.append(series_item)

        config_diff = []
        for config_diff_item_data in self.config_diff:
            config_diff_item = config_diff_item_data.to_dict()
            config_diff.append(config_diff_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "runs": runs,
                "series": series,
                "config_diff": config_diff,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.metric_series_set import MetricSeriesSet
        from ..models.run import Run
        from ..models.run_comparison_config_diff_item import RunComparisonConfigDiffItem

        d = dict(src_dict)
        runs = []
        _runs = d.pop("runs")
        for runs_item_data in _runs:
            runs_item = Run.from_dict(runs_item_data)

            runs.append(runs_item)

        series = []
        _series = d.pop("series")
        for series_item_data in _series:
            series_item = MetricSeriesSet.from_dict(series_item_data)

            series.append(series_item)

        config_diff = []
        _config_diff = d.pop("config_diff")
        for config_diff_item_data in _config_diff:
            config_diff_item = RunComparisonConfigDiffItem.from_dict(
                config_diff_item_data
            )

            config_diff.append(config_diff_item)

        run_comparison = cls(
            runs=runs,
            series=series,
            config_diff=config_diff,
        )

        run_comparison.additional_properties = d
        return run_comparison

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
