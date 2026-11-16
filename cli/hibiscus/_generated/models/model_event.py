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

from ..models.model_status import ModelStatus
from ..models.onnx_status import OnnxStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="ModelEvent")


@_attrs_define
class ModelEvent:
    """
    Attributes:
        kind (Literal['model']):
        model_id (UUID):
        status (ModelStatus):
        ts (datetime.datetime):
        verified (bool | Unset):
        onnx_status (OnnxStatus | Unset):
    """

    kind: Literal["model"]
    model_id: UUID
    status: ModelStatus
    ts: datetime.datetime
    verified: bool | Unset = UNSET
    onnx_status: OnnxStatus | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        kind = self.kind

        model_id = str(self.model_id)

        status = self.status.value

        ts = self.ts.isoformat()

        verified = self.verified

        onnx_status: str | Unset = UNSET
        if not isinstance(self.onnx_status, Unset):
            onnx_status = self.onnx_status.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "kind": kind,
                "model_id": model_id,
                "status": status,
                "ts": ts,
            }
        )
        if verified is not UNSET:
            field_dict["verified"] = verified
        if onnx_status is not UNSET:
            field_dict["onnx_status"] = onnx_status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        kind = cast(Literal["model"], d.pop("kind"))
        if kind != "model":
            raise ValueError(f"kind must match const 'model', got '{kind}'")

        model_id = UUID(d.pop("model_id"))

        status = ModelStatus(d.pop("status"))

        ts = isoparse(d.pop("ts"))

        verified = d.pop("verified", UNSET)

        _onnx_status = d.pop("onnx_status", UNSET)
        onnx_status: OnnxStatus | Unset
        if isinstance(_onnx_status, Unset):
            onnx_status = UNSET
        else:
            onnx_status = OnnxStatus(_onnx_status)

        model_event = cls(
            kind=kind,
            model_id=model_id,
            status=status,
            ts=ts,
            verified=verified,
            onnx_status=onnx_status,
        )

        model_event.additional_properties = d
        return model_event

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
