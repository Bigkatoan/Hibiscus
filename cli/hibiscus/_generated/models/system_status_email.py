from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.system_status_email_provider import SystemStatusEmailProvider

T = TypeVar("T", bound="SystemStatusEmail")


@_attrs_define
class SystemStatusEmail:
    """
    Attributes:
        provider (SystemStatusEmailProvider):
        enabled (bool):
    """

    provider: SystemStatusEmailProvider
    enabled: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        provider = self.provider.value

        enabled = self.enabled

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "provider": provider,
                "enabled": enabled,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        provider = SystemStatusEmailProvider(d.pop("provider"))

        enabled = d.pop("enabled")

        system_status_email = cls(
            provider=provider,
            enabled=enabled,
        )

        system_status_email.additional_properties = d
        return system_status_email

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
