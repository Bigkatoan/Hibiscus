from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="TotpDisableRequest")


@_attrs_define
class TotpDisableRequest:
    """
    Attributes:
        password (str):
        code (str):
    """

    password: str
    code: str

    def to_dict(self) -> dict[str, Any]:
        password = self.password

        code = self.code

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "password": password,
                "code": code,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        password = d.pop("password")

        code = d.pop("code")

        totp_disable_request = cls(
            password=password,
            code=code,
        )

        return totp_disable_request
