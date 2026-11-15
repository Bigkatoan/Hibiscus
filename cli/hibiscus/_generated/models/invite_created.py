import datetime
from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    Union,
    cast,
)
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.invite_status import InviteStatus
from ..models.workspace_role import WorkspaceRole
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.user_ref import UserRef


T = TypeVar("T", bound="InviteCreated")


@_attrs_define
class InviteCreated:
    """
    Attributes:
        id (UUID):
        email (str):
        role (WorkspaceRole): owner: everything incl. delete workspace, manage owners. admin: members/invites (non-
            owner),
            all resources. member: create datasets/runs; edit/cancel/delete own runs and datasets;
            read all. viewer: read-only. owner/admin require 2FA.
        status (InviteStatus):
        expires_at (datetime.datetime):
        created_at (datetime.datetime):
        invited_by (Union[Unset, UserRef]):
        accept_url (Union[None, Unset, str]): Only when email delivery is disabled (admin shares it manually)
    """

    id: UUID
    email: str
    role: WorkspaceRole
    status: InviteStatus
    expires_at: datetime.datetime
    created_at: datetime.datetime
    invited_by: Union[Unset, "UserRef"] = UNSET
    accept_url: Union[None, Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        email = self.email

        role = self.role.value

        status = self.status.value

        expires_at = self.expires_at.isoformat()

        created_at = self.created_at.isoformat()

        invited_by: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.invited_by, Unset):
            invited_by = self.invited_by.to_dict()

        accept_url: Union[None, Unset, str]
        if isinstance(self.accept_url, Unset):
            accept_url = UNSET
        else:
            accept_url = self.accept_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "email": email,
                "role": role,
                "status": status,
                "expires_at": expires_at,
                "created_at": created_at,
            }
        )
        if invited_by is not UNSET:
            field_dict["invited_by"] = invited_by
        if accept_url is not UNSET:
            field_dict["accept_url"] = accept_url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.user_ref import UserRef

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        email = d.pop("email")

        role = WorkspaceRole(d.pop("role"))

        status = InviteStatus(d.pop("status"))

        expires_at = isoparse(d.pop("expires_at"))

        created_at = isoparse(d.pop("created_at"))

        _invited_by = d.pop("invited_by", UNSET)
        invited_by: Union[Unset, UserRef]
        if isinstance(_invited_by, Unset):
            invited_by = UNSET
        else:
            invited_by = UserRef.from_dict(_invited_by)

        def _parse_accept_url(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        accept_url = _parse_accept_url(d.pop("accept_url", UNSET))

        invite_created = cls(
            id=id,
            email=email,
            role=role,
            status=status,
            expires_at=expires_at,
            created_at=created_at,
            invited_by=invited_by,
            accept_url=accept_url,
        )

        invite_created.additional_properties = d
        return invite_created

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
