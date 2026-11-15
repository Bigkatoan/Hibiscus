import datetime
from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
    cast,
)
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.pat_scope import PatScope
from ..types import UNSET, Unset

T = TypeVar("T", bound="ApiTokenCreated")


@_attrs_define
class ApiTokenCreated:
    """
    Attributes:
        id (UUID):
        name (str):
        prefix (str): Shown as `hbp_<prefix>_…`
        workspace_id (UUID):
        scopes (list[PatScope]):
        created_at (datetime.datetime):
        token (str): Plaintext
        expires_at (Union[None, Unset, datetime.datetime]):
        last_used_at (Union[None, Unset, datetime.datetime]):
        last_used_ip (Union[None, Unset, str]):
        revoked_at (Union[None, Unset, datetime.datetime]):
    """

    id: UUID
    name: str
    prefix: str
    workspace_id: UUID
    scopes: list[PatScope]
    created_at: datetime.datetime
    token: str
    expires_at: Union[None, Unset, datetime.datetime] = UNSET
    last_used_at: Union[None, Unset, datetime.datetime] = UNSET
    last_used_ip: Union[None, Unset, str] = UNSET
    revoked_at: Union[None, Unset, datetime.datetime] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        name = self.name

        prefix = self.prefix

        workspace_id = str(self.workspace_id)

        scopes = []
        for scopes_item_data in self.scopes:
            scopes_item = scopes_item_data.value
            scopes.append(scopes_item)

        created_at = self.created_at.isoformat()

        token = self.token

        expires_at: Union[None, Unset, str]
        if isinstance(self.expires_at, Unset):
            expires_at = UNSET
        elif isinstance(self.expires_at, datetime.datetime):
            expires_at = self.expires_at.isoformat()
        else:
            expires_at = self.expires_at

        last_used_at: Union[None, Unset, str]
        if isinstance(self.last_used_at, Unset):
            last_used_at = UNSET
        elif isinstance(self.last_used_at, datetime.datetime):
            last_used_at = self.last_used_at.isoformat()
        else:
            last_used_at = self.last_used_at

        last_used_ip: Union[None, Unset, str]
        if isinstance(self.last_used_ip, Unset):
            last_used_ip = UNSET
        else:
            last_used_ip = self.last_used_ip

        revoked_at: Union[None, Unset, str]
        if isinstance(self.revoked_at, Unset):
            revoked_at = UNSET
        elif isinstance(self.revoked_at, datetime.datetime):
            revoked_at = self.revoked_at.isoformat()
        else:
            revoked_at = self.revoked_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "name": name,
                "prefix": prefix,
                "workspace_id": workspace_id,
                "scopes": scopes,
                "created_at": created_at,
                "token": token,
            }
        )
        if expires_at is not UNSET:
            field_dict["expires_at"] = expires_at
        if last_used_at is not UNSET:
            field_dict["last_used_at"] = last_used_at
        if last_used_ip is not UNSET:
            field_dict["last_used_ip"] = last_used_ip
        if revoked_at is not UNSET:
            field_dict["revoked_at"] = revoked_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        name = d.pop("name")

        prefix = d.pop("prefix")

        workspace_id = UUID(d.pop("workspace_id"))

        scopes = []
        _scopes = d.pop("scopes")
        for scopes_item_data in _scopes:
            scopes_item = PatScope(scopes_item_data)

            scopes.append(scopes_item)

        created_at = isoparse(d.pop("created_at"))

        token = d.pop("token")

        def _parse_expires_at(data: object) -> Union[None, Unset, datetime.datetime]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                expires_at_type_0 = isoparse(data)

                return expires_at_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, datetime.datetime], data)

        expires_at = _parse_expires_at(d.pop("expires_at", UNSET))

        def _parse_last_used_at(data: object) -> Union[None, Unset, datetime.datetime]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_used_at_type_0 = isoparse(data)

                return last_used_at_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, datetime.datetime], data)

        last_used_at = _parse_last_used_at(d.pop("last_used_at", UNSET))

        def _parse_last_used_ip(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        last_used_ip = _parse_last_used_ip(d.pop("last_used_ip", UNSET))

        def _parse_revoked_at(data: object) -> Union[None, Unset, datetime.datetime]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                revoked_at_type_0 = isoparse(data)

                return revoked_at_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, datetime.datetime], data)

        revoked_at = _parse_revoked_at(d.pop("revoked_at", UNSET))

        api_token_created = cls(
            id=id,
            name=name,
            prefix=prefix,
            workspace_id=workspace_id,
            scopes=scopes,
            created_at=created_at,
            token=token,
            expires_at=expires_at,
            last_used_at=last_used_at,
            last_used_ip=last_used_ip,
            revoked_at=revoked_at,
        )

        api_token_created.additional_properties = d
        return api_token_created

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
