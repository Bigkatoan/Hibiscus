import datetime
from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    cast,
)
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.notification_channel_kind import NotificationChannelKind

T = TypeVar("T", bound="NotificationChannel")


@_attrs_define
class NotificationChannel:
    """
    Attributes:
        id (UUID):
        kind (NotificationChannelKind):
        events (list[str]):
        enabled (bool):
        target_hint (str): Redacted target, e.g. `discord.com/api/webhooks/…/abcd`
        created_at (datetime.datetime):
    """

    id: UUID
    kind: NotificationChannelKind
    events: list[str]
    enabled: bool
    target_hint: str
    created_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        kind = self.kind.value

        events = self.events

        enabled = self.enabled

        target_hint = self.target_hint

        created_at = self.created_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "kind": kind,
                "events": events,
                "enabled": enabled,
                "target_hint": target_hint,
                "created_at": created_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        kind = NotificationChannelKind(d.pop("kind"))

        events = cast(list[str], d.pop("events"))

        enabled = d.pop("enabled")

        target_hint = d.pop("target_hint")

        created_at = isoparse(d.pop("created_at"))

        notification_channel = cls(
            id=id,
            kind=kind,
            events=events,
            enabled=enabled,
            target_hint=target_hint,
            created_at=created_at,
        )

        notification_channel.additional_properties = d
        return notification_channel

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
