from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.validation_summary_result import ValidationSummaryResult

T = TypeVar("T", bound="ValidationSummary")


@_attrs_define
class ValidationSummary:
    """
    Attributes:
        result (ValidationSummaryResult):
        errors (int):
        warnings (int):
    """

    result: ValidationSummaryResult
    errors: int
    warnings: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = self.result.value

        errors = self.errors

        warnings = self.warnings

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "result": result,
                "errors": errors,
                "warnings": warnings,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        result = ValidationSummaryResult(d.pop("result"))

        errors = d.pop("errors")

        warnings = d.pop("warnings")

        validation_summary = cls(
            result=result,
            errors=errors,
            warnings=warnings,
        )

        validation_summary.additional_properties = d
        return validation_summary

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
