from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.dataset import Dataset
    from ..models.dataset_version_summary import DatasetVersionSummary
    from ..models.job import Job
    from ..models.upload_session import UploadSession


T = TypeVar("T", bound="UploadCompleted")


@_attrs_define
class UploadCompleted:
    """
    Attributes:
        upload (UploadSession):
        dataset (Dataset):
        version (DatasetVersionSummary):
        job (Job):
    """

    upload: UploadSession
    dataset: Dataset
    version: DatasetVersionSummary
    job: Job
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        upload = self.upload.to_dict()

        dataset = self.dataset.to_dict()

        version = self.version.to_dict()

        job = self.job.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "upload": upload,
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
        from ..models.upload_session import UploadSession

        d = dict(src_dict)
        upload = UploadSession.from_dict(d.pop("upload"))

        dataset = Dataset.from_dict(d.pop("dataset"))

        version = DatasetVersionSummary.from_dict(d.pop("version"))

        job = Job.from_dict(d.pop("job"))

        upload_completed = cls(
            upload=upload,
            dataset=dataset,
            version=version,
            job=job,
        )

        upload_completed.additional_properties = d
        return upload_completed

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
