from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.validation_issue_code import ValidationIssueCode
from ..models.validation_severity import ValidationSeverity
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.validation_issue_params import ValidationIssueParams


T = TypeVar("T", bound="ValidationIssue")


@_attrs_define
class ValidationIssue:
    """
    Attributes:
        code (ValidationIssueCode):
        severity (ValidationSeverity):
        message (str): English; UI localises by code + params
        params (ValidationIssueParams | Unset):
        episode_index (int | None | Unset):
        path (None | str | Unset): Path relative to dataset root
        feature (None | str | Unset):
    """

    code: ValidationIssueCode
    severity: ValidationSeverity
    message: str
    params: ValidationIssueParams | Unset = UNSET
    episode_index: int | None | Unset = UNSET
    path: None | str | Unset = UNSET
    feature: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        code = self.code.value

        severity = self.severity.value

        message = self.message

        params: dict[str, Any] | Unset = UNSET
        if not isinstance(self.params, Unset):
            params = self.params.to_dict()

        episode_index: int | None | Unset
        if isinstance(self.episode_index, Unset):
            episode_index = UNSET
        else:
            episode_index = self.episode_index

        path: None | str | Unset
        if isinstance(self.path, Unset):
            path = UNSET
        else:
            path = self.path

        feature: None | str | Unset
        if isinstance(self.feature, Unset):
            feature = UNSET
        else:
            feature = self.feature

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "code": code,
                "severity": severity,
                "message": message,
            }
        )
        if params is not UNSET:
            field_dict["params"] = params
        if episode_index is not UNSET:
            field_dict["episode_index"] = episode_index
        if path is not UNSET:
            field_dict["path"] = path
        if feature is not UNSET:
            field_dict["feature"] = feature

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.validation_issue_params import ValidationIssueParams

        d = dict(src_dict)
        code = ValidationIssueCode(d.pop("code"))

        severity = ValidationSeverity(d.pop("severity"))

        message = d.pop("message")

        _params = d.pop("params", UNSET)
        params: ValidationIssueParams | Unset
        if isinstance(_params, Unset):
            params = UNSET
        else:
            params = ValidationIssueParams.from_dict(_params)

        def _parse_episode_index(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        episode_index = _parse_episode_index(d.pop("episode_index", UNSET))

        def _parse_path(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        path = _parse_path(d.pop("path", UNSET))

        def _parse_feature(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        feature = _parse_feature(d.pop("feature", UNSET))

        validation_issue = cls(
            code=code,
            severity=severity,
            message=message,
            params=params,
            episode_index=episode_index,
            path=path,
            feature=feature,
        )

        validation_issue.additional_properties = d
        return validation_issue

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
