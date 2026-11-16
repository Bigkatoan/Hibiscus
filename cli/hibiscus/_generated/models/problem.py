from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.error_code import ErrorCode
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.field_error import FieldError
    from ..models.problem_params import ProblemParams


T = TypeVar("T", bound="Problem")


@_attrs_define
class Problem:
    """RFC 9457 problem details. `type` = `https://robot.example.com/problems/<code>`.

    Attributes:
        type_ (str):
        title (str): Short English summary (stable per code)
        status (int):
        code (ErrorCode): Stable error catalogue (HTTP status in brackets). New codes require a contract bump.
            General: bad_request [400], validation_failed [422], unauthenticated [401], token_expired [401],
            forbidden [403], insufficient_scope [403], csrf_failed [403], not_found [404], conflict [409],
            gone [410], length_required [411], payload_too_large [413], unsupported_media_type [415],
            range_not_satisfiable [416], rate_limited [429], internal_error [500], service_unavailable [503].
            An operation this server does not run answers HTTP 501 with code service_unavailable and
            `params.reason = feature_disabled` (`FeatureDisabled` response).
            Auth: invalid_credentials [401], account_locked [423], account_disabled [403],
            email_not_verified [403], mfa_invalid_code [401], mfa_token_invalid [401],
            mfa_enrollment_required [403], mfa_required_by_role [409], mfa_already_enabled [409],
            mfa_reauth_required [403], turnstile_failed [400], refresh_reuse_detected [401],
            session_revoked [401], token_revoked [401], password_too_weak [422], password_breached [422],
            password_incorrect [401], one_time_token_invalid [400], invite_invalid [404], invite_expired [410],
            invite_email_mismatch [403], email_taken [409].
            Workspaces: workspace_slug_taken [409], workspace_not_empty [409], last_owner [409],
            member_exists [409], quota_exceeded [403].
            Datasets/uploads: dataset_name_taken [409], dataset_in_use [409], dataset_version_not_ready [409],
            dataset_version_duplicate [409], dataset_schema_mismatch [422], hf_uri_invalid [422],
            hf_token_missing [409], upload_not_active [409], upload_incomplete [409],
            upload_part_out_of_range [422], upload_part_size_invalid [422], upload_part_checksum_mismatch [422],
            upload_too_large [413], archive_format_unsupported [422].
            Runs: policy_unknown [404], policy_not_trainable [422], policy_config_invalid [422],
            policy_requires_peft [422], preflight_failed [422], gpu_unknown [422],
            gpu_insufficient_vram [422], run_invalid_transition [409], run_not_resumable [409],
            checkpoint_not_found [404].
            Models/jobs: model_not_ready [409], hub_repo_invalid [422], job_not_cancellable [409].
        request_id (str):
        detail (str | Unset): English
        instance (str | Unset): Request path
        errors (list[FieldError] | Unset): Field errors for `validation_failed` (and `preflight_failed` blockers)
        retry_after_s (int | Unset):
        missing_parts (list[int] | Unset): For `upload_incomplete`
        params (ProblemParams | Unset): Interpolation params for the localised message, e.g. {"limit_gb": 50}
    """

    type_: str
    title: str
    status: int
    code: ErrorCode
    request_id: str
    detail: str | Unset = UNSET
    instance: str | Unset = UNSET
    errors: list[FieldError] | Unset = UNSET
    retry_after_s: int | Unset = UNSET
    missing_parts: list[int] | Unset = UNSET
    params: ProblemParams | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        type_ = self.type_

        title = self.title

        status = self.status

        code = self.code.value

        request_id = self.request_id

        detail = self.detail

        instance = self.instance

        errors: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.errors, Unset):
            errors = []
            for errors_item_data in self.errors:
                errors_item = errors_item_data.to_dict()
                errors.append(errors_item)

        retry_after_s = self.retry_after_s

        missing_parts: list[int] | Unset = UNSET
        if not isinstance(self.missing_parts, Unset):
            missing_parts = self.missing_parts

        params: dict[str, Any] | Unset = UNSET
        if not isinstance(self.params, Unset):
            params = self.params.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "type": type_,
                "title": title,
                "status": status,
                "code": code,
                "request_id": request_id,
            }
        )
        if detail is not UNSET:
            field_dict["detail"] = detail
        if instance is not UNSET:
            field_dict["instance"] = instance
        if errors is not UNSET:
            field_dict["errors"] = errors
        if retry_after_s is not UNSET:
            field_dict["retry_after_s"] = retry_after_s
        if missing_parts is not UNSET:
            field_dict["missing_parts"] = missing_parts
        if params is not UNSET:
            field_dict["params"] = params

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.field_error import FieldError
        from ..models.problem_params import ProblemParams

        d = dict(src_dict)
        type_ = d.pop("type")

        title = d.pop("title")

        status = d.pop("status")

        code = ErrorCode(d.pop("code"))

        request_id = d.pop("request_id")

        detail = d.pop("detail", UNSET)

        instance = d.pop("instance", UNSET)

        _errors = d.pop("errors", UNSET)
        errors: list[FieldError] | Unset = UNSET
        if _errors is not UNSET:
            errors = []
            for errors_item_data in _errors:
                errors_item = FieldError.from_dict(errors_item_data)

                errors.append(errors_item)

        retry_after_s = d.pop("retry_after_s", UNSET)

        missing_parts = cast(list[int], d.pop("missing_parts", UNSET))

        _params = d.pop("params", UNSET)
        params: ProblemParams | Unset
        if isinstance(_params, Unset):
            params = UNSET
        else:
            params = ProblemParams.from_dict(_params)

        problem = cls(
            type_=type_,
            title=title,
            status=status,
            code=code,
            request_id=request_id,
            detail=detail,
            instance=instance,
            errors=errors,
            retry_after_s=retry_after_s,
            missing_parts=missing_parts,
            params=params,
        )

        problem.additional_properties = d
        return problem

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
