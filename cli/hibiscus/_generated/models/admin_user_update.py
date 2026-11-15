from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
)

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="AdminUserUpdate")


@_attrs_define
class AdminUserUpdate:
    """
    Attributes:
        is_active (Union[Unset, bool]):
        is_platform_admin (Union[Unset, bool]): Requires target to have 2FA enabled
        unlock (Union[Unset, bool]):
        reset_mfa (Union[Unset, bool]): Disables TOTP and deletes recovery codes (account recovery)
    """

    is_active: Union[Unset, bool] = UNSET
    is_platform_admin: Union[Unset, bool] = UNSET
    unlock: Union[Unset, bool] = UNSET
    reset_mfa: Union[Unset, bool] = UNSET

    def to_dict(self) -> dict[str, Any]:
        is_active = self.is_active

        is_platform_admin = self.is_platform_admin

        unlock = self.unlock

        reset_mfa = self.reset_mfa

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if is_active is not UNSET:
            field_dict["is_active"] = is_active
        if is_platform_admin is not UNSET:
            field_dict["is_platform_admin"] = is_platform_admin
        if unlock is not UNSET:
            field_dict["unlock"] = unlock
        if reset_mfa is not UNSET:
            field_dict["reset_mfa"] = reset_mfa

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        is_active = d.pop("is_active", UNSET)

        is_platform_admin = d.pop("is_platform_admin", UNSET)

        unlock = d.pop("unlock", UNSET)

        reset_mfa = d.pop("reset_mfa", UNSET)

        admin_user_update = cls(
            is_active=is_active,
            is_platform_admin=is_platform_admin,
            unlock=unlock,
            reset_mfa=reset_mfa,
        )

        return admin_user_update
