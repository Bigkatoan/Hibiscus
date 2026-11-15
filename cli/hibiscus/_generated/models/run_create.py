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

from ..models.policy_type import PolicyType
from ..models.run_create_preset_type_1 import RunCreatePresetType1
from ..models.run_create_preset_type_2_type_1 import RunCreatePresetType2Type1
from ..models.run_create_preset_type_3_type_1 import RunCreatePresetType3Type1
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.export_options import ExportOptions
    from ..models.run_config import RunConfig


T = TypeVar("T", bound="RunCreate")


@_attrs_define
class RunCreate:
    """
    Attributes:
        workspace_id (UUID):
        dataset_version_id (UUID):
        policy_type (PolicyType):
        config (RunConfig):
        name (Union[Unset, str]):
        preset (Union[None, RunCreatePresetType1, RunCreatePresetType2Type1, RunCreatePresetType3Type1, Unset]):
        heldout_fraction (Union[Unset, float]):  Default: 0.1.
        heldout_episodes (Union[None, Unset, list[int]]): Explicit held-out episode indices (overrides heldout_fraction)
        gpu (Union[Unset, str]): `auto` or a GpuNode.id (e.g. cuda0) Default: 'auto'.
        priority (Union[Unset, int]): > 0 requires workspace admin Default: 0.
        init_from (Union[Any, None, Unset]):
        export (Union[Unset, ExportOptions]):
        seed (Union[None, Unset, int]): null => train.seed default (1000)
    """

    workspace_id: UUID
    dataset_version_id: UUID
    policy_type: PolicyType
    config: "RunConfig"
    name: Union[Unset, str] = UNSET
    preset: Union[
        None,
        RunCreatePresetType1,
        RunCreatePresetType2Type1,
        RunCreatePresetType3Type1,
        Unset,
    ] = UNSET
    heldout_fraction: Union[Unset, float] = 0.1
    heldout_episodes: Union[None, Unset, list[int]] = UNSET
    gpu: Union[Unset, str] = "auto"
    priority: Union[Unset, int] = 0
    init_from: Union[Any, None, Unset] = UNSET
    export: Union[Unset, "ExportOptions"] = UNSET
    seed: Union[None, Unset, int] = UNSET

    def to_dict(self) -> dict[str, Any]:
        workspace_id = str(self.workspace_id)

        dataset_version_id = str(self.dataset_version_id)

        policy_type = self.policy_type.value

        config = self.config.to_dict()

        name = self.name

        preset: Union[None, Unset, str]
        if isinstance(self.preset, Unset):
            preset = UNSET
        elif isinstance(self.preset, RunCreatePresetType1):
            preset = self.preset.value
        elif isinstance(self.preset, RunCreatePresetType2Type1):
            preset = self.preset.value
        elif isinstance(self.preset, RunCreatePresetType3Type1):
            preset = self.preset.value
        else:
            preset = self.preset

        heldout_fraction = self.heldout_fraction

        heldout_episodes: Union[None, Unset, list[int]]
        if isinstance(self.heldout_episodes, Unset):
            heldout_episodes = UNSET
        elif isinstance(self.heldout_episodes, list):
            heldout_episodes = self.heldout_episodes

        else:
            heldout_episodes = self.heldout_episodes

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

        seed: Union[None, Unset, int]
        if isinstance(self.seed, Unset):
            seed = UNSET
        else:
            seed = self.seed

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "workspace_id": workspace_id,
                "dataset_version_id": dataset_version_id,
                "policy_type": policy_type,
                "config": config,
            }
        )
        if name is not UNSET:
            field_dict["name"] = name
        if preset is not UNSET:
            field_dict["preset"] = preset
        if heldout_fraction is not UNSET:
            field_dict["heldout_fraction"] = heldout_fraction
        if heldout_episodes is not UNSET:
            field_dict["heldout_episodes"] = heldout_episodes
        if gpu is not UNSET:
            field_dict["gpu"] = gpu
        if priority is not UNSET:
            field_dict["priority"] = priority
        if init_from is not UNSET:
            field_dict["init_from"] = init_from
        if export is not UNSET:
            field_dict["export"] = export
        if seed is not UNSET:
            field_dict["seed"] = seed

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.export_options import ExportOptions
        from ..models.run_config import RunConfig

        d = dict(src_dict)
        workspace_id = UUID(d.pop("workspace_id"))

        dataset_version_id = UUID(d.pop("dataset_version_id"))

        policy_type = PolicyType(d.pop("policy_type"))

        config = RunConfig.from_dict(d.pop("config"))

        name = d.pop("name", UNSET)

        def _parse_preset(
            data: object,
        ) -> Union[
            None,
            RunCreatePresetType1,
            RunCreatePresetType2Type1,
            RunCreatePresetType3Type1,
            Unset,
        ]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                preset_type_1 = RunCreatePresetType1(data)

                return preset_type_1
            except:  # noqa: E722
                pass
            try:
                if not isinstance(data, str):
                    raise TypeError()
                preset_type_2_type_1 = RunCreatePresetType2Type1(data)

                return preset_type_2_type_1
            except:  # noqa: E722
                pass
            try:
                if not isinstance(data, str):
                    raise TypeError()
                preset_type_3_type_1 = RunCreatePresetType3Type1(data)

                return preset_type_3_type_1
            except:  # noqa: E722
                pass
            return cast(
                Union[
                    None,
                    RunCreatePresetType1,
                    RunCreatePresetType2Type1,
                    RunCreatePresetType3Type1,
                    Unset,
                ],
                data,
            )

        preset = _parse_preset(d.pop("preset", UNSET))

        heldout_fraction = d.pop("heldout_fraction", UNSET)

        def _parse_heldout_episodes(data: object) -> Union[None, Unset, list[int]]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                heldout_episodes_type_0 = cast(list[int], data)

                return heldout_episodes_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, list[int]], data)

        heldout_episodes = _parse_heldout_episodes(d.pop("heldout_episodes", UNSET))

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

        def _parse_seed(data: object) -> Union[None, Unset, int]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, int], data)

        seed = _parse_seed(d.pop("seed", UNSET))

        run_create = cls(
            workspace_id=workspace_id,
            dataset_version_id=dataset_version_id,
            policy_type=policy_type,
            config=config,
            name=name,
            preset=preset,
            heldout_fraction=heldout_fraction,
            heldout_episodes=heldout_episodes,
            gpu=gpu,
            priority=priority,
            init_from=init_from,
            export=export,
            seed=seed,
        )

        return run_create
