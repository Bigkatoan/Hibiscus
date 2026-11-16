from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ReadinessChecksAdditionalProperty")


@_attrs_define
class ReadinessChecksAdditionalProperty:
    """
    Attributes:
        ok (bool):
        latency_ms (float | Unset):
        detail (str | Unset):
    """

    ok: bool
    latency_ms: float | Unset = UNSET
    detail: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ok = self.ok

        latency_ms = self.latency_ms

        detail = self.detail

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "ok": ok,
            }
        )
        if latency_ms is not UNSET:
            field_dict["latency_ms"] = latency_ms
        if detail is not UNSET:
            field_dict["detail"] = detail

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        ok = d.pop("ok")

        latency_ms = d.pop("latency_ms", UNSET)

        detail = d.pop("detail", UNSET)

        readiness_checks_additional_property = cls(
            ok=ok,
            latency_ms=latency_ms,
            detail=detail,
        )

        readiness_checks_additional_property.additional_properties = d
        return readiness_checks_additional_property

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
