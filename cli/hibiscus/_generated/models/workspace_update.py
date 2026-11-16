from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.workspace_settings import WorkspaceSettings


T = TypeVar("T", bound="WorkspaceUpdate")


@_attrs_define
class WorkspaceUpdate:
    """
    Attributes:
        name (str | Unset):
        settings (WorkspaceSettings | Unset):
    """

    name: str | Unset = UNSET
    settings: WorkspaceSettings | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        settings: dict[str, Any] | Unset = UNSET
        if not isinstance(self.settings, Unset):
            settings = self.settings.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if settings is not UNSET:
            field_dict["settings"] = settings

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.workspace_settings import WorkspaceSettings

        d = dict(src_dict)
        name = d.pop("name", UNSET)

        _settings = d.pop("settings", UNSET)
        settings: WorkspaceSettings | Unset
        if isinstance(_settings, Unset):
            settings = UNSET
        else:
            settings = WorkspaceSettings.from_dict(_settings)

        workspace_update = cls(
            name=name,
            settings=settings,
        )

        return workspace_update
