from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="RecoveryCodes")


@_attrs_define
class RecoveryCodes:
    """
    Attributes:
        recovery_codes (list[str]):
        api_tokens_revoked (int | Unset): enableTotp only: number of the user's personal access tokens revoked because
            they were minted before 2FA was enabled. New tokens must be created from this 2FA-verified session.
    """

    recovery_codes: list[str]
    api_tokens_revoked: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        recovery_codes = self.recovery_codes

        api_tokens_revoked = self.api_tokens_revoked

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "recovery_codes": recovery_codes,
            }
        )
        if api_tokens_revoked is not UNSET:
            field_dict["api_tokens_revoked"] = api_tokens_revoked

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        recovery_codes = cast(list[str], d.pop("recovery_codes"))

        api_tokens_revoked = d.pop("api_tokens_revoked", UNSET)

        recovery_codes = cls(
            recovery_codes=recovery_codes,
            api_tokens_revoked=api_tokens_revoked,
        )

        recovery_codes.additional_properties = d
        return recovery_codes

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
