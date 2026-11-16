from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.checkpoint_eval_summary_type_0 import CheckpointEvalSummaryType0


T = TypeVar("T", bound="Checkpoint")


@_attrs_define
class Checkpoint:
    """
    Attributes:
        id (UUID):
        run_id (UUID):
        step (int):
        size_bytes (int):
        is_last (bool):
        created_at (datetime.datetime):
        has_training_state (bool | Unset):
        model_id (None | Unset | UUID):
        eval_summary (CheckpointEvalSummaryType0 | None | Unset):
    """

    id: UUID
    run_id: UUID
    step: int
    size_bytes: int
    is_last: bool
    created_at: datetime.datetime
    has_training_state: bool | Unset = UNSET
    model_id: None | Unset | UUID = UNSET
    eval_summary: CheckpointEvalSummaryType0 | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.checkpoint_eval_summary_type_0 import CheckpointEvalSummaryType0

        id = str(self.id)

        run_id = str(self.run_id)

        step = self.step

        size_bytes = self.size_bytes

        is_last = self.is_last

        created_at = self.created_at.isoformat()

        has_training_state = self.has_training_state

        model_id: None | str | Unset
        if isinstance(self.model_id, Unset):
            model_id = UNSET
        elif isinstance(self.model_id, UUID):
            model_id = str(self.model_id)
        else:
            model_id = self.model_id

        eval_summary: dict[str, Any] | None | Unset
        if isinstance(self.eval_summary, Unset):
            eval_summary = UNSET
        elif isinstance(self.eval_summary, CheckpointEvalSummaryType0):
            eval_summary = self.eval_summary.to_dict()
        else:
            eval_summary = self.eval_summary

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "run_id": run_id,
                "step": step,
                "size_bytes": size_bytes,
                "is_last": is_last,
                "created_at": created_at,
            }
        )
        if has_training_state is not UNSET:
            field_dict["has_training_state"] = has_training_state
        if model_id is not UNSET:
            field_dict["model_id"] = model_id
        if eval_summary is not UNSET:
            field_dict["eval_summary"] = eval_summary

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.checkpoint_eval_summary_type_0 import CheckpointEvalSummaryType0

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        run_id = UUID(d.pop("run_id"))

        step = d.pop("step")

        size_bytes = d.pop("size_bytes")

        is_last = d.pop("is_last")

        created_at = isoparse(d.pop("created_at"))

        has_training_state = d.pop("has_training_state", UNSET)

        def _parse_model_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                model_id_type_0 = UUID(data)

                return model_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        model_id = _parse_model_id(d.pop("model_id", UNSET))

        def _parse_eval_summary(
            data: object,
        ) -> CheckpointEvalSummaryType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                eval_summary_type_0 = CheckpointEvalSummaryType0.from_dict(data)

                return eval_summary_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(CheckpointEvalSummaryType0 | None | Unset, data)

        eval_summary = _parse_eval_summary(d.pop("eval_summary", UNSET))

        checkpoint = cls(
            id=id,
            run_id=run_id,
            step=step,
            size_bytes=size_bytes,
            is_last=is_last,
            created_at=created_at,
            has_training_state=has_training_state,
            model_id=model_id,
            eval_summary=eval_summary,
        )

        checkpoint.additional_properties = d
        return checkpoint

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
