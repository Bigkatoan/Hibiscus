from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.notification_channel import NotificationChannel


T = TypeVar("T", bound="ListNotificationChannelsResponse200")


@_attrs_define
class ListNotificationChannelsResponse200:
    """
    Attributes:
        items (list[NotificationChannel]):
    """

    items: list[NotificationChannel]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        items = []
        for items_item_data in self.items:
            items_item = items_item_data.to_dict()
            items.append(items_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "items": items,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.notification_channel import NotificationChannel

        d = dict(src_dict)
        items = []
        _items = d.pop("items")
        for items_item_data in _items:
            items_item = NotificationChannel.from_dict(items_item_data)

            items.append(items_item)

        list_notification_channels_response_200 = cls(
            items=items,
        )

        list_notification_channels_response_200.additional_properties = d
        return list_notification_channels_response_200

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
