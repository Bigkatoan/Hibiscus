from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.dataset import Dataset
    from ..models.dataset_version_summary import DatasetVersionSummary
    from ..models.job import Job


T = TypeVar("T", bound="DatasetVersionAccepted")


@_attrs_define
class DatasetVersionAccepted:
    """
    Attributes:
        dataset (Dataset):
        version (DatasetVersionSummary):
        job (Job):
    """

    dataset: "Dataset"
    version: "DatasetVersionSummary"
    job: "Job"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        dataset = self.dataset.to_dict()

        version = self.version.to_dict()

        job = self.job.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "dataset": dataset,
                "version": version,
                "job": job,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.dataset import Dataset
        from ..models.dataset_version_summary import DatasetVersionSummary
        from ..models.job import Job

        d = dict(src_dict)
        dataset = Dataset.from_dict(d.pop("dataset"))

        version = DatasetVersionSummary.from_dict(d.pop("version"))

        job = Job.from_dict(d.pop("job"))

        dataset_version_accepted = cls(
            dataset=dataset,
            version=version,
            job=job,
        )

        dataset_version_accepted.additional_properties = d
        return dataset_version_accepted

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
