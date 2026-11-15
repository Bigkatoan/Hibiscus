import datetime
from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    Union,
)
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.workspace_role import WorkspaceRole
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.workspace_settings import WorkspaceSettings


T = TypeVar("T", bound="Workspace")


@_attrs_define
class Workspace:
    """
    Attributes:
        id (UUID):
        slug (str):
        name (str):
        my_role (WorkspaceRole): owner: everything incl. delete workspace, manage owners. admin: members/invites (non-
            owner),
            all resources. member: create datasets/runs; edit/cancel/delete own runs and datasets;
            read all. viewer: read-only. owner/admin require 2FA.
        created_at (datetime.datetime):
        member_count (Union[Unset, int]):
        settings (Union[Unset, WorkspaceSettings]):
    """

    id: UUID
    slug: str
    name: str
    my_role: WorkspaceRole
    created_at: datetime.datetime
    member_count: Union[Unset, int] = UNSET
    settings: Union[Unset, "WorkspaceSettings"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        slug = self.slug

        name = self.name

        my_role = self.my_role.value

        created_at = self.created_at.isoformat()

        member_count = self.member_count

        settings: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.settings, Unset):
            settings = self.settings.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "slug": slug,
                "name": name,
                "my_role": my_role,
                "created_at": created_at,
            }
        )
        if member_count is not UNSET:
            field_dict["member_count"] = member_count
        if settings is not UNSET:
            field_dict["settings"] = settings

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.workspace_settings import WorkspaceSettings

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        slug = d.pop("slug")

        name = d.pop("name")

        my_role = WorkspaceRole(d.pop("my_role"))

        created_at = isoparse(d.pop("created_at"))

        member_count = d.pop("member_count", UNSET)

        _settings = d.pop("settings", UNSET)
        settings: Union[Unset, WorkspaceSettings]
        if isinstance(_settings, Unset):
            settings = UNSET
        else:
            settings = WorkspaceSettings.from_dict(_settings)

        workspace = cls(
            id=id,
            slug=slug,
            name=name,
            my_role=my_role,
            created_at=created_at,
            member_count=member_count,
            settings=settings,
        )

        workspace.additional_properties = d
        return workspace

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
