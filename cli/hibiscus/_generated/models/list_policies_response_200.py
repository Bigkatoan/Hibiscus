from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.policy_summary import PolicySummary


T = TypeVar("T", bound="ListPoliciesResponse200")


@_attrs_define
class ListPoliciesResponse200:
    """
    Attributes:
        lerobot_version (str):
        items (list[PolicySummary]):
    """

    lerobot_version: str
    items: list[PolicySummary]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        lerobot_version = self.lerobot_version

        items = []
        for items_item_data in self.items:
            items_item = items_item_data.to_dict()
            items.append(items_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "lerobot_version": lerobot_version,
                "items": items,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.policy_summary import PolicySummary

        d = dict(src_dict)
        lerobot_version = d.pop("lerobot_version")

        items = []
        _items = d.pop("items")
        for items_item_data in _items:
            items_item = PolicySummary.from_dict(items_item_data)

            items.append(items_item)

        list_policies_response_200 = cls(
            lerobot_version=lerobot_version,
            items=items,
        )

        list_policies_response_200.additional_properties = d
        return list_policies_response_200

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
