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

from ..models.model_status import ModelStatus
from ..models.onnx_status import OnnxStatus
from ..models.policy_type import PolicyType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.model_dataset import ModelDataset
    from ..models.model_eval_summary_type_0 import ModelEvalSummaryType0
    from ..models.user_ref import UserRef
    from ..models.verification import Verification


T = TypeVar("T", bound="Model")


@_attrs_define
class Model:
    """
    Attributes:
        id (UUID):
        workspace_id (UUID):
        name (str):
        policy_type (PolicyType):
        run_id (UUID):
        run_number (int):
        step (int):
        status (ModelStatus):
        verified (bool):
        onnx_status (OnnxStatus):
        created_at (datetime.datetime):
        checkpoint_id (Union[Unset, UUID]):
        error_message (Union[None, Unset, str]):
        verification (Union['Verification', None, Unset]):
        onnx_detail (Union[None, Unset, str]):
        bundle_size_bytes (Union[None, Unset, int]):
        bundle_sha256 (Union[None, Unset, str]):
        dataset (Union[Unset, ModelDataset]):
        eval_summary (Union['ModelEvalSummaryType0', None, Unset]):
        hub_repo_id (Union[None, Unset, str]):
        hub_pushed_at (Union[None, Unset, datetime.datetime]):
        created_by (Union[Unset, UserRef]):
    """

    id: UUID
    workspace_id: UUID
    name: str
    policy_type: PolicyType
    run_id: UUID
    run_number: int
    step: int
    status: ModelStatus
    verified: bool
    onnx_status: OnnxStatus
    created_at: datetime.datetime
    checkpoint_id: Union[Unset, UUID] = UNSET
    error_message: Union[None, Unset, str] = UNSET
    verification: Union["Verification", None, Unset] = UNSET
    onnx_detail: Union[None, Unset, str] = UNSET
    bundle_size_bytes: Union[None, Unset, int] = UNSET
    bundle_sha256: Union[None, Unset, str] = UNSET
    dataset: Union[Unset, "ModelDataset"] = UNSET
    eval_summary: Union["ModelEvalSummaryType0", None, Unset] = UNSET
    hub_repo_id: Union[None, Unset, str] = UNSET
    hub_pushed_at: Union[None, Unset, datetime.datetime] = UNSET
    created_by: Union[Unset, "UserRef"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.model_eval_summary_type_0 import ModelEvalSummaryType0
        from ..models.verification import Verification

        id = str(self.id)

        workspace_id = str(self.workspace_id)

        name = self.name

        policy_type = self.policy_type.value

        run_id = str(self.run_id)

        run_number = self.run_number

        step = self.step

        status = self.status.value

        verified = self.verified

        onnx_status = self.onnx_status.value

        created_at = self.created_at.isoformat()

        checkpoint_id: Union[Unset, str] = UNSET
        if not isinstance(self.checkpoint_id, Unset):
            checkpoint_id = str(self.checkpoint_id)

        error_message: Union[None, Unset, str]
        if isinstance(self.error_message, Unset):
            error_message = UNSET
        else:
            error_message = self.error_message

        verification: Union[None, Unset, dict[str, Any]]
        if isinstance(self.verification, Unset):
            verification = UNSET
        elif isinstance(self.verification, Verification):
            verification = self.verification.to_dict()
        else:
            verification = self.verification

        onnx_detail: Union[None, Unset, str]
        if isinstance(self.onnx_detail, Unset):
            onnx_detail = UNSET
        else:
            onnx_detail = self.onnx_detail

        bundle_size_bytes: Union[None, Unset, int]
        if isinstance(self.bundle_size_bytes, Unset):
            bundle_size_bytes = UNSET
        else:
            bundle_size_bytes = self.bundle_size_bytes

        bundle_sha256: Union[None, Unset, str]
        if isinstance(self.bundle_sha256, Unset):
            bundle_sha256 = UNSET
        else:
            bundle_sha256 = self.bundle_sha256

        dataset: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.dataset, Unset):
            dataset = self.dataset.to_dict()

        eval_summary: Union[None, Unset, dict[str, Any]]
        if isinstance(self.eval_summary, Unset):
            eval_summary = UNSET
        elif isinstance(self.eval_summary, ModelEvalSummaryType0):
            eval_summary = self.eval_summary.to_dict()
        else:
            eval_summary = self.eval_summary

        hub_repo_id: Union[None, Unset, str]
        if isinstance(self.hub_repo_id, Unset):
            hub_repo_id = UNSET
        else:
            hub_repo_id = self.hub_repo_id

        hub_pushed_at: Union[None, Unset, str]
        if isinstance(self.hub_pushed_at, Unset):
            hub_pushed_at = UNSET
        elif isinstance(self.hub_pushed_at, datetime.datetime):
            hub_pushed_at = self.hub_pushed_at.isoformat()
        else:
            hub_pushed_at = self.hub_pushed_at

        created_by: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.created_by, Unset):
            created_by = self.created_by.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "workspace_id": workspace_id,
                "name": name,
                "policy_type": policy_type,
                "run_id": run_id,
                "run_number": run_number,
                "step": step,
                "status": status,
                "verified": verified,
                "onnx_status": onnx_status,
                "created_at": created_at,
            }
        )
        if checkpoint_id is not UNSET:
            field_dict["checkpoint_id"] = checkpoint_id
        if error_message is not UNSET:
            field_dict["error_message"] = error_message
        if verification is not UNSET:
            field_dict["verification"] = verification
        if onnx_detail is not UNSET:
            field_dict["onnx_detail"] = onnx_detail
        if bundle_size_bytes is not UNSET:
            field_dict["bundle_size_bytes"] = bundle_size_bytes
        if bundle_sha256 is not UNSET:
            field_dict["bundle_sha256"] = bundle_sha256
        if dataset is not UNSET:
            field_dict["dataset"] = dataset
        if eval_summary is not UNSET:
            field_dict["eval_summary"] = eval_summary
        if hub_repo_id is not UNSET:
            field_dict["hub_repo_id"] = hub_repo_id
        if hub_pushed_at is not UNSET:
            field_dict["hub_pushed_at"] = hub_pushed_at
        if created_by is not UNSET:
            field_dict["created_by"] = created_by

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.model_dataset import ModelDataset
        from ..models.model_eval_summary_type_0 import ModelEvalSummaryType0
        from ..models.user_ref import UserRef
        from ..models.verification import Verification

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        workspace_id = UUID(d.pop("workspace_id"))

        name = d.pop("name")

        policy_type = PolicyType(d.pop("policy_type"))

        run_id = UUID(d.pop("run_id"))

        run_number = d.pop("run_number")

        step = d.pop("step")

        status = ModelStatus(d.pop("status"))

        verified = d.pop("verified")

        onnx_status = OnnxStatus(d.pop("onnx_status"))

        created_at = isoparse(d.pop("created_at"))

        _checkpoint_id = d.pop("checkpoint_id", UNSET)
        checkpoint_id: Union[Unset, UUID]
        if isinstance(_checkpoint_id, Unset):
            checkpoint_id = UNSET
        else:
            checkpoint_id = UUID(_checkpoint_id)

        def _parse_error_message(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        error_message = _parse_error_message(d.pop("error_message", UNSET))

        def _parse_verification(data: object) -> Union["Verification", None, Unset]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                verification_type_0 = Verification.from_dict(data)

                return verification_type_0
            except:  # noqa: E722
                pass
            return cast(Union["Verification", None, Unset], data)

        verification = _parse_verification(d.pop("verification", UNSET))

        def _parse_onnx_detail(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        onnx_detail = _parse_onnx_detail(d.pop("onnx_detail", UNSET))

        def _parse_bundle_size_bytes(data: object) -> Union[None, Unset, int]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, int], data)

        bundle_size_bytes = _parse_bundle_size_bytes(d.pop("bundle_size_bytes", UNSET))

        def _parse_bundle_sha256(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        bundle_sha256 = _parse_bundle_sha256(d.pop("bundle_sha256", UNSET))

        _dataset = d.pop("dataset", UNSET)
        dataset: Union[Unset, ModelDataset]
        if isinstance(_dataset, Unset):
            dataset = UNSET
        else:
            dataset = ModelDataset.from_dict(_dataset)

        def _parse_eval_summary(
            data: object,
        ) -> Union["ModelEvalSummaryType0", None, Unset]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                eval_summary_type_0 = ModelEvalSummaryType0.from_dict(data)

                return eval_summary_type_0
            except:  # noqa: E722
                pass
            return cast(Union["ModelEvalSummaryType0", None, Unset], data)

        eval_summary = _parse_eval_summary(d.pop("eval_summary", UNSET))

        def _parse_hub_repo_id(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        hub_repo_id = _parse_hub_repo_id(d.pop("hub_repo_id", UNSET))

        def _parse_hub_pushed_at(data: object) -> Union[None, Unset, datetime.datetime]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                hub_pushed_at_type_0 = isoparse(data)

                return hub_pushed_at_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, datetime.datetime], data)

        hub_pushed_at = _parse_hub_pushed_at(d.pop("hub_pushed_at", UNSET))

        _created_by = d.pop("created_by", UNSET)
        created_by: Union[Unset, UserRef]
        if isinstance(_created_by, Unset):
            created_by = UNSET
        else:
            created_by = UserRef.from_dict(_created_by)

        model = cls(
            id=id,
            workspace_id=workspace_id,
            name=name,
            policy_type=policy_type,
            run_id=run_id,
            run_number=run_number,
            step=step,
            status=status,
            verified=verified,
            onnx_status=onnx_status,
            created_at=created_at,
            checkpoint_id=checkpoint_id,
            error_message=error_message,
            verification=verification,
            onnx_detail=onnx_detail,
            bundle_size_bytes=bundle_size_bytes,
            bundle_sha256=bundle_sha256,
            dataset=dataset,
            eval_summary=eval_summary,
            hub_repo_id=hub_repo_id,
            hub_pushed_at=hub_pushed_at,
            created_by=created_by,
        )

        model.additional_properties = d
        return model

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
