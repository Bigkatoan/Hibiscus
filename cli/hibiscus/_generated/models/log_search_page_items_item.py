from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="LogSearchPageItemsItem")


@_attrs_define
class LogSearchPageItemsItem:
    """
    Attributes:
        line_no (int):
        byte_offset (int):
        text (str):
        attempt (int | Unset):
    """

    line_no: int
    byte_offset: int
    text: str
    attempt: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        line_no = self.line_no

        byte_offset = self.byte_offset

        text = self.text

        attempt = self.attempt

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "line_no": line_no,
                "byte_offset": byte_offset,
                "text": text,
            }
        )
        if attempt is not UNSET:
            field_dict["attempt"] = attempt

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        line_no = d.pop("line_no")

        byte_offset = d.pop("byte_offset")

        text = d.pop("text")

        attempt = d.pop("attempt", UNSET)

        log_search_page_items_item = cls(
            line_no=line_no,
            byte_offset=byte_offset,
            text=text,
            attempt=attempt,
        )

        log_search_page_items_item.additional_properties = d
        return log_search_page_items_item

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
