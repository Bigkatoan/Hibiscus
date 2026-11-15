import datetime
from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="UploadPart")


@_attrs_define
class UploadPart:
    """
    Attributes:
        part_number (int):
        size (int):
        sha256 (str):
        received_at (Union[Unset, datetime.datetime]):
    """

    part_number: int
    size: int
    sha256: str
    received_at: Union[Unset, datetime.datetime] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        part_number = self.part_number

        size = self.size

        sha256 = self.sha256

        received_at: Union[Unset, str] = UNSET
        if not isinstance(self.received_at, Unset):
            received_at = self.received_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "part_number": part_number,
                "size": size,
                "sha256": sha256,
            }
        )
        if received_at is not UNSET:
            field_dict["received_at"] = received_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        part_number = d.pop("part_number")

        size = d.pop("size")

        sha256 = d.pop("sha256")

        _received_at = d.pop("received_at", UNSET)
        received_at: Union[Unset, datetime.datetime]
        if isinstance(_received_at, Unset):
            received_at = UNSET
        else:
            received_at = isoparse(_received_at)

        upload_part = cls(
            part_number=part_number,
            size=size,
            sha256=sha256,
            received_at=received_at,
        )

        upload_part.additional_properties = d
        return upload_part

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
