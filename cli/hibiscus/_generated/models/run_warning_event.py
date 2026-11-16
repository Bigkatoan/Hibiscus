from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.run_warning_event_code import RunWarningEventCode
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.run_warning_event_params import RunWarningEventParams


T = TypeVar("T", bound="RunWarningEvent")


@_attrs_define
class RunWarningEvent:
    """
    Attributes:
        kind (Literal['warning']):
        code (RunWarningEventCode):
        message (str):
        ts (datetime.datetime):
        params (RunWarningEventParams | Unset):
    """

    kind: Literal["warning"]
    code: RunWarningEventCode
    message: str
    ts: datetime.datetime
    params: RunWarningEventParams | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        kind = self.kind

        code = self.code.value

        message = self.message

        ts = self.ts.isoformat()

        params: dict[str, Any] | Unset = UNSET
        if not isinstance(self.params, Unset):
            params = self.params.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "kind": kind,
                "code": code,
                "message": message,
                "ts": ts,
            }
        )
        if params is not UNSET:
            field_dict["params"] = params

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.run_warning_event_params import RunWarningEventParams

        d = dict(src_dict)
        kind = cast(Literal["warning"], d.pop("kind"))
        if kind != "warning":
            raise ValueError(f"kind must match const 'warning', got '{kind}'")

        code = RunWarningEventCode(d.pop("code"))

        message = d.pop("message")

        ts = isoparse(d.pop("ts"))

        _params = d.pop("params", UNSET)
        params: RunWarningEventParams | Unset
        if isinstance(_params, Unset):
            params = UNSET
        else:
            params = RunWarningEventParams.from_dict(_params)

        run_warning_event = cls(
            kind=kind,
            code=code,
            message=message,
            ts=ts,
            params=params,
        )

        run_warning_event.additional_properties = d
        return run_warning_event

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
