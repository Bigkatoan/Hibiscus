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

from ..models.locale import Locale

if TYPE_CHECKING:
    from ..models.membership import Membership


T = TypeVar("T", bound="AdminUser")


@_attrs_define
class AdminUser:
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
        is_active (bool):
        locked_until (Union[None, datetime.datetime]):
        last_login_at (Union[None, datetime.datetime]):
        workspaces (list['Membership']):
    """

    id: UUID
    email: str
    display_name: str
    locale: Locale
    email_verified: bool
    mfa_enabled: bool
    is_platform_admin: bool
    created_at: datetime.datetime
    is_active: bool
    locked_until: Union[None, datetime.datetime]
    last_login_at: Union[None, datetime.datetime]
    workspaces: list["Membership"]
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

        is_active = self.is_active

        locked_until: Union[None, str]
        if isinstance(self.locked_until, datetime.datetime):
            locked_until = self.locked_until.isoformat()
        else:
            locked_until = self.locked_until

        last_login_at: Union[None, str]
        if isinstance(self.last_login_at, datetime.datetime):
            last_login_at = self.last_login_at.isoformat()
        else:
            last_login_at = self.last_login_at

        workspaces = []
        for workspaces_item_data in self.workspaces:
            workspaces_item = workspaces_item_data.to_dict()
            workspaces.append(workspaces_item)

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
                "is_active": is_active,
                "locked_until": locked_until,
                "last_login_at": last_login_at,
                "workspaces": workspaces,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.membership import Membership

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        email = d.pop("email")

        display_name = d.pop("display_name")

        locale = Locale(d.pop("locale"))

        email_verified = d.pop("email_verified")

        mfa_enabled = d.pop("mfa_enabled")

        is_platform_admin = d.pop("is_platform_admin")

        created_at = isoparse(d.pop("created_at"))

        is_active = d.pop("is_active")

        def _parse_locked_until(data: object) -> Union[None, datetime.datetime]:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                locked_until_type_0 = isoparse(data)

                return locked_until_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, datetime.datetime], data)

        locked_until = _parse_locked_until(d.pop("locked_until"))

        def _parse_last_login_at(data: object) -> Union[None, datetime.datetime]:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_login_at_type_0 = isoparse(data)

                return last_login_at_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, datetime.datetime], data)

        last_login_at = _parse_last_login_at(d.pop("last_login_at"))

        workspaces = []
        _workspaces = d.pop("workspaces")
        for workspaces_item_data in _workspaces:
            workspaces_item = Membership.from_dict(workspaces_item_data)

            workspaces.append(workspaces_item)

        admin_user = cls(
            id=id,
            email=email,
            display_name=display_name,
            locale=locale,
            email_verified=email_verified,
            mfa_enabled=mfa_enabled,
            is_platform_admin=is_platform_admin,
            created_at=created_at,
            is_active=is_active,
            locked_until=locked_until,
            last_login_at=last_login_at,
            workspaces=workspaces,
        )

        admin_user.additional_properties = d
        return admin_user

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
