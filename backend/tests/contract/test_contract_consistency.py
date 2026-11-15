"""Contract drift guard (owner A1): DB enums == OpenAPI enums, policy schemas present & valid."""

from __future__ import annotations

import enum
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db import models as m

REPO = Path(__file__).resolve().parents[3]
OPENAPI = yaml.safe_load((REPO / "api" / "openapi.yaml").read_text())
SCHEMAS: dict[str, Any] = OPENAPI["components"]["schemas"]

PAIRS: list[tuple[type[enum.Enum], str]] = [
    (m.WorkspaceRole, "WorkspaceRole"),
    (m.PatScope, "PatScope"),
    (m.ArchiveFormat, "ArchiveFormat"),
    (m.UploadStatus, "UploadStatus"),
    (m.DatasetSource, "DatasetSource"),
    (m.DatasetVersionStatus, "DatasetVersionStatus"),
    (m.RunStatus, "RunStatus"),
    (m.MixedPrecision, "MixedPrecision"),
    (m.JobKind, "JobKind"),
    (m.JobStatus, "JobStatus"),
    (m.OnnxStatus, "OnnxStatus"),
    (m.ModelStatus, "ModelStatus"),
    (m.NotificationChannelKind, "NotificationChannelKind"),
]


@pytest.mark.parametrize(("py_enum", "schema_name"), PAIRS, ids=[p[1] for p in PAIRS])
def test_enum_matches_openapi(py_enum: type[enum.Enum], schema_name: str) -> None:
    assert [e.value for e in py_enum] == SCHEMAS[schema_name]["enum"]


def test_gpu_status_matches() -> None:
    assert [e.value for e in m.GpuNodeStatus] == SCHEMAS["GpuNode"]["properties"]["status"]["enum"]


def test_policy_types_have_schemas() -> None:
    index = json.loads((REPO / "api" / "policy-schemas" / "index.json").read_text())
    assert sorted(SCHEMAS["PolicyType"]["enum"]) == sorted(index["policies"])
    for p in index["policies"]:
        doc = json.loads((REPO / "api" / "policy-schemas" / f"{p}.json").read_text())
        assert doc["x-hibiscus"]["policy_type"] == p
        assert doc["x-hibiscus"]["lerobot_version"] == index["lerobot_version"] == "0.7.1"


def test_ddl_compiles_for_postgres() -> None:
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]  # untyped in SQLAlchemy
    m.Base.registry.configure()
    names: list[str] = []
    for table in m.Base.metadata.sorted_tables:
        str(CreateTable(table).compile(dialect=dialect))
        names += [c.name for c in table.constraints if isinstance(c.name, str)]
        for ix in table.indexes:
            str(CreateIndex(ix).compile(dialect=dialect))
            names.append(str(ix.name))
    assert len(names) == len(set(names)), "constraint/index names must be unique per schema"
    assert all(len(n) <= 63 for n in names)


def _deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def test_presets_validate_against_schemas() -> None:
    from jsonschema import Draft202012Validator

    base = REPO / "api" / "policy-schemas"
    presets = json.loads((base / "presets.json").read_text())["presets"]
    assert [p["id"] for p in presets] == SCHEMAS["Preset"]["properties"]["id"]["enum"]
    train_schema = json.loads((base / "train.json").read_text())
    for policy in SCHEMAS["PolicyType"]["enum"]:
        pol_schema = json.loads((base / f"{policy}.json").read_text())
        for p in presets:
            extra = p["per_policy"].get(policy, {})
            train = _deep_merge(p["train"], extra.get("train", {}))
            pol = _deep_merge(p["policy"], extra.get("policy", {}))
            errs = [e.message for e in Draft202012Validator(train_schema).iter_errors(train)]
            errs += [e.message for e in Draft202012Validator(pol_schema).iter_errors(pol)]
            assert not errs, (policy, p["id"], errs)


def test_real_act_checkpoint_config_validates() -> None:
    from jsonschema import Draft202012Validator

    schema = json.loads((REPO / "api" / "policy-schemas" / "act.json").read_text())
    cfg = json.loads((REPO / "docs" / "spec" / "examples" / "act_checkpoint_config.json").read_text())
    cfg = {k: v for k, v in cfg.items() if k not in schema["x-hibiscus"]["excluded"] and k != "type"}
    assert not [e.message for e in Draft202012Validator(schema).iter_errors(cfg)]
