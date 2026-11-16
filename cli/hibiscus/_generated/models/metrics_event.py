from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

if TYPE_CHECKING:
    from ..models.metrics_event_values import MetricsEventValues


T = TypeVar("T", bound="MetricsEvent")


@_attrs_define
class MetricsEvent:
    """
    Attributes:
        kind (Literal['metrics']):
        step (int): Exact step (log-parsing.md §4)
        values (MetricsEventValues): Canonical keys (log-parsing.md §5): loss, grad_norm, lr, data_s, prep_s, update_s,
            step_s, samples_per_s, gpu_mem_gb, grad_scale, <policy sub-losses>; NaN/Inf => null
        ts (datetime.datetime):
    """

    kind: Literal["metrics"]
    step: int
    values: MetricsEventValues
    ts: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        kind = self.kind

        step = self.step

        values = self.values.to_dict()

        ts = self.ts.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "kind": kind,
                "step": step,
                "values": values,
                "ts": ts,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.metrics_event_values import MetricsEventValues

        d = dict(src_dict)
        kind = cast(Literal["metrics"], d.pop("kind"))
        if kind != "metrics":
            raise ValueError(f"kind must match const 'metrics', got '{kind}'")

        step = d.pop("step")

        values = MetricsEventValues.from_dict(d.pop("values"))

        ts = isoparse(d.pop("ts"))

        metrics_event = cls(
            kind=kind,
            step=step,
            values=values,
            ts=ts,
        )

        metrics_event.additional_properties = d
        return metrics_event

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
