from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
)

from attrs import define as _attrs_define

from ..models.workspace_settings_notify_on_item import WorkspaceSettingsNotifyOnItem
from ..types import UNSET, Unset

T = TypeVar("T", bound="WorkspaceSettings")


@_attrs_define
class WorkspaceSettings:
    """
    Attributes:
        default_heldout_fraction (Union[Unset, float]):  Default: 0.1.
        default_gpu (Union[Unset, str]): `auto` or a gpu id Default: 'auto'.
        notify_on (Union[Unset, list[WorkspaceSettingsNotifyOnItem]]):
    """

    default_heldout_fraction: Union[Unset, float] = 0.1
    default_gpu: Union[Unset, str] = "auto"
    notify_on: Union[Unset, list[WorkspaceSettingsNotifyOnItem]] = UNSET

    def to_dict(self) -> dict[str, Any]:
        default_heldout_fraction = self.default_heldout_fraction

        default_gpu = self.default_gpu

        notify_on: Union[Unset, list[str]] = UNSET
        if not isinstance(self.notify_on, Unset):
            notify_on = []
            for notify_on_item_data in self.notify_on:
                notify_on_item = notify_on_item_data.value
                notify_on.append(notify_on_item)

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if default_heldout_fraction is not UNSET:
            field_dict["default_heldout_fraction"] = default_heldout_fraction
        if default_gpu is not UNSET:
            field_dict["default_gpu"] = default_gpu
        if notify_on is not UNSET:
            field_dict["notify_on"] = notify_on

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        default_heldout_fraction = d.pop("default_heldout_fraction", UNSET)

        default_gpu = d.pop("default_gpu", UNSET)

        notify_on = []
        _notify_on = d.pop("notify_on", UNSET)
        for notify_on_item_data in _notify_on or []:
            notify_on_item = WorkspaceSettingsNotifyOnItem(notify_on_item_data)

            notify_on.append(notify_on_item)

        workspace_settings = cls(
            default_heldout_fraction=default_heldout_fraction,
            default_gpu=default_gpu,
            notify_on=notify_on,
        )

        return workspace_settings
