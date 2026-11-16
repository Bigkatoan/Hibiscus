from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.notification_kind import NotificationKind
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.notification_params import NotificationParams


T = TypeVar("T", bound="Notification")


@_attrs_define
class Notification:
    """
    Attributes:
        id (UUID):
        kind (NotificationKind):
        params (NotificationParams): i18n interpolation params
        read (bool):
        created_at (datetime.datetime):
        workspace_id (None | Unset | UUID):
        link (None | str | Unset): SPA path
    """

    id: UUID
    kind: NotificationKind
    params: NotificationParams
    read: bool
    created_at: datetime.datetime
    workspace_id: None | Unset | UUID = UNSET
    link: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        kind = self.kind.value

        params = self.params.to_dict()

        read = self.read

        created_at = self.created_at.isoformat()

        workspace_id: None | str | Unset
        if isinstance(self.workspace_id, Unset):
            workspace_id = UNSET
        elif isinstance(self.workspace_id, UUID):
            workspace_id = str(self.workspace_id)
        else:
            workspace_id = self.workspace_id

        link: None | str | Unset
        if isinstance(self.link, Unset):
            link = UNSET
        else:
            link = self.link

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "kind": kind,
                "params": params,
                "read": read,
                "created_at": created_at,
            }
        )
        if workspace_id is not UNSET:
            field_dict["workspace_id"] = workspace_id
        if link is not UNSET:
            field_dict["link"] = link

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.notification_params import NotificationParams

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        kind = NotificationKind(d.pop("kind"))

        params = NotificationParams.from_dict(d.pop("params"))

        read = d.pop("read")

        created_at = isoparse(d.pop("created_at"))

        def _parse_workspace_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                workspace_id_type_0 = UUID(data)

                return workspace_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        workspace_id = _parse_workspace_id(d.pop("workspace_id", UNSET))

        def _parse_link(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        link = _parse_link(d.pop("link", UNSET))

        notification = cls(
            id=id,
            kind=kind,
            params=params,
            read=read,
            created_at=created_at,
            workspace_id=workspace_id,
            link=link,
        )

        notification.additional_properties = d
        return notification

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
