from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define

if TYPE_CHECKING:
    from ..models.run_config_policy import RunConfigPolicy
    from ..models.run_config_train import RunConfigTrain


T = TypeVar("T", bound="RunConfig")


@_attrs_define
class RunConfig:
    """
    Attributes:
        policy (RunConfigPolicy): Validated against api/policy-schemas/<policy_type>.json (only fields that differ from
            defaults need be sent)
        train (RunConfigTrain): Validated against api/policy-schemas/train.json
    """

    policy: RunConfigPolicy
    train: RunConfigTrain

    def to_dict(self) -> dict[str, Any]:
        policy = self.policy.to_dict()

        train = self.train.to_dict()

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "policy": policy,
                "train": train,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.run_config_policy import RunConfigPolicy
        from ..models.run_config_train import RunConfigTrain

        d = dict(src_dict)
        policy = RunConfigPolicy.from_dict(d.pop("policy"))

        train = RunConfigTrain.from_dict(d.pop("train"))

        run_config = cls(
            policy=policy,
            train=train,
        )

        return run_config
