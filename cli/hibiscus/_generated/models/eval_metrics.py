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

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.eval_metrics_overall import EvalMetricsOverall
    from ..models.eval_metrics_per_joint_item import EvalMetricsPerJointItem
    from ..models.eval_metrics_plots_item import EvalMetricsPlotsItem


T = TypeVar("T", bound="EvalMetrics")


@_attrs_define
class EvalMetrics:
    """Same document as bundle `eval/metrics.json` (docs/spec/bundle.md §5)

    Attributes:
        schema_version (Literal['1']):
        run_id (UUID):
        step (int):
        heldout_episodes (list[int]):
        n_frames (int):
        action_names (list[str]):
        overall (EvalMetricsOverall):
        per_joint (list[EvalMetricsPerJointItem]):
        disclaimer_key (Literal['eval.offline_not_success_rate']):
        plots (list[EvalMetricsPlotsItem] | Unset):
    """

    schema_version: Literal["1"]
    run_id: UUID
    step: int
    heldout_episodes: list[int]
    n_frames: int
    action_names: list[str]
    overall: EvalMetricsOverall
    per_joint: list[EvalMetricsPerJointItem]
    disclaimer_key: Literal["eval.offline_not_success_rate"]
    plots: list[EvalMetricsPlotsItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        schema_version = self.schema_version

        run_id = str(self.run_id)

        step = self.step

        heldout_episodes = self.heldout_episodes

        n_frames = self.n_frames

        action_names = self.action_names

        overall = self.overall.to_dict()

        per_joint = []
        for per_joint_item_data in self.per_joint:
            per_joint_item = per_joint_item_data.to_dict()
            per_joint.append(per_joint_item)

        disclaimer_key = self.disclaimer_key

        plots: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.plots, Unset):
            plots = []
            for plots_item_data in self.plots:
                plots_item = plots_item_data.to_dict()
                plots.append(plots_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "schema_version": schema_version,
                "run_id": run_id,
                "step": step,
                "heldout_episodes": heldout_episodes,
                "n_frames": n_frames,
                "action_names": action_names,
                "overall": overall,
                "per_joint": per_joint,
                "disclaimer_key": disclaimer_key,
            }
        )
        if plots is not UNSET:
            field_dict["plots"] = plots

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.eval_metrics_overall import EvalMetricsOverall
        from ..models.eval_metrics_per_joint_item import EvalMetricsPerJointItem
        from ..models.eval_metrics_plots_item import EvalMetricsPlotsItem

        d = dict(src_dict)
        schema_version = cast(Literal["1"], d.pop("schema_version"))
        if schema_version != "1":
            raise ValueError(
                f"schema_version must match const '1', got '{schema_version}'"
            )

        run_id = UUID(d.pop("run_id"))

        step = d.pop("step")

        heldout_episodes = cast(list[int], d.pop("heldout_episodes"))

        n_frames = d.pop("n_frames")

        action_names = cast(list[str], d.pop("action_names"))

        overall = EvalMetricsOverall.from_dict(d.pop("overall"))

        per_joint = []
        _per_joint = d.pop("per_joint")
        for per_joint_item_data in _per_joint:
            per_joint_item = EvalMetricsPerJointItem.from_dict(per_joint_item_data)

            per_joint.append(per_joint_item)

        disclaimer_key = cast(
            Literal["eval.offline_not_success_rate"], d.pop("disclaimer_key")
        )
        if disclaimer_key != "eval.offline_not_success_rate":
            raise ValueError(
                f"disclaimer_key must match const 'eval.offline_not_success_rate', got '{disclaimer_key}'"
            )

        _plots = d.pop("plots", UNSET)
        plots: list[EvalMetricsPlotsItem] | Unset = UNSET
        if _plots is not UNSET:
            plots = []
            for plots_item_data in _plots:
                plots_item = EvalMetricsPlotsItem.from_dict(plots_item_data)

                plots.append(plots_item)

        eval_metrics = cls(
            schema_version=schema_version,
            run_id=run_id,
            step=step,
            heldout_episodes=heldout_episodes,
            n_frames=n_frames,
            action_names=action_names,
            overall=overall,
            per_joint=per_joint,
            disclaimer_key=disclaimer_key,
            plots=plots,
        )

        eval_metrics.additional_properties = d
        return eval_metrics

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
