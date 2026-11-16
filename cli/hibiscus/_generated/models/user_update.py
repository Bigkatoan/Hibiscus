from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..models.locale import Locale
from ..types import UNSET, Unset

T = TypeVar("T", bound="UserUpdate")


@_attrs_define
class UserUpdate:
    """
    Attributes:
        display_name (str | Unset):
        locale (Locale | Unset):
    """

    display_name: str | Unset = UNSET
    locale: Locale | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        display_name = self.display_name

        locale: str | Unset = UNSET
        if not isinstance(self.locale, Unset):
            locale = self.locale.value

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if display_name is not UNSET:
            field_dict["display_name"] = display_name
        if locale is not UNSET:
            field_dict["locale"] = locale

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        display_name = d.pop("display_name", UNSET)

        _locale = d.pop("locale", UNSET)
        locale: Locale | Unset
        if isinstance(_locale, Unset):
            locale = UNSET
        else:
            locale = Locale(_locale)

        user_update = cls(
            display_name=display_name,
            locale=locale,
        )

        return user_update
