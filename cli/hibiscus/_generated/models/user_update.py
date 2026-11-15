from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
)

from attrs import define as _attrs_define

from ..models.locale import Locale
from ..types import UNSET, Unset

T = TypeVar("T", bound="UserUpdate")


@_attrs_define
class UserUpdate:
    """
    Attributes:
        display_name (Union[Unset, str]):
        locale (Union[Unset, Locale]):
    """

    display_name: Union[Unset, str] = UNSET
    locale: Union[Unset, Locale] = UNSET

    def to_dict(self) -> dict[str, Any]:
        display_name = self.display_name

        locale: Union[Unset, str] = UNSET
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
        locale: Union[Unset, Locale]
        if isinstance(_locale, Unset):
            locale = UNSET
        else:
            locale = Locale(_locale)

        user_update = cls(
            display_name=display_name,
            locale=locale,
        )

        return user_update
