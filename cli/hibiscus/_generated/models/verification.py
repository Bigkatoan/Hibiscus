import datetime
from collections.abc import Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    Union,
    cast,
)

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.verification_parity_type_0 import VerificationParityType0


T = TypeVar("T", bound="Verification")


@_attrs_define
class Verification:
    """
    Attributes:
        load_ok (bool): PreTrainedPolicy.from_pretrained + processors load and run one select_action
        parity_ok (Union[None, bool]): null when onnx_status=not_supported (not required for verified)
        manifest_ok (bool):
        checked_at (datetime.datetime):
        lelab_compatible (Union[None, Unset, bool]): CR-A5-W1 (QC-ml-1). The same load check passes in the LeLab venv
            (LeRobot 0.7.1 without optional extras) with no extra packages. false = the user must install the packages
            listed in MANIFEST.checks.lelab_requirements first (e.g. diffusers for diffusion). null = not checked (bundles
            built before this field existed). Not part of `verified`.
        parity (Union['VerificationParityType0', None, Unset]): Summary of onnx/parity_report.json
        details (Union[None, Unset, str]):
    """

    load_ok: bool
    parity_ok: Union[None, bool]
    manifest_ok: bool
    checked_at: datetime.datetime
    lelab_compatible: Union[None, Unset, bool] = UNSET
    parity: Union["VerificationParityType0", None, Unset] = UNSET
    details: Union[None, Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.verification_parity_type_0 import VerificationParityType0

        load_ok = self.load_ok

        parity_ok: Union[None, bool]
        parity_ok = self.parity_ok

        manifest_ok = self.manifest_ok

        checked_at = self.checked_at.isoformat()

        lelab_compatible: Union[None, Unset, bool]
        if isinstance(self.lelab_compatible, Unset):
            lelab_compatible = UNSET
        else:
            lelab_compatible = self.lelab_compatible

        parity: Union[None, Unset, dict[str, Any]]
        if isinstance(self.parity, Unset):
            parity = UNSET
        elif isinstance(self.parity, VerificationParityType0):
            parity = self.parity.to_dict()
        else:
            parity = self.parity

        details: Union[None, Unset, str]
        if isinstance(self.details, Unset):
            details = UNSET
        else:
            details = self.details

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "load_ok": load_ok,
                "parity_ok": parity_ok,
                "manifest_ok": manifest_ok,
                "checked_at": checked_at,
            }
        )
        if lelab_compatible is not UNSET:
            field_dict["lelab_compatible"] = lelab_compatible
        if parity is not UNSET:
            field_dict["parity"] = parity
        if details is not UNSET:
            field_dict["details"] = details

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.verification_parity_type_0 import VerificationParityType0

        d = dict(src_dict)
        load_ok = d.pop("load_ok")

        def _parse_parity_ok(data: object) -> Union[None, bool]:
            if data is None:
                return data
            return cast(Union[None, bool], data)

        parity_ok = _parse_parity_ok(d.pop("parity_ok"))

        manifest_ok = d.pop("manifest_ok")

        checked_at = isoparse(d.pop("checked_at"))

        def _parse_lelab_compatible(data: object) -> Union[None, Unset, bool]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, bool], data)

        lelab_compatible = _parse_lelab_compatible(d.pop("lelab_compatible", UNSET))

        def _parse_parity(
            data: object,
        ) -> Union["VerificationParityType0", None, Unset]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                parity_type_0 = VerificationParityType0.from_dict(data)

                return parity_type_0
            except:  # noqa: E722
                pass
            return cast(Union["VerificationParityType0", None, Unset], data)

        parity = _parse_parity(d.pop("parity", UNSET))

        def _parse_details(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        details = _parse_details(d.pop("details", UNSET))

        verification = cls(
            load_ok=load_ok,
            parity_ok=parity_ok,
            manifest_ok=manifest_ok,
            checked_at=checked_at,
            lelab_compatible=lelab_compatible,
            parity=parity,
            details=details,
        )

        verification.additional_properties = d
        return verification

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
