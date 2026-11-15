import datetime
from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

T = TypeVar("T", bound="TelemetryEvent")


@_attrs_define
class TelemetryEvent:
    """
    Attributes:
        gpu_id (str):
        ts (datetime.datetime):
        util_pct (float):
        mem_used_mb (int):
        mem_total_mb (int):
        temperature_c (float):
        power_w (float):
        kind (Literal['telemetry']):
    """

    gpu_id: str
    ts: datetime.datetime
    util_pct: float
    mem_used_mb: int
    mem_total_mb: int
    temperature_c: float
    power_w: float
    kind: Literal["telemetry"]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        gpu_id = self.gpu_id

        ts = self.ts.isoformat()

        util_pct = self.util_pct

        mem_used_mb = self.mem_used_mb

        mem_total_mb = self.mem_total_mb

        temperature_c = self.temperature_c

        power_w = self.power_w

        kind = self.kind

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "gpu_id": gpu_id,
                "ts": ts,
                "util_pct": util_pct,
                "mem_used_mb": mem_used_mb,
                "mem_total_mb": mem_total_mb,
                "temperature_c": temperature_c,
                "power_w": power_w,
                "kind": kind,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        gpu_id = d.pop("gpu_id")

        ts = isoparse(d.pop("ts"))

        util_pct = d.pop("util_pct")

        mem_used_mb = d.pop("mem_used_mb")

        mem_total_mb = d.pop("mem_total_mb")

        temperature_c = d.pop("temperature_c")

        power_w = d.pop("power_w")

        kind = cast(Literal["telemetry"], d.pop("kind"))
        if kind != "telemetry":
            raise ValueError(f"kind must match const 'telemetry', got '{kind}'")

        telemetry_event = cls(
            gpu_id=gpu_id,
            ts=ts,
            util_pct=util_pct,
            mem_used_mb=mem_used_mb,
            mem_total_mb=mem_total_mb,
            temperature_c=temperature_c,
            power_w=power_w,
            kind=kind,
        )

        telemetry_event.additional_properties = d
        return telemetry_event

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
