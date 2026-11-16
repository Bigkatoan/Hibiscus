from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.workspace_role import WorkspaceRole

T = TypeVar("T", bound="Membership")


@_attrs_define
class Membership:
    """
    Attributes:
        workspace_id (UUID):
        workspace_slug (str):
        workspace_name (str):
        role (WorkspaceRole): owner: everything incl. delete workspace, manage owners. admin: members/invites (non-
            owner),
            all resources. member: create datasets/runs; edit/cancel/delete own runs and datasets;
            read all. viewer: read-only. owner/admin require 2FA.
    """

    workspace_id: UUID
    workspace_slug: str
    workspace_name: str
    role: WorkspaceRole
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        workspace_id = str(self.workspace_id)

        workspace_slug = self.workspace_slug

        workspace_name = self.workspace_name

        role = self.role.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "workspace_id": workspace_id,
                "workspace_slug": workspace_slug,
                "workspace_name": workspace_name,
                "role": role,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        workspace_id = UUID(d.pop("workspace_id"))

        workspace_slug = d.pop("workspace_slug")

        workspace_name = d.pop("workspace_name")

        role = WorkspaceRole(d.pop("role"))

        membership = cls(
            workspace_id=workspace_id,
            workspace_slug=workspace_slug,
            workspace_name=workspace_name,
            role=role,
        )

        membership.additional_properties = d
        return membership

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
