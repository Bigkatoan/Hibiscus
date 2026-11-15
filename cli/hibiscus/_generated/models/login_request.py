from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
)

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="LoginRequest")


@_attrs_define
class LoginRequest:
    """
    Attributes:
        email (str):
        password (str):
        turnstile_token (Union[Unset, str]): Cloudflare Turnstile response token (required when
            AuthConfig.turnstile_site_key is set)
    """

    email: str
    password: str
    turnstile_token: Union[Unset, str] = UNSET

    def to_dict(self) -> dict[str, Any]:
        email = self.email

        password = self.password

        turnstile_token = self.turnstile_token

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "email": email,
                "password": password,
            }
        )
        if turnstile_token is not UNSET:
            field_dict["turnstile_token"] = turnstile_token

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        email = d.pop("email")

        password = d.pop("password")

        turnstile_token = d.pop("turnstile_token", UNSET)

        login_request = cls(
            email=email,
            password=password,
            turnstile_token=turnstile_token,
        )

        return login_request
