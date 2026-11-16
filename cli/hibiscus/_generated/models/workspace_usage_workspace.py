from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.quota_limits import QuotaLimits


T = TypeVar("T", bound="WorkspaceUsageWorkspace")


@_attrs_define
class WorkspaceUsageWorkspace:
    """
    Attributes:
        limits (QuotaLimits):
        storage_bytes_used (int):
        gpu_hours_this_month (float):
        active_runs (int):
        queued_runs (int):
    """

    limits: QuotaLimits
    storage_bytes_used: int
    gpu_hours_this_month: float
    active_runs: int
    queued_runs: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        limits = self.limits.to_dict()

        storage_bytes_used = self.storage_bytes_used

        gpu_hours_this_month = self.gpu_hours_this_month

        active_runs = self.active_runs

        queued_runs = self.queued_runs

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "limits": limits,
                "storage_bytes_used": storage_bytes_used,
                "gpu_hours_this_month": gpu_hours_this_month,
                "active_runs": active_runs,
                "queued_runs": queued_runs,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.quota_limits import QuotaLimits

        d = dict(src_dict)
        limits = QuotaLimits.from_dict(d.pop("limits"))

        storage_bytes_used = d.pop("storage_bytes_used")

        gpu_hours_this_month = d.pop("gpu_hours_this_month")

        active_runs = d.pop("active_runs")

        queued_runs = d.pop("queued_runs")

        workspace_usage_workspace = cls(
            limits=limits,
            storage_bytes_used=storage_bytes_used,
            gpu_hours_this_month=gpu_hours_this_month,
            active_runs=active_runs,
            queued_runs=queued_runs,
        )

        workspace_usage_workspace.additional_properties = d
        return workspace_usage_workspace

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
