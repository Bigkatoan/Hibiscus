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

T = TypeVar("T", bound="ProgressEvent")


@_attrs_define
class ProgressEvent:
    """
    Attributes:
        kind (Literal['progress']):
        step (int): initial_step + tqdm n
        total_steps (int):
        ts (datetime.datetime):
        steps_per_s (float | None | Unset):
        eta_s (float | None | Unset):
    """

    kind: Literal["progress"]
    step: int
    total_steps: int
    ts: datetime.datetime
    steps_per_s: float | None | Unset = UNSET
    eta_s: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        kind = self.kind

        step = self.step

        total_steps = self.total_steps

        ts = self.ts.isoformat()

        steps_per_s: float | None | Unset
        if isinstance(self.steps_per_s, Unset):
            steps_per_s = UNSET
        else:
            steps_per_s = self.steps_per_s

        eta_s: float | None | Unset
        if isinstance(self.eta_s, Unset):
            eta_s = UNSET
        else:
            eta_s = self.eta_s

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "kind": kind,
                "step": step,
                "total_steps": total_steps,
                "ts": ts,
            }
        )
        if steps_per_s is not UNSET:
            field_dict["steps_per_s"] = steps_per_s
        if eta_s is not UNSET:
            field_dict["eta_s"] = eta_s

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        kind = cast(Literal["progress"], d.pop("kind"))
        if kind != "progress":
            raise ValueError(f"kind must match const 'progress', got '{kind}'")

        step = d.pop("step")

        total_steps = d.pop("total_steps")

        ts = isoparse(d.pop("ts"))

        def _parse_steps_per_s(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        steps_per_s = _parse_steps_per_s(d.pop("steps_per_s", UNSET))

        def _parse_eta_s(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        eta_s = _parse_eta_s(d.pop("eta_s", UNSET))

        progress_event = cls(
            kind=kind,
            step=step,
            total_steps=total_steps,
            ts=ts,
            steps_per_s=steps_per_s,
            eta_s=eta_s,
        )

        progress_event.additional_properties = d
        return progress_event

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
