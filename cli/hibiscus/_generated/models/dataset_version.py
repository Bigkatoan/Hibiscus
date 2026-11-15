import datetime
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
from dateutil.parser import isoparse

from ..models.dataset_source import DatasetSource
from ..models.dataset_version_status import DatasetVersionStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.dataset_version_features_type_0 import DatasetVersionFeaturesType0
    from ..models.validation_summary import ValidationSummary


T = TypeVar("T", bound="DatasetVersion")


@_attrs_define
class DatasetVersion:
    """
    Attributes:
        id (UUID):
        dataset_id (UUID):
        version (int):
        status (DatasetVersionStatus):
        source (DatasetSource):
        created_at (datetime.datetime):
        content_hash (Union[None, str]):
        codebase_version (Union[None, str]):
        robot_type (Union[None, str]):
        camera_keys (list[str]):
        features (Union['DatasetVersionFeaturesType0', None]):
        state_dim (Union[None, int]):
        action_dim (Union[None, int]):
        joint_names (list[str]):
        validation_summary (Union['ValidationSummary', None]):
        total_episodes (Union[None, Unset, int]):
        total_frames (Union[None, Unset, int]):
        fps (Union[None, Unset, float]):
        size_bytes (Union[None, Unset, int]):
        source_ref (Union[None, Unset, str]):
        merged_from (Union[None, Unset, list[UUID]]):
        converted_from (Union[None, Unset, str]):
        tasks (Union[Unset, list[str]]):
        error_code (Union[None, Unset, str]): Infra failure code when status=failed (e.g. upload_checksum_mismatch
        ready_at (Union[None, Unset, datetime.datetime]):
    """

    id: UUID
    dataset_id: UUID
    version: int
    status: DatasetVersionStatus
    source: DatasetSource
    created_at: datetime.datetime
    content_hash: Union[None, str]
    codebase_version: Union[None, str]
    robot_type: Union[None, str]
    camera_keys: list[str]
    features: Union["DatasetVersionFeaturesType0", None]
    state_dim: Union[None, int]
    action_dim: Union[None, int]
    joint_names: list[str]
    validation_summary: Union["ValidationSummary", None]
    total_episodes: Union[None, Unset, int] = UNSET
    total_frames: Union[None, Unset, int] = UNSET
    fps: Union[None, Unset, float] = UNSET
    size_bytes: Union[None, Unset, int] = UNSET
    source_ref: Union[None, Unset, str] = UNSET
    merged_from: Union[None, Unset, list[UUID]] = UNSET
    converted_from: Union[None, Unset, str] = UNSET
    tasks: Union[Unset, list[str]] = UNSET
    error_code: Union[None, Unset, str] = UNSET
    ready_at: Union[None, Unset, datetime.datetime] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.dataset_version_features_type_0 import DatasetVersionFeaturesType0
        from ..models.validation_summary import ValidationSummary

        id = str(self.id)

        dataset_id = str(self.dataset_id)

        version = self.version

        status = self.status.value

        source = self.source.value

        created_at = self.created_at.isoformat()

        content_hash: Union[None, str]
        content_hash = self.content_hash

        codebase_version: Union[None, str]
        codebase_version = self.codebase_version

        robot_type: Union[None, str]
        robot_type = self.robot_type

        camera_keys = self.camera_keys

        features: Union[None, dict[str, Any]]
        if isinstance(self.features, DatasetVersionFeaturesType0):
            features = self.features.to_dict()
        else:
            features = self.features

        state_dim: Union[None, int]
        state_dim = self.state_dim

        action_dim: Union[None, int]
        action_dim = self.action_dim

        joint_names = self.joint_names

        validation_summary: Union[None, dict[str, Any]]
        if isinstance(self.validation_summary, ValidationSummary):
            validation_summary = self.validation_summary.to_dict()
        else:
            validation_summary = self.validation_summary

        total_episodes: Union[None, Unset, int]
        if isinstance(self.total_episodes, Unset):
            total_episodes = UNSET
        else:
            total_episodes = self.total_episodes

        total_frames: Union[None, Unset, int]
        if isinstance(self.total_frames, Unset):
            total_frames = UNSET
        else:
            total_frames = self.total_frames

        fps: Union[None, Unset, float]
        if isinstance(self.fps, Unset):
            fps = UNSET
        else:
            fps = self.fps

        size_bytes: Union[None, Unset, int]
        if isinstance(self.size_bytes, Unset):
            size_bytes = UNSET
        else:
            size_bytes = self.size_bytes

        source_ref: Union[None, Unset, str]
        if isinstance(self.source_ref, Unset):
            source_ref = UNSET
        else:
            source_ref = self.source_ref

        merged_from: Union[None, Unset, list[str]]
        if isinstance(self.merged_from, Unset):
            merged_from = UNSET
        elif isinstance(self.merged_from, list):
            merged_from = []
            for merged_from_type_0_item_data in self.merged_from:
                merged_from_type_0_item = str(merged_from_type_0_item_data)
                merged_from.append(merged_from_type_0_item)

        else:
            merged_from = self.merged_from

        converted_from: Union[None, Unset, str]
        if isinstance(self.converted_from, Unset):
            converted_from = UNSET
        else:
            converted_from = self.converted_from

        tasks: Union[Unset, list[str]] = UNSET
        if not isinstance(self.tasks, Unset):
            tasks = self.tasks

        error_code: Union[None, Unset, str]
        if isinstance(self.error_code, Unset):
            error_code = UNSET
        else:
            error_code = self.error_code

        ready_at: Union[None, Unset, str]
        if isinstance(self.ready_at, Unset):
            ready_at = UNSET
        elif isinstance(self.ready_at, datetime.datetime):
            ready_at = self.ready_at.isoformat()
        else:
            ready_at = self.ready_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "dataset_id": dataset_id,
                "version": version,
                "status": status,
                "source": source,
                "created_at": created_at,
                "content_hash": content_hash,
                "codebase_version": codebase_version,
                "robot_type": robot_type,
                "camera_keys": camera_keys,
                "features": features,
                "state_dim": state_dim,
                "action_dim": action_dim,
                "joint_names": joint_names,
                "validation_summary": validation_summary,
            }
        )
        if total_episodes is not UNSET:
            field_dict["total_episodes"] = total_episodes
        if total_frames is not UNSET:
            field_dict["total_frames"] = total_frames
        if fps is not UNSET:
            field_dict["fps"] = fps
        if size_bytes is not UNSET:
            field_dict["size_bytes"] = size_bytes
        if source_ref is not UNSET:
            field_dict["source_ref"] = source_ref
        if merged_from is not UNSET:
            field_dict["merged_from"] = merged_from
        if converted_from is not UNSET:
            field_dict["converted_from"] = converted_from
        if tasks is not UNSET:
            field_dict["tasks"] = tasks
        if error_code is not UNSET:
            field_dict["error_code"] = error_code
        if ready_at is not UNSET:
            field_dict["ready_at"] = ready_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.dataset_version_features_type_0 import DatasetVersionFeaturesType0
        from ..models.validation_summary import ValidationSummary

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        dataset_id = UUID(d.pop("dataset_id"))

        version = d.pop("version")

        status = DatasetVersionStatus(d.pop("status"))

        source = DatasetSource(d.pop("source"))

        created_at = isoparse(d.pop("created_at"))

        def _parse_content_hash(data: object) -> Union[None, str]:
            if data is None:
                return data
            return cast(Union[None, str], data)

        content_hash = _parse_content_hash(d.pop("content_hash"))

        def _parse_codebase_version(data: object) -> Union[None, str]:
            if data is None:
                return data
            return cast(Union[None, str], data)

        codebase_version = _parse_codebase_version(d.pop("codebase_version"))

        def _parse_robot_type(data: object) -> Union[None, str]:
            if data is None:
                return data
            return cast(Union[None, str], data)

        robot_type = _parse_robot_type(d.pop("robot_type"))

        camera_keys = cast(list[str], d.pop("camera_keys"))

        def _parse_features(data: object) -> Union["DatasetVersionFeaturesType0", None]:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                features_type_0 = DatasetVersionFeaturesType0.from_dict(data)

                return features_type_0
            except:  # noqa: E722
                pass
            return cast(Union["DatasetVersionFeaturesType0", None], data)

        features = _parse_features(d.pop("features"))

        def _parse_state_dim(data: object) -> Union[None, int]:
            if data is None:
                return data
            return cast(Union[None, int], data)

        state_dim = _parse_state_dim(d.pop("state_dim"))

        def _parse_action_dim(data: object) -> Union[None, int]:
            if data is None:
                return data
            return cast(Union[None, int], data)

        action_dim = _parse_action_dim(d.pop("action_dim"))

        joint_names = cast(list[str], d.pop("joint_names"))

        def _parse_validation_summary(data: object) -> Union["ValidationSummary", None]:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                validation_summary_type_0 = ValidationSummary.from_dict(data)

                return validation_summary_type_0
            except:  # noqa: E722
                pass
            return cast(Union["ValidationSummary", None], data)

        validation_summary = _parse_validation_summary(d.pop("validation_summary"))

        def _parse_total_episodes(data: object) -> Union[None, Unset, int]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, int], data)

        total_episodes = _parse_total_episodes(d.pop("total_episodes", UNSET))

        def _parse_total_frames(data: object) -> Union[None, Unset, int]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, int], data)

        total_frames = _parse_total_frames(d.pop("total_frames", UNSET))

        def _parse_fps(data: object) -> Union[None, Unset, float]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, float], data)

        fps = _parse_fps(d.pop("fps", UNSET))

        def _parse_size_bytes(data: object) -> Union[None, Unset, int]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, int], data)

        size_bytes = _parse_size_bytes(d.pop("size_bytes", UNSET))

        def _parse_source_ref(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        source_ref = _parse_source_ref(d.pop("source_ref", UNSET))

        def _parse_merged_from(data: object) -> Union[None, Unset, list[UUID]]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                merged_from_type_0 = []
                _merged_from_type_0 = data
                for merged_from_type_0_item_data in _merged_from_type_0:
                    merged_from_type_0_item = UUID(merged_from_type_0_item_data)

                    merged_from_type_0.append(merged_from_type_0_item)

                return merged_from_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, list[UUID]], data)

        merged_from = _parse_merged_from(d.pop("merged_from", UNSET))

        def _parse_converted_from(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        converted_from = _parse_converted_from(d.pop("converted_from", UNSET))

        tasks = cast(list[str], d.pop("tasks", UNSET))

        def _parse_error_code(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        error_code = _parse_error_code(d.pop("error_code", UNSET))

        def _parse_ready_at(data: object) -> Union[None, Unset, datetime.datetime]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                ready_at_type_0 = isoparse(data)

                return ready_at_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, datetime.datetime], data)

        ready_at = _parse_ready_at(d.pop("ready_at", UNSET))

        dataset_version = cls(
            id=id,
            dataset_id=dataset_id,
            version=version,
            status=status,
            source=source,
            created_at=created_at,
            content_hash=content_hash,
            codebase_version=codebase_version,
            robot_type=robot_type,
            camera_keys=camera_keys,
            features=features,
            state_dim=state_dim,
            action_dim=action_dim,
            joint_names=joint_names,
            validation_summary=validation_summary,
            total_episodes=total_episodes,
            total_frames=total_frames,
            fps=fps,
            size_bytes=size_bytes,
            source_ref=source_ref,
            merged_from=merged_from,
            converted_from=converted_from,
            tasks=tasks,
            error_code=error_code,
            ready_at=ready_at,
        )

        dataset_version.additional_properties = d
        return dataset_version

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
