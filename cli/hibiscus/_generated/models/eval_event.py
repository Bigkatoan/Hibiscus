from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="EvalEvent")


@_attrs_define
class EvalEvent:
    """
    Attributes:
        kind (Literal['eval']):
        step (int):
        ts (datetime.datetime):
        action_mae (float | Unset):
        action_mse (float | Unset):
    """

    kind: Literal["eval"]
    step: int
    ts: datetime.datetime
    action_mae: float | Unset = UNSET
    action_mse: float | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        kind = self.kind

        step = self.step

        ts = self.ts.isoformat()

        action_mae = self.action_mae

        action_mse = self.action_mse

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "kind": kind,
                "step": step,
                "ts": ts,
            }
        )
        if action_mae is not UNSET:
            field_dict["action_mae"] = action_mae
        if action_mse is not UNSET:
            field_dict["action_mse"] = action_mse

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        kind = cast(Literal["eval"], d.pop("kind"))
        if kind != "eval":
            raise ValueError(f"kind must match const 'eval', got '{kind}'")

        step = d.pop("step")

        ts = isoparse(d.pop("ts"))

        action_mae = d.pop("action_mae", UNSET)

        action_mse = d.pop("action_mse", UNSET)

        eval_event = cls(
            kind=kind,
            step=step,
            ts=ts,
            action_mae=action_mae,
            action_mse=action_mse,
        )

        eval_event.additional_properties = d
        return eval_event

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
