from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
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
        name (str | Unset):
        preset (None | RunCreatePresetType1 | RunCreatePresetType2Type1 | RunCreatePresetType3Type1 | Unset):
        heldout_fraction (float | Unset):  Default: 0.1.
        heldout_episodes (list[int] | None | Unset): Explicit held-out episode indices (overrides heldout_fraction)
        gpu (str | Unset): `auto` or a GpuNode.id (e.g. cuda0) Default: 'auto'.
        priority (int | Unset): > 0 requires workspace admin Default: 0.
        init_from (Any | None | Unset):
        export (ExportOptions | Unset):
        seed (int | None | Unset): null => train.seed default (1000)
    """

    workspace_id: UUID
    dataset_version_id: UUID
    policy_type: PolicyType
    config: RunConfig
    name: str | Unset = UNSET
    preset: (
        None
        | RunCreatePresetType1
        | RunCreatePresetType2Type1
        | RunCreatePresetType3Type1
        | Unset
    ) = UNSET
    heldout_fraction: float | Unset = 0.1
    heldout_episodes: list[int] | None | Unset = UNSET
    gpu: str | Unset = "auto"
    priority: int | Unset = 0
    init_from: Any | None | Unset = UNSET
    export: ExportOptions | Unset = UNSET
    seed: int | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        workspace_id = str(self.workspace_id)

        dataset_version_id = str(self.dataset_version_id)

        policy_type = self.policy_type.value

        config = self.config.to_dict()

        name = self.name

        preset: None | str | Unset
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

        heldout_episodes: list[int] | None | Unset
        if isinstance(self.heldout_episodes, Unset):
            heldout_episodes = UNSET
        elif isinstance(self.heldout_episodes, list):
            heldout_episodes = self.heldout_episodes

        else:
            heldout_episodes = self.heldout_episodes

        gpu = self.gpu

        priority = self.priority

        init_from: Any | None | Unset
        if isinstance(self.init_from, Unset):
            init_from = UNSET
        else:
            init_from = self.init_from

        export: dict[str, Any] | Unset = UNSET
        if not isinstance(self.export, Unset):
            export = self.export.to_dict()

        seed: int | None | Unset
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
        ) -> (
            None
            | RunCreatePresetType1
            | RunCreatePresetType2Type1
            | RunCreatePresetType3Type1
            | Unset
        ):
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                preset_type_1 = RunCreatePresetType1(data)

                return preset_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, str):
                    raise TypeError()
                preset_type_2_type_1 = RunCreatePresetType2Type1(data)

                return preset_type_2_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, str):
                    raise TypeError()
                preset_type_3_type_1 = RunCreatePresetType3Type1(data)

                return preset_type_3_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                None
                | RunCreatePresetType1
                | RunCreatePresetType2Type1
                | RunCreatePresetType3Type1
                | Unset,
                data,
            )

        preset = _parse_preset(d.pop("preset", UNSET))

        heldout_fraction = d.pop("heldout_fraction", UNSET)

        def _parse_heldout_episodes(data: object) -> list[int] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                heldout_episodes_type_0 = cast(list[int], data)

                return heldout_episodes_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[int] | None | Unset, data)

        heldout_episodes = _parse_heldout_episodes(d.pop("heldout_episodes", UNSET))

        gpu = d.pop("gpu", UNSET)

        priority = d.pop("priority", UNSET)

        def _parse_init_from(data: object) -> Any | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Any | None | Unset, data)

        init_from = _parse_init_from(d.pop("init_from", UNSET))

        _export = d.pop("export", UNSET)
        export: ExportOptions | Unset
        if isinstance(_export, Unset):
            export = UNSET
        else:
            export = ExportOptions.from_dict(_export)

        def _parse_seed(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

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
