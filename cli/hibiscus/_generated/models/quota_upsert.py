from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
    cast,
)
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="QuotaUpsert")


@_attrs_define
class QuotaUpsert:
    """
    Attributes:
        max_concurrent_runs (int):
        max_queued_runs (int):
        gpu_hours_per_month (float):
        storage_bytes (int):
        max_upload_bytes (int):
        user_id (Union[None, UUID]):
    """

    max_concurrent_runs: int
    max_queued_runs: int
    gpu_hours_per_month: float
    storage_bytes: int
    max_upload_bytes: int
    user_id: Union[None, UUID]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        max_concurrent_runs = self.max_concurrent_runs

        max_queued_runs = self.max_queued_runs

        gpu_hours_per_month = self.gpu_hours_per_month

        storage_bytes = self.storage_bytes

        max_upload_bytes = self.max_upload_bytes

        user_id: Union[None, str]
        if isinstance(self.user_id, UUID):
            user_id = str(self.user_id)
        else:
            user_id = self.user_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "max_concurrent_runs": max_concurrent_runs,
                "max_queued_runs": max_queued_runs,
                "gpu_hours_per_month": gpu_hours_per_month,
                "storage_bytes": storage_bytes,
                "max_upload_bytes": max_upload_bytes,
                "user_id": user_id,
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

        def _parse_user_id(data: object) -> Union[None, UUID]:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                user_id_type_0 = UUID(data)

                return user_id_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, UUID], data)

        user_id = _parse_user_id(d.pop("user_id"))

        quota_upsert = cls(
            max_concurrent_runs=max_concurrent_runs,
            max_queued_runs=max_queued_runs,
            gpu_hours_per_month=gpu_hours_per_month,
            storage_bytes=storage_bytes,
            max_upload_bytes=max_upload_bytes,
            user_id=user_id,
        )

        quota_upsert.additional_properties = d
        return quota_upsert

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
