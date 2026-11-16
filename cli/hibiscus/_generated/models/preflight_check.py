from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.preflight_check_id import PreflightCheckId
from ..models.validation_severity import ValidationSeverity
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.preflight_check_params import PreflightCheckParams


T = TypeVar("T", bound="PreflightCheck")


@_attrs_define
class PreflightCheck:
    """
    Attributes:
        id (PreflightCheckId):
        severity (ValidationSeverity):
        code (str): ErrorCode for errors; warning code otherwise (e.g. `mixed_precision_forced_no`)
        message (str):
        params (PreflightCheckParams | Unset):
    """

    id: PreflightCheckId
    severity: ValidationSeverity
    code: str
    message: str
    params: PreflightCheckParams | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id.value

        severity = self.severity.value

        code = self.code

        message = self.message

        params: dict[str, Any] | Unset = UNSET
        if not isinstance(self.params, Unset):
            params = self.params.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "severity": severity,
                "code": code,
                "message": message,
            }
        )
        if params is not UNSET:
            field_dict["params"] = params

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.preflight_check_params import PreflightCheckParams

        d = dict(src_dict)
        id = PreflightCheckId(d.pop("id"))

        severity = ValidationSeverity(d.pop("severity"))

        code = d.pop("code")

        message = d.pop("message")

        _params = d.pop("params", UNSET)
        params: PreflightCheckParams | Unset
        if isinstance(_params, Unset):
            params = UNSET
        else:
            params = PreflightCheckParams.from_dict(_params)

        preflight_check = cls(
            id=id,
            severity=severity,
            code=code,
            message=message,
            params=params,
        )

        preflight_check.additional_properties = d
        return preflight_check

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
