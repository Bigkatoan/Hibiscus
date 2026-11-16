from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.locale import Locale

T = TypeVar("T", bound="AuthConfig")


@_attrs_define
class AuthConfig:
    """
    Attributes:
        turnstile_site_key (None | str):
        email_delivery_enabled (bool):
        password_min_length (Literal[12]):
        supported_locales (list[Locale]):
    """

    turnstile_site_key: None | str
    email_delivery_enabled: bool
    password_min_length: Literal[12]
    supported_locales: list[Locale]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        turnstile_site_key: None | str
        turnstile_site_key = self.turnstile_site_key

        email_delivery_enabled = self.email_delivery_enabled

        password_min_length = self.password_min_length

        supported_locales = []
        for supported_locales_item_data in self.supported_locales:
            supported_locales_item = supported_locales_item_data.value
            supported_locales.append(supported_locales_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "turnstile_site_key": turnstile_site_key,
                "email_delivery_enabled": email_delivery_enabled,
                "password_min_length": password_min_length,
                "supported_locales": supported_locales,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_turnstile_site_key(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        turnstile_site_key = _parse_turnstile_site_key(d.pop("turnstile_site_key"))

        email_delivery_enabled = d.pop("email_delivery_enabled")

        password_min_length = cast(Literal[12], d.pop("password_min_length"))
        if password_min_length != 12:
            raise ValueError(
                f"password_min_length must match const 12, got '{password_min_length}'"
            )

        supported_locales = []
        _supported_locales = d.pop("supported_locales")
        for supported_locales_item_data in _supported_locales:
            supported_locales_item = Locale(supported_locales_item_data)

            supported_locales.append(supported_locales_item)

        auth_config = cls(
            turnstile_site_key=turnstile_site_key,
            email_delivery_enabled=email_delivery_enabled,
            password_min_length=password_min_length,
            supported_locales=supported_locales,
        )

        auth_config.additional_properties = d
        return auth_config

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
