from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.workspace_role import WorkspaceRole

if TYPE_CHECKING:
    from ..models.user_ref import UserRef


T = TypeVar("T", bound="Member")


@_attrs_define
class Member:
    """
    Attributes:
        user (UserRef):
        email (str):
        role (WorkspaceRole): owner: everything incl. delete workspace, manage owners. admin: members/invites (non-
            owner),
            all resources. member: create datasets/runs; edit/cancel/delete own runs and datasets;
            read all. viewer: read-only. owner/admin require 2FA.
        mfa_enabled (bool):
        joined_at (datetime.datetime):
    """

    user: UserRef
    email: str
    role: WorkspaceRole
    mfa_enabled: bool
    joined_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        user = self.user.to_dict()

        email = self.email

        role = self.role.value

        mfa_enabled = self.mfa_enabled

        joined_at = self.joined_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "user": user,
                "email": email,
                "role": role,
                "mfa_enabled": mfa_enabled,
                "joined_at": joined_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.user_ref import UserRef

        d = dict(src_dict)
        user = UserRef.from_dict(d.pop("user"))

        email = d.pop("email")

        role = WorkspaceRole(d.pop("role"))

        mfa_enabled = d.pop("mfa_enabled")

        joined_at = isoparse(d.pop("joined_at"))

        member = cls(
            user=user,
            email=email,
            role=role,
            mfa_enabled=mfa_enabled,
            joined_at=joined_at,
        )

        member.additional_properties = d
        return member

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
