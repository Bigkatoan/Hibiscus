from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="VerificationParityType0")


@_attrs_define
class VerificationParityType0:
    """Summary of onnx/parity_report.json

    Attributes:
        max_abs_diff (float | Unset):
        atol (float | Unset):
        rtol (float | Unset):
        n_samples (int | Unset):
    """

    max_abs_diff: float | Unset = UNSET
    atol: float | Unset = UNSET
    rtol: float | Unset = UNSET
    n_samples: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        max_abs_diff = self.max_abs_diff

        atol = self.atol

        rtol = self.rtol

        n_samples = self.n_samples

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if max_abs_diff is not UNSET:
            field_dict["max_abs_diff"] = max_abs_diff
        if atol is not UNSET:
            field_dict["atol"] = atol
        if rtol is not UNSET:
            field_dict["rtol"] = rtol
        if n_samples is not UNSET:
            field_dict["n_samples"] = n_samples

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        max_abs_diff = d.pop("max_abs_diff", UNSET)

        atol = d.pop("atol", UNSET)

        rtol = d.pop("rtol", UNSET)

        n_samples = d.pop("n_samples", UNSET)

        verification_parity_type_0 = cls(
            max_abs_diff=max_abs_diff,
            atol=atol,
            rtol=rtol,
            n_samples=n_samples,
        )

        verification_parity_type_0.additional_properties = d
        return verification_parity_type_0

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
