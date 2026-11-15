"""Bundle JSON Schemas are valid and the examples (built from the real ACT checkpoint) conform."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parents[3]
SCHEMAS = REPO / "api" / "bundle-schemas"
EXAMPLES = REPO / "docs" / "spec" / "examples"

CASES = [
    ("manifest.schema.json", "MANIFEST.example.json"),
    ("io_spec.schema.json", "io_spec.example.json"),
    ("normalization.schema.json", "normalization.example.json"),
    ("parity_report.schema.json", "parity_report.example.json"),
]


@pytest.mark.parametrize(("schema_file", "example_file"), CASES)
def test_example_validates(schema_file: str, example_file: str) -> None:
    schema = json.loads((SCHEMAS / schema_file).read_text())
    Draft202012Validator.check_schema(schema)
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
            json.loads((EXAMPLES / example_file).read_text())
        )
    )
    assert not errors, [e.message for e in errors]


def test_manifest_files_sorted_and_exclude_itself() -> None:
    files = json.loads((EXAMPLES / "MANIFEST.example.json").read_text())["files"]
    paths = [f["path"] for f in files]
    assert paths == sorted(paths)
    assert "MANIFEST.json" not in paths


def test_appendix_matches_files() -> None:
    md = (REPO / "docs" / "spec" / "bundle.md").read_text()
    for schema_file in [c[0] for c in CASES]:
        body = (SCHEMAS / schema_file).read_text().rstrip("\n")
        assert f"### {schema_file}\n\n```json\n{body}\n```" in md, schema_file
