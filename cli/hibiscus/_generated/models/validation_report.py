from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    Union,
    cast,
)
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.validation_report_recomputed_stats_max_rel_diff_type_0 import (
        ValidationReportRecomputedStatsMaxRelDiffType0,
    )
    from ..models.validation_step import ValidationStep
    from ..models.validation_summary import ValidationSummary


T = TypeVar("T", bound="ValidationReport")


@_attrs_define
class ValidationReport:
    """
    Attributes:
        dataset_version_id (UUID):
        validator_version (str):
        lerobot_version (str):
        summary (ValidationSummary):
        steps (list['ValidationStep']):
        job_id (Union[None, UUID, Unset]):
        recomputed_stats_max_rel_diff (Union['ValidationReportRecomputedStatsMaxRelDiffType0', None, Unset]): feature
            key -> {mean, std, min, max} max relative difference vs stats.json
    """

    dataset_version_id: UUID
    validator_version: str
    lerobot_version: str
    summary: "ValidationSummary"
    steps: list["ValidationStep"]
    job_id: Union[None, UUID, Unset] = UNSET
    recomputed_stats_max_rel_diff: Union[
        "ValidationReportRecomputedStatsMaxRelDiffType0", None, Unset
    ] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.validation_report_recomputed_stats_max_rel_diff_type_0 import (
            ValidationReportRecomputedStatsMaxRelDiffType0,
        )

        dataset_version_id = str(self.dataset_version_id)

        validator_version = self.validator_version

        lerobot_version = self.lerobot_version

        summary = self.summary.to_dict()

        steps = []
        for steps_item_data in self.steps:
            steps_item = steps_item_data.to_dict()
            steps.append(steps_item)

        job_id: Union[None, Unset, str]
        if isinstance(self.job_id, Unset):
            job_id = UNSET
        elif isinstance(self.job_id, UUID):
            job_id = str(self.job_id)
        else:
            job_id = self.job_id

        recomputed_stats_max_rel_diff: Union[None, Unset, dict[str, Any]]
        if isinstance(self.recomputed_stats_max_rel_diff, Unset):
            recomputed_stats_max_rel_diff = UNSET
        elif isinstance(
            self.recomputed_stats_max_rel_diff,
            ValidationReportRecomputedStatsMaxRelDiffType0,
        ):
            recomputed_stats_max_rel_diff = self.recomputed_stats_max_rel_diff.to_dict()
        else:
            recomputed_stats_max_rel_diff = self.recomputed_stats_max_rel_diff

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "dataset_version_id": dataset_version_id,
                "validator_version": validator_version,
                "lerobot_version": lerobot_version,
                "summary": summary,
                "steps": steps,
            }
        )
        if job_id is not UNSET:
            field_dict["job_id"] = job_id
        if recomputed_stats_max_rel_diff is not UNSET:
            field_dict["recomputed_stats_max_rel_diff"] = recomputed_stats_max_rel_diff

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.validation_report_recomputed_stats_max_rel_diff_type_0 import (
            ValidationReportRecomputedStatsMaxRelDiffType0,
        )
        from ..models.validation_step import ValidationStep
        from ..models.validation_summary import ValidationSummary

        d = dict(src_dict)
        dataset_version_id = UUID(d.pop("dataset_version_id"))

        validator_version = d.pop("validator_version")

        lerobot_version = d.pop("lerobot_version")

        summary = ValidationSummary.from_dict(d.pop("summary"))

        steps = []
        _steps = d.pop("steps")
        for steps_item_data in _steps:
            steps_item = ValidationStep.from_dict(steps_item_data)

            steps.append(steps_item)

        def _parse_job_id(data: object) -> Union[None, UUID, Unset]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                job_id_type_0 = UUID(data)

                return job_id_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, UUID, Unset], data)

        job_id = _parse_job_id(d.pop("job_id", UNSET))

        def _parse_recomputed_stats_max_rel_diff(
            data: object,
        ) -> Union["ValidationReportRecomputedStatsMaxRelDiffType0", None, Unset]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                recomputed_stats_max_rel_diff_type_0 = (
                    ValidationReportRecomputedStatsMaxRelDiffType0.from_dict(data)
                )

                return recomputed_stats_max_rel_diff_type_0
            except:  # noqa: E722
                pass
            return cast(
                Union["ValidationReportRecomputedStatsMaxRelDiffType0", None, Unset],
                data,
            )

        recomputed_stats_max_rel_diff = _parse_recomputed_stats_max_rel_diff(
            d.pop("recomputed_stats_max_rel_diff", UNSET)
        )

        validation_report = cls(
            dataset_version_id=dataset_version_id,
            validator_version=validator_version,
            lerobot_version=lerobot_version,
            summary=summary,
            steps=steps,
            job_id=job_id,
            recomputed_stats_max_rel_diff=recomputed_stats_max_rel_diff,
        )

        validation_report.additional_properties = d
        return validation_report

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
