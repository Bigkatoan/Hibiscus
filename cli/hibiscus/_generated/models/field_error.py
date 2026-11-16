from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="FieldError")


@_attrs_define
class FieldError:
    """
    Attributes:
        loc (list[int | str]): JSON path, e.g. `["body","config","policy","chunk_size"]`
        code (str): pydantic / JSON Schema keyword, e.g. `minimum`, `required`, `pattern`, `policy_config_invalid`
        message (str):
    """

    loc: list[int | str]
    code: str
    message: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        loc = []
        for loc_item_data in self.loc:
            loc_item: int | str
            loc_item = loc_item_data
            loc.append(loc_item)

        code = self.code

        message = self.message

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "loc": loc,
                "code": code,
                "message": message,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        loc = []
        _loc = d.pop("loc")
        for loc_item_data in _loc:

            def _parse_loc_item(data: object) -> int | str:
                return cast(int | str, data)

            loc_item = _parse_loc_item(loc_item_data)

            loc.append(loc_item)

        code = d.pop("code")

        message = d.pop("message")

        field_error = cls(
            loc=loc,
            code=code,
            message=message,
        )

        field_error.additional_properties = d
        return field_error

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
