from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..models.admin_update_gpu_body_status import AdminUpdateGpuBodyStatus

T = TypeVar("T", bound="AdminUpdateGpuBody")


@_attrs_define
class AdminUpdateGpuBody:
    """
    Attributes:
        status (AdminUpdateGpuBodyStatus):
    """

    status: AdminUpdateGpuBodyStatus

    def to_dict(self) -> dict[str, Any]:
        status = self.status.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "status": status,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        status = AdminUpdateGpuBodyStatus(d.pop("status"))

        admin_update_gpu_body = cls(
            status=status,
        )

        return admin_update_gpu_body
