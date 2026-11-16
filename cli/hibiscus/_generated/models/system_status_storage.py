from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.system_status_storage_buckets import SystemStatusStorageBuckets


T = TypeVar("T", bound="SystemStatusStorage")


@_attrs_define
class SystemStatusStorage:
    """
    Attributes:
        buckets (SystemStatusStorageBuckets | Unset):
        disk_free_bytes (int | Unset):
    """

    buckets: SystemStatusStorageBuckets | Unset = UNSET
    disk_free_bytes: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        buckets: dict[str, Any] | Unset = UNSET
        if not isinstance(self.buckets, Unset):
            buckets = self.buckets.to_dict()

        disk_free_bytes = self.disk_free_bytes

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if buckets is not UNSET:
            field_dict["buckets"] = buckets
        if disk_free_bytes is not UNSET:
            field_dict["disk_free_bytes"] = disk_free_bytes

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.system_status_storage_buckets import SystemStatusStorageBuckets

        d = dict(src_dict)
        _buckets = d.pop("buckets", UNSET)
        buckets: SystemStatusStorageBuckets | Unset
        if isinstance(_buckets, Unset):
            buckets = UNSET
        else:
            buckets = SystemStatusStorageBuckets.from_dict(_buckets)

        disk_free_bytes = d.pop("disk_free_bytes", UNSET)

        system_status_storage = cls(
            buckets=buckets,
            disk_free_bytes=disk_free_bytes,
        )

        system_status_storage.additional_properties = d
        return system_status_storage

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
