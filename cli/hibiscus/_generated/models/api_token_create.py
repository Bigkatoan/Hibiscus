from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
    cast,
)
from uuid import UUID

from attrs import define as _attrs_define

from ..models.pat_scope import PatScope
from ..types import UNSET, Unset

T = TypeVar("T", bound="ApiTokenCreate")


@_attrs_define
class ApiTokenCreate:
    """
    Attributes:
        name (str):
        workspace_id (UUID):
        scopes (list[PatScope]):
        expires_in_days (Union[None, Unset, int]): null = never expires (UI shows a warning) Default: 90.
    """

    name: str
    workspace_id: UUID
    scopes: list[PatScope]
    expires_in_days: Union[None, Unset, int] = 90

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        workspace_id = str(self.workspace_id)

        scopes = []
        for scopes_item_data in self.scopes:
            scopes_item = scopes_item_data.value
            scopes.append(scopes_item)

        expires_in_days: Union[None, Unset, int]
        if isinstance(self.expires_in_days, Unset):
            expires_in_days = UNSET
        else:
            expires_in_days = self.expires_in_days

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "name": name,
                "workspace_id": workspace_id,
                "scopes": scopes,
            }
        )
        if expires_in_days is not UNSET:
            field_dict["expires_in_days"] = expires_in_days

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        workspace_id = UUID(d.pop("workspace_id"))

        scopes = []
        _scopes = d.pop("scopes")
        for scopes_item_data in _scopes:
            scopes_item = PatScope(scopes_item_data)

            scopes.append(scopes_item)

        def _parse_expires_in_days(data: object) -> Union[None, Unset, int]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, int], data)

        expires_in_days = _parse_expires_in_days(d.pop("expires_in_days", UNSET))

        api_token_create = cls(
            name=name,
            workspace_id=workspace_id,
            scopes=scopes,
            expires_in_days=expires_in_days,
        )

        return api_token_create
