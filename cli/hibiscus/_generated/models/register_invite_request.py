from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..models.locale import Locale
from ..types import UNSET, Unset

T = TypeVar("T", bound="RegisterInviteRequest")


@_attrs_define
class RegisterInviteRequest:
    """
    Attributes:
        invite_token (str):
        display_name (str):
        password (str): argon2id; >= 12 chars; rejected if in the offline breached-password list (422
            `password_breached`)
        locale (Locale | Unset):
        turnstile_token (str | Unset): Cloudflare Turnstile response token (required when AuthConfig.turnstile_site_key
            is set)
    """

    invite_token: str
    display_name: str
    password: str
    locale: Locale | Unset = UNSET
    turnstile_token: str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        invite_token = self.invite_token

        display_name = self.display_name

        password = self.password

        locale: str | Unset = UNSET
        if not isinstance(self.locale, Unset):
            locale = self.locale.value

        turnstile_token = self.turnstile_token

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "invite_token": invite_token,
                "display_name": display_name,
                "password": password,
            }
        )
        if locale is not UNSET:
            field_dict["locale"] = locale
        if turnstile_token is not UNSET:
            field_dict["turnstile_token"] = turnstile_token

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        invite_token = d.pop("invite_token")

        display_name = d.pop("display_name")

        password = d.pop("password")

        _locale = d.pop("locale", UNSET)
        locale: Locale | Unset
        if isinstance(_locale, Unset):
            locale = UNSET
        else:
            locale = Locale(_locale)

        turnstile_token = d.pop("turnstile_token", UNSET)

        register_invite_request = cls(
            invite_token=invite_token,
            display_name=display_name,
            password=password,
            locale=locale,
            turnstile_token=turnstile_token,
        )

        return register_invite_request
