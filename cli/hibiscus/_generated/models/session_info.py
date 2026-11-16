from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="SessionInfo")


@_attrs_define
class SessionInfo:
    """
    Attributes:
        id (UUID): Session family id
        created_at (datetime.datetime):
        last_used_at (datetime.datetime):
        expires_at (datetime.datetime):
        current (bool):
        mfa_verified (bool):
        ip (None | str | Unset):
        user_agent (None | str | Unset):
    """

    id: UUID
    created_at: datetime.datetime
    last_used_at: datetime.datetime
    expires_at: datetime.datetime
    current: bool
    mfa_verified: bool
    ip: None | str | Unset = UNSET
    user_agent: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        created_at = self.created_at.isoformat()

        last_used_at = self.last_used_at.isoformat()

        expires_at = self.expires_at.isoformat()

        current = self.current

        mfa_verified = self.mfa_verified

        ip: None | str | Unset
        if isinstance(self.ip, Unset):
            ip = UNSET
        else:
            ip = self.ip

        user_agent: None | str | Unset
        if isinstance(self.user_agent, Unset):
            user_agent = UNSET
        else:
            user_agent = self.user_agent

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "created_at": created_at,
                "last_used_at": last_used_at,
                "expires_at": expires_at,
                "current": current,
                "mfa_verified": mfa_verified,
            }
        )
        if ip is not UNSET:
            field_dict["ip"] = ip
        if user_agent is not UNSET:
            field_dict["user_agent"] = user_agent

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        created_at = isoparse(d.pop("created_at"))

        last_used_at = isoparse(d.pop("last_used_at"))

        expires_at = isoparse(d.pop("expires_at"))

        current = d.pop("current")

        mfa_verified = d.pop("mfa_verified")

        def _parse_ip(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ip = _parse_ip(d.pop("ip", UNSET))

        def _parse_user_agent(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_agent = _parse_user_agent(d.pop("user_agent", UNSET))

        session_info = cls(
            id=id,
            created_at=created_at,
            last_used_at=last_used_at,
            expires_at=expires_at,
            current=current,
            mfa_verified=mfa_verified,
            ip=ip,
            user_agent=user_agent,
        )

        session_info.additional_properties = d
        return session_info

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
