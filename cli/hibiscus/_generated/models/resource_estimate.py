from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.resource_estimate_source import ResourceEstimateSource
from ..types import UNSET, Unset

T = TypeVar("T", bound="ResourceEstimate")


@_attrs_define
class ResourceEstimate:
    """
    Attributes:
        source (ResourceEstimateSource):
        gpu_id (None | str | Unset):
        peak_vram_mb (int | None | Unset):
        sec_per_step (float | None | Unset):
        total_duration_s (float | None | Unset):
        measured_at (datetime.datetime | None | Unset):
    """

    source: ResourceEstimateSource
    gpu_id: None | str | Unset = UNSET
    peak_vram_mb: int | None | Unset = UNSET
    sec_per_step: float | None | Unset = UNSET
    total_duration_s: float | None | Unset = UNSET
    measured_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        source = self.source.value

        gpu_id: None | str | Unset
        if isinstance(self.gpu_id, Unset):
            gpu_id = UNSET
        else:
            gpu_id = self.gpu_id

        peak_vram_mb: int | None | Unset
        if isinstance(self.peak_vram_mb, Unset):
            peak_vram_mb = UNSET
        else:
            peak_vram_mb = self.peak_vram_mb

        sec_per_step: float | None | Unset
        if isinstance(self.sec_per_step, Unset):
            sec_per_step = UNSET
        else:
            sec_per_step = self.sec_per_step

        total_duration_s: float | None | Unset
        if isinstance(self.total_duration_s, Unset):
            total_duration_s = UNSET
        else:
            total_duration_s = self.total_duration_s

        measured_at: None | str | Unset
        if isinstance(self.measured_at, Unset):
            measured_at = UNSET
        elif isinstance(self.measured_at, datetime.datetime):
            measured_at = self.measured_at.isoformat()
        else:
            measured_at = self.measured_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "source": source,
            }
        )
        if gpu_id is not UNSET:
            field_dict["gpu_id"] = gpu_id
        if peak_vram_mb is not UNSET:
            field_dict["peak_vram_mb"] = peak_vram_mb
        if sec_per_step is not UNSET:
            field_dict["sec_per_step"] = sec_per_step
        if total_duration_s is not UNSET:
            field_dict["total_duration_s"] = total_duration_s
        if measured_at is not UNSET:
            field_dict["measured_at"] = measured_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        source = ResourceEstimateSource(d.pop("source"))

        def _parse_gpu_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        gpu_id = _parse_gpu_id(d.pop("gpu_id", UNSET))

        def _parse_peak_vram_mb(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        peak_vram_mb = _parse_peak_vram_mb(d.pop("peak_vram_mb", UNSET))

        def _parse_sec_per_step(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        sec_per_step = _parse_sec_per_step(d.pop("sec_per_step", UNSET))

        def _parse_total_duration_s(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        total_duration_s = _parse_total_duration_s(d.pop("total_duration_s", UNSET))

        def _parse_measured_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                measured_at_type_0 = isoparse(data)

                return measured_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        measured_at = _parse_measured_at(d.pop("measured_at", UNSET))

        resource_estimate = cls(
            source=source,
            gpu_id=gpu_id,
            peak_vram_mb=peak_vram_mb,
            sec_per_step=sec_per_step,
            total_duration_s=total_duration_s,
            measured_at=measured_at,
        )

        resource_estimate.additional_properties = d
        return resource_estimate

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
