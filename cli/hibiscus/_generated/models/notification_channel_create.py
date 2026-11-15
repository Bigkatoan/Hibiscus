from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
)

from attrs import define as _attrs_define

from ..models.notification_channel_create_events_item import (
    NotificationChannelCreateEventsItem,
)
from ..models.notification_channel_kind import NotificationChannelKind

T = TypeVar("T", bound="NotificationChannelCreate")


@_attrs_define
class NotificationChannelCreate:
    """
    Attributes:
        kind (NotificationChannelKind):
        target (str): email: address; discord/webhook: https URL (server blocks private IPs, SSRF); telegram:
            `<bot_token>:<chat_id>`
        events (list[NotificationChannelCreateEventsItem]):
    """

    kind: NotificationChannelKind
    target: str
    events: list[NotificationChannelCreateEventsItem]

    def to_dict(self) -> dict[str, Any]:
        kind = self.kind.value

        target = self.target

        events = []
        for events_item_data in self.events:
            events_item = events_item_data.value
            events.append(events_item)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "kind": kind,
                "target": target,
                "events": events,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        kind = NotificationChannelKind(d.pop("kind"))

        target = d.pop("target")

        events = []
        _events = d.pop("events")
        for events_item_data in _events:
            events_item = NotificationChannelCreateEventsItem(events_item_data)

            events.append(events_item)

        notification_channel_create = cls(
            kind=kind,
            target=target,
            events=events,
        )

        return notification_channel_create
