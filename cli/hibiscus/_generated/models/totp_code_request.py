from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="TotpCodeRequest")


@_attrs_define
class TotpCodeRequest:
    """
    Attributes:
        code (str):
    """

    code: str

    def to_dict(self) -> dict[str, Any]:
        code = self.code

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "code": code,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        code = d.pop("code")

        totp_code_request = cls(
            code=code,
        )

        return totp_code_request
