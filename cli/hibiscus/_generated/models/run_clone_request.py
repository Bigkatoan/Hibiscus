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

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.export_options import ExportOptions
    from ..models.run_clone_request_config import RunCloneRequestConfig


T = TypeVar("T", bound="RunCloneRequest")


@_attrs_define
class RunCloneRequest:
    """
    Attributes:
        name (Union[Unset, str]):
        dataset_version_id (Union[Unset, UUID]):
        config (Union[Unset, RunCloneRequestConfig]): Deep-merged into the source config
            ({"policy":{...},"train":{...}})
        heldout_fraction (Union[Unset, float]):
        gpu (Union[Unset, str]):
        priority (Union[Unset, int]):
        init_from (Union[Any, None, Unset]):
        export (Union[Unset, ExportOptions]):
    """

    name: Union[Unset, str] = UNSET
    dataset_version_id: Union[Unset, UUID] = UNSET
    config: Union[Unset, "RunCloneRequestConfig"] = UNSET
    heldout_fraction: Union[Unset, float] = UNSET
    gpu: Union[Unset, str] = UNSET
    priority: Union[Unset, int] = UNSET
    init_from: Union[Any, None, Unset] = UNSET
    export: Union[Unset, "ExportOptions"] = UNSET

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        dataset_version_id: Union[Unset, str] = UNSET
        if not isinstance(self.dataset_version_id, Unset):
            dataset_version_id = str(self.dataset_version_id)

        config: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.config, Unset):
            config = self.config.to_dict()

        heldout_fraction = self.heldout_fraction

        gpu = self.gpu

        priority = self.priority

        init_from: Union[Any, None, Unset]
        if isinstance(self.init_from, Unset):
            init_from = UNSET
        else:
            init_from = self.init_from

        export: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.export, Unset):
            export = self.export.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if dataset_version_id is not UNSET:
            field_dict["dataset_version_id"] = dataset_version_id
        if config is not UNSET:
            field_dict["config"] = config
        if heldout_fraction is not UNSET:
            field_dict["heldout_fraction"] = heldout_fraction
        if gpu is not UNSET:
            field_dict["gpu"] = gpu
        if priority is not UNSET:
            field_dict["priority"] = priority
        if init_from is not UNSET:
            field_dict["init_from"] = init_from
        if export is not UNSET:
            field_dict["export"] = export

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.export_options import ExportOptions
        from ..models.run_clone_request_config import RunCloneRequestConfig

        d = dict(src_dict)
        name = d.pop("name", UNSET)

        _dataset_version_id = d.pop("dataset_version_id", UNSET)
        dataset_version_id: Union[Unset, UUID]
        if isinstance(_dataset_version_id, Unset):
            dataset_version_id = UNSET
        else:
            dataset_version_id = UUID(_dataset_version_id)

        _config = d.pop("config", UNSET)
        config: Union[Unset, RunCloneRequestConfig]
        if isinstance(_config, Unset):
            config = UNSET
        else:
            config = RunCloneRequestConfig.from_dict(_config)

        heldout_fraction = d.pop("heldout_fraction", UNSET)

        gpu = d.pop("gpu", UNSET)

        priority = d.pop("priority", UNSET)

        def _parse_init_from(data: object) -> Union[Any, None, Unset]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[Any, None, Unset], data)

        init_from = _parse_init_from(d.pop("init_from", UNSET))

        _export = d.pop("export", UNSET)
        export: Union[Unset, ExportOptions]
        if isinstance(_export, Unset):
            export = UNSET
        else:
            export = ExportOptions.from_dict(_export)

        run_clone_request = cls(
            name=name,
            dataset_version_id=dataset_version_id,
            config=config,
            heldout_fraction=heldout_fraction,
            gpu=gpu,
            priority=priority,
            init_from=init_from,
            export=export,
        )

        return run_clone_request
