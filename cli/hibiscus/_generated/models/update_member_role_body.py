from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

from ..models.workspace_role import WorkspaceRole

T = TypeVar("T", bound="UpdateMemberRoleBody")


@_attrs_define
class UpdateMemberRoleBody:
    """
    Attributes:
        role (WorkspaceRole): owner: everything incl. delete workspace, manage owners. admin: members/invites (non-
            owner),
            all resources. member: create datasets/runs; edit/cancel/delete own runs and datasets;
            read all. viewer: read-only. owner/admin require 2FA.
    """

    role: WorkspaceRole

    def to_dict(self) -> dict[str, Any]:
        role = self.role.value

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "role": role,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        role = WorkspaceRole(d.pop("role"))

        update_member_role_body = cls(
            role=role,
        )

        return update_member_role_body
