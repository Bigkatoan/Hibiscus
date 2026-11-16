from __future__ import annotations

from collections.abc import Mapping
from typing import (
    Any,
    Literal,
    TypeVar,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.run_status import RunStatus

T = TypeVar("T", bound="EndEvent")


@_attrs_define
class EndEvent:
    """
    Attributes:
        kind (Literal['end']):
        final_status (RunStatus): State machine in docs/spec/run-lifecycle.md
    """

    kind: Literal["end"]
    final_status: RunStatus
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        kind = self.kind

        final_status = self.final_status.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "kind": kind,
                "final_status": final_status,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        kind = cast(Literal["end"], d.pop("kind"))
        if kind != "end":
            raise ValueError(f"kind must match const 'end', got '{kind}'")

        final_status = RunStatus(d.pop("final_status"))

        end_event = cls(
            kind=kind,
            final_status=final_status,
        )

        end_event.additional_properties = d
        return end_event

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
