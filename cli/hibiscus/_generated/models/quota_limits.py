from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="QuotaLimits")


@_attrs_define
class QuotaLimits:
    """
    Attributes:
        max_concurrent_runs (int):
        max_queued_runs (int):
        gpu_hours_per_month (float):
        storage_bytes (int):
        max_upload_bytes (int):
    """

    max_concurrent_runs: int
    max_queued_runs: int
    gpu_hours_per_month: float
    storage_bytes: int
    max_upload_bytes: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        max_concurrent_runs = self.max_concurrent_runs

        max_queued_runs = self.max_queued_runs

        gpu_hours_per_month = self.gpu_hours_per_month

        storage_bytes = self.storage_bytes

        max_upload_bytes = self.max_upload_bytes

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "max_concurrent_runs": max_concurrent_runs,
                "max_queued_runs": max_queued_runs,
                "gpu_hours_per_month": gpu_hours_per_month,
                "storage_bytes": storage_bytes,
                "max_upload_bytes": max_upload_bytes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        max_concurrent_runs = d.pop("max_concurrent_runs")

        max_queued_runs = d.pop("max_queued_runs")

        gpu_hours_per_month = d.pop("gpu_hours_per_month")

        storage_bytes = d.pop("storage_bytes")

        max_upload_bytes = d.pop("max_upload_bytes")

        quota_limits = cls(
            max_concurrent_runs=max_concurrent_runs,
            max_queued_runs=max_queued_runs,
            gpu_hours_per_month=gpu_hours_per_month,
            storage_bytes=storage_bytes,
            max_upload_bytes=max_upload_bytes,
        )

        quota_limits.additional_properties = d
        return quota_limits

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
