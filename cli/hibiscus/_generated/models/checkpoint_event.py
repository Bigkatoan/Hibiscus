from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    cast,
)
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="CheckpointEvent")


@_attrs_define
class CheckpointEvent:
    """
    Attributes:
        kind (Literal['checkpoint']):
        step (int):
        checkpoint_id (UUID):
        ts (datetime.datetime):
        size_bytes (int | Unset):
    """

    kind: Literal["checkpoint"]
    step: int
    checkpoint_id: UUID
    ts: datetime.datetime
    size_bytes: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        kind = self.kind

        step = self.step

        checkpoint_id = str(self.checkpoint_id)

        ts = self.ts.isoformat()

        size_bytes = self.size_bytes

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "kind": kind,
                "step": step,
                "checkpoint_id": checkpoint_id,
                "ts": ts,
            }
        )
        if size_bytes is not UNSET:
            field_dict["size_bytes"] = size_bytes

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        kind = cast(Literal["checkpoint"], d.pop("kind"))
        if kind != "checkpoint":
            raise ValueError(f"kind must match const 'checkpoint', got '{kind}'")

        step = d.pop("step")

        checkpoint_id = UUID(d.pop("checkpoint_id"))

        ts = isoparse(d.pop("ts"))

        size_bytes = d.pop("size_bytes", UNSET)

        checkpoint_event = cls(
            kind=kind,
            step=step,
            checkpoint_id=checkpoint_id,
            ts=ts,
            size_bytes=size_bytes,
        )

        checkpoint_event.additional_properties = d
        return checkpoint_event

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
