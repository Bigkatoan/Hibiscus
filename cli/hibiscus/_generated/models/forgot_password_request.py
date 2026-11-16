from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ForgotPasswordRequest")


@_attrs_define
class ForgotPasswordRequest:
    """
    Attributes:
        email (str):
        turnstile_token (str | Unset): Cloudflare Turnstile response token (required when AuthConfig.turnstile_site_key
            is set)
    """

    email: str
    turnstile_token: str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        email = self.email

        turnstile_token = self.turnstile_token

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "email": email,
            }
        )
        if turnstile_token is not UNSET:
            field_dict["turnstile_token"] = turnstile_token

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        email = d.pop("email")

        turnstile_token = d.pop("turnstile_token", UNSET)

        forgot_password_request = cls(
            email=email,
            turnstile_token=turnstile_token,
        )

        return forgot_password_request
