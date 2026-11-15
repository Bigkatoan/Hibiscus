from collections.abc import Mapping
from typing import (
    Any,
    TypeVar,
    Union,
)

from attrs import define as _attrs_define

from ..models.run_pause_request_mode import RunPauseRequestMode
from ..types import UNSET, Unset

T = TypeVar("T", bound="RunPauseRequest")


@_attrs_define
class RunPauseRequest:
    """
    Attributes:
        mode (Union[Unset, RunPauseRequestMode]):  Default: RunPauseRequestMode.NEXT_CHECKPOINT.
    """

    mode: Union[Unset, RunPauseRequestMode] = RunPauseRequestMode.NEXT_CHECKPOINT

    def to_dict(self) -> dict[str, Any]:
        mode: Union[Unset, str] = UNSET
        if not isinstance(self.mode, Unset):
            mode = self.mode.value

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if mode is not UNSET:
            field_dict["mode"] = mode

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        _mode = d.pop("mode", UNSET)
        mode: Union[Unset, RunPauseRequestMode]
        if isinstance(_mode, Unset):
            mode = UNSET
        else:
            mode = RunPauseRequestMode(_mode)

        run_pause_request = cls(
            mode=mode,
        )

        return run_pause_request
