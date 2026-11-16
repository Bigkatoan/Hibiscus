from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.workspace_role import WorkspaceRole
from ..types import UNSET, Unset

T = TypeVar("T", bound="InvitePreview")


@_attrs_define
class InvitePreview:
    """
    Attributes:
        workspace_name (str):
        email (str):
        role (WorkspaceRole): owner: everything incl. delete workspace, manage owners. admin: members/invites (non-
            owner),
            all resources. member: create datasets/runs; edit/cancel/delete own runs and datasets;
            read all. viewer: read-only. owner/admin require 2FA.
        expires_at (datetime.datetime):
        account_exists (bool): true => client should log in and call accept
        invited_by (None | str | Unset): Display name
    """

    workspace_name: str
    email: str
    role: WorkspaceRole
    expires_at: datetime.datetime
    account_exists: bool
    invited_by: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        workspace_name = self.workspace_name

        email = self.email

        role = self.role.value

        expires_at = self.expires_at.isoformat()

        account_exists = self.account_exists

        invited_by: None | str | Unset
        if isinstance(self.invited_by, Unset):
            invited_by = UNSET
        else:
            invited_by = self.invited_by

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "workspace_name": workspace_name,
                "email": email,
                "role": role,
                "expires_at": expires_at,
                "account_exists": account_exists,
            }
        )
        if invited_by is not UNSET:
            field_dict["invited_by"] = invited_by

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        workspace_name = d.pop("workspace_name")

        email = d.pop("email")

        role = WorkspaceRole(d.pop("role"))

        expires_at = isoparse(d.pop("expires_at"))

        account_exists = d.pop("account_exists")

        def _parse_invited_by(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        invited_by = _parse_invited_by(d.pop("invited_by", UNSET))

        invite_preview = cls(
            workspace_name=workspace_name,
            email=email,
            role=role,
            expires_at=expires_at,
            account_exists=account_exists,
            invited_by=invited_by,
        )

        invite_preview.additional_properties = d
        return invite_preview

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
