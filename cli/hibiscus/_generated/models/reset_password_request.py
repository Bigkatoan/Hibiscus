from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="ResetPasswordRequest")


@_attrs_define
class ResetPasswordRequest:
    """
    Attributes:
        token (str):
        new_password (str): argon2id; >= 12 chars; rejected if in the offline breached-password list (422
            `password_breached`)
    """

    token: str
    new_password: str

    def to_dict(self) -> dict[str, Any]:
        token = self.token

        new_password = self.new_password

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "token": token,
                "new_password": new_password,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        token = d.pop("token")

        new_password = d.pop("new_password")

        reset_password_request = cls(
            token=token,
            new_password=new_password,
        )

        return reset_password_request
