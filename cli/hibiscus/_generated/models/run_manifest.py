from __future__ import annotations

from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    cast,
)
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.mixed_precision import MixedPrecision
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.run_config import RunConfig
    from ..models.run_manifest_attempts_item import RunManifestAttemptsItem
    from ..models.run_manifest_dataset import RunManifestDataset
    from ..models.run_manifest_gpu import RunManifestGpu


T = TypeVar("T", bound="RunManifest")


@_attrs_define
class RunManifest:
    """Written by the worker at preparing (and finalised at succeeded); also embedded in MANIFEST.json.

    Attributes:
        schema_version (Literal['1']):
        run_id (UUID):
        lerobot_version (str):
        torch_version (str):
        cuda_version (str):
        python_version (str):
        image_digest (str):
        gpu (RunManifestGpu):
        dataset (RunManifestDataset):
        seed (int):
        heldout_episodes (list[int]):
        train_episodes (list[int]):
        lerobot_args (list[str]):
        config (RunConfig):
        attempts (list[RunManifestAttemptsItem] | Unset):
        hibiscus_version (str | Unset):
        mixed_precision (MixedPrecision | Unset):
    """

    schema_version: Literal["1"]
    run_id: UUID
    lerobot_version: str
    torch_version: str
    cuda_version: str
    python_version: str
    image_digest: str
    gpu: RunManifestGpu
    dataset: RunManifestDataset
    seed: int
    heldout_episodes: list[int]
    train_episodes: list[int]
    lerobot_args: list[str]
    config: RunConfig
    attempts: list[RunManifestAttemptsItem] | Unset = UNSET
    hibiscus_version: str | Unset = UNSET
    mixed_precision: MixedPrecision | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        schema_version = self.schema_version

        run_id = str(self.run_id)

        lerobot_version = self.lerobot_version

        torch_version = self.torch_version

        cuda_version = self.cuda_version

        python_version = self.python_version

        image_digest = self.image_digest

        gpu = self.gpu.to_dict()

        dataset = self.dataset.to_dict()

        seed = self.seed

        heldout_episodes = self.heldout_episodes

        train_episodes = self.train_episodes

        lerobot_args = self.lerobot_args

        config = self.config.to_dict()

        attempts: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.attempts, Unset):
            attempts = []
            for attempts_item_data in self.attempts:
                attempts_item = attempts_item_data.to_dict()
                attempts.append(attempts_item)

        hibiscus_version = self.hibiscus_version

        mixed_precision: str | Unset = UNSET
        if not isinstance(self.mixed_precision, Unset):
            mixed_precision = self.mixed_precision.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "schema_version": schema_version,
                "run_id": run_id,
                "lerobot_version": lerobot_version,
                "torch_version": torch_version,
                "cuda_version": cuda_version,
                "python_version": python_version,
                "image_digest": image_digest,
                "gpu": gpu,
                "dataset": dataset,
                "seed": seed,
                "heldout_episodes": heldout_episodes,
                "train_episodes": train_episodes,
                "lerobot_args": lerobot_args,
                "config": config,
            }
        )
        if attempts is not UNSET:
            field_dict["attempts"] = attempts
        if hibiscus_version is not UNSET:
            field_dict["hibiscus_version"] = hibiscus_version
        if mixed_precision is not UNSET:
            field_dict["mixed_precision"] = mixed_precision

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.run_config import RunConfig
        from ..models.run_manifest_attempts_item import RunManifestAttemptsItem
        from ..models.run_manifest_dataset import RunManifestDataset
        from ..models.run_manifest_gpu import RunManifestGpu

        d = dict(src_dict)
        schema_version = cast(Literal["1"], d.pop("schema_version"))
        if schema_version != "1":
            raise ValueError(
                f"schema_version must match const '1', got '{schema_version}'"
            )

        run_id = UUID(d.pop("run_id"))

        lerobot_version = d.pop("lerobot_version")

        torch_version = d.pop("torch_version")

        cuda_version = d.pop("cuda_version")

        python_version = d.pop("python_version")

        image_digest = d.pop("image_digest")

        gpu = RunManifestGpu.from_dict(d.pop("gpu"))

        dataset = RunManifestDataset.from_dict(d.pop("dataset"))

        seed = d.pop("seed")

        heldout_episodes = cast(list[int], d.pop("heldout_episodes"))

        train_episodes = cast(list[int], d.pop("train_episodes"))

        lerobot_args = cast(list[str], d.pop("lerobot_args"))

        config = RunConfig.from_dict(d.pop("config"))

        _attempts = d.pop("attempts", UNSET)
        attempts: list[RunManifestAttemptsItem] | Unset = UNSET
        if _attempts is not UNSET:
            attempts = []
            for attempts_item_data in _attempts:
                attempts_item = RunManifestAttemptsItem.from_dict(attempts_item_data)

                attempts.append(attempts_item)

        hibiscus_version = d.pop("hibiscus_version", UNSET)

        _mixed_precision = d.pop("mixed_precision", UNSET)
        mixed_precision: MixedPrecision | Unset
        if isinstance(_mixed_precision, Unset):
            mixed_precision = UNSET
        else:
            mixed_precision = MixedPrecision(_mixed_precision)

        run_manifest = cls(
            schema_version=schema_version,
            run_id=run_id,
            lerobot_version=lerobot_version,
            torch_version=torch_version,
            cuda_version=cuda_version,
            python_version=python_version,
            image_digest=image_digest,
            gpu=gpu,
            dataset=dataset,
            seed=seed,
            heldout_episodes=heldout_episodes,
            train_episodes=train_episodes,
            lerobot_args=lerobot_args,
            config=config,
            attempts=attempts,
            hibiscus_version=hibiscus_version,
            mixed_precision=mixed_precision,
        )

        run_manifest.additional_properties = d
        return run_manifest

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
