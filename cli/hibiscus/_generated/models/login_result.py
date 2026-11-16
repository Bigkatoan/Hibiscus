from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.login_result_status import LoginResultStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.user import User


T = TypeVar("T", bound="LoginResult")


@_attrs_define
class LoginResult:
    """
    Attributes:
        status (LoginResultStatus):
        user (User | Unset):
        mfa_token (str | Unset): Present when status=mfa_required; valid 5 minutes, single use
        mfa_enrollment_required (bool | Unset):
        recovery_codes_remaining (int | Unset):
    """

    status: LoginResultStatus
    user: User | Unset = UNSET
    mfa_token: str | Unset = UNSET
    mfa_enrollment_required: bool | Unset = UNSET
    recovery_codes_remaining: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        status = self.status.value

        user: dict[str, Any] | Unset = UNSET
        if not isinstance(self.user, Unset):
            user = self.user.to_dict()

        mfa_token = self.mfa_token

        mfa_enrollment_required = self.mfa_enrollment_required

        recovery_codes_remaining = self.recovery_codes_remaining

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "status": status,
            }
        )
        if user is not UNSET:
            field_dict["user"] = user
        if mfa_token is not UNSET:
            field_dict["mfa_token"] = mfa_token
        if mfa_enrollment_required is not UNSET:
            field_dict["mfa_enrollment_required"] = mfa_enrollment_required
        if recovery_codes_remaining is not UNSET:
            field_dict["recovery_codes_remaining"] = recovery_codes_remaining

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.user import User

        d = dict(src_dict)
        status = LoginResultStatus(d.pop("status"))

        _user = d.pop("user", UNSET)
        user: User | Unset
        if isinstance(_user, Unset):
            user = UNSET
        else:
            user = User.from_dict(_user)

        mfa_token = d.pop("mfa_token", UNSET)

        mfa_enrollment_required = d.pop("mfa_enrollment_required", UNSET)

        recovery_codes_remaining = d.pop("recovery_codes_remaining", UNSET)

        login_result = cls(
            status=status,
            user=user,
            mfa_token=mfa_token,
            mfa_enrollment_required=mfa_enrollment_required,
            recovery_codes_remaining=recovery_codes_remaining,
        )

        login_result.additional_properties = d
        return login_result

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
