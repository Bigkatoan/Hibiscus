import datetime
from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
)
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.locale import Locale

T = TypeVar("T", bound="User")


@_attrs_define
class User:
    """
    Attributes:
        id (UUID):
        email (str):
        display_name (str):
        locale (Locale):
        email_verified (bool):
        mfa_enabled (bool):
        is_platform_admin (bool):
        created_at (datetime.datetime):
    """

    id: UUID
    email: str
    display_name: str
    locale: Locale
    email_verified: bool
    mfa_enabled: bool
    is_platform_admin: bool
    created_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        email = self.email

        display_name = self.display_name

        locale = self.locale.value

        email_verified = self.email_verified

        mfa_enabled = self.mfa_enabled

        is_platform_admin = self.is_platform_admin

        created_at = self.created_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "email": email,
                "display_name": display_name,
                "locale": locale,
                "email_verified": email_verified,
                "mfa_enabled": mfa_enabled,
                "is_platform_admin": is_platform_admin,
                "created_at": created_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        email = d.pop("email")

        display_name = d.pop("display_name")

        locale = Locale(d.pop("locale"))

        email_verified = d.pop("email_verified")

        mfa_enabled = d.pop("mfa_enabled")

        is_platform_admin = d.pop("is_platform_admin")

        created_at = isoparse(d.pop("created_at"))

        user = cls(
            id=id,
            email=email,
            display_name=display_name,
            locale=locale,
            email_verified=email_verified,
            mfa_enabled=mfa_enabled,
            is_platform_admin=is_platform_admin,
            created_at=created_at,
        )

        user.additional_properties = d
        return user

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
