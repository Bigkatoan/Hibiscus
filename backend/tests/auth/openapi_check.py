"""Validate live responses against api/openapi.yaml (JSON Schema 2020-12 via ``jsonschema``).

Rules: the (path, method) must exist in the contract; a documented status must match its schema
(and content type); an undocumented status >= 400 must still be a valid ``Problem``; an
undocumented 2xx/3xx fails. Every Problem ``code`` must be in the ErrorCode catalogue (enforced by
the schema enum).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import jsonschema
import yaml
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SPEC_PATH = Path(__file__).resolve().parents[3] / "api" / "openapi.yaml"
URI = "urn:hibiscus:openapi"
ROOT_PATHS = {"/healthz", "/readyz", "/metrics"}


class ContractViolationError(AssertionError):
    pass


@lru_cache(maxsize=1)
def _spec() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(SPEC_PATH.read_text())
    return data


@lru_cache(maxsize=1)
def _registry() -> Registry:
    reg: Registry = Registry().with_resource(
        URI, Resource.from_contents(_spec(), default_specification=DRAFT202012)
    )
    return reg


@lru_cache(maxsize=1)
def _routes() -> list[tuple[re.Pattern[str], str]]:
    out = []
    for tmpl in _spec()["paths"]:
        prefix = "" if tmpl in ROOT_PATHS else "/api/v1"
        rx = re.sub(r"\{[^}/]+\}", r"[^/]+", re.escape(prefix + tmpl).replace(r"\{", "{").replace(r"\}", "}"))
        out.append((re.compile(f"^{rx}$"), tmpl))
    # literal segments win over templated ones (e.g. /sessions/revoke-others vs /sessions/{id})
    out.sort(key=lambda p: p[1].count("{"))
    return out


def _resolve(obj: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in obj:
        ref = obj["$ref"]
        node: Any = _spec()
        for part in ref.lstrip("#/").split("/"):
            node = node[part]
        obj = node
    return obj


def _validate(instance: Any, schema: dict[str, Any], where: str) -> None:
    wrapped = (
        {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": f"{URI}#{_pointer(schema)}"}
        if "$ref" in schema
        else None
    )
    validator_schema = wrapped or {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **_rebase(schema),
    }
    v = jsonschema.Draft202012Validator(validator_schema, registry=_registry())
    errors = sorted(v.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        msgs = "; ".join(f"{list(e.path)}: {e.message[:300]}" for e in errors[:5])
        raise ContractViolationError(f"{where}: {msgs}")


def _pointer(schema: dict[str, Any]) -> str:
    return str(schema["$ref"]).lstrip("#")


def _rebase(schema: Any) -> Any:
    """Rewrite local ``#/...`` refs of an inline schema to the registered document URI."""
    if isinstance(schema, dict):
        return {
            k: (f"{URI}{v}" if k == "$ref" and isinstance(v, str) and v.startswith("#") else _rebase(v))
            for k, v in schema.items()
        }
    if isinstance(schema, list):
        return [_rebase(x) for x in schema]
    return schema


def find_operation(method: str, path: str) -> tuple[str, dict[str, Any]]:
    for rx, tmpl in _routes():
        if rx.match(path):
            op = _spec()["paths"][tmpl].get(method.lower())
            if op is None:
                raise ContractViolationError(f"{method} {tmpl} not in contract")
            return tmpl, op
    raise ContractViolationError(f"{method} {path}: path not in contract")


def validate_response(method: str, path: str, response: httpx.Response) -> None:
    if path.startswith("/api/docs") or path == "/api/openapi.json":
        return
    tmpl, op = find_operation(method, path)
    where = f"{method} {tmpl} -> {response.status_code}"
    status = str(response.status_code)
    responses = op.get("responses", {})
    spec_resp = responses.get(status)
    ctype = response.headers.get("content-type", "").split(";")[0].strip()
    if spec_resp is None:
        if response.status_code < 400:
            raise ContractViolationError(f"{where}: undocumented success status")
        if ctype != "application/problem+json":
            raise ContractViolationError(f"{where}: error without problem+json ({ctype})")
        _validate(response.json(), {"$ref": "#/components/schemas/Problem"}, where)
        return
    spec_resp = _resolve(spec_resp)
    content = spec_resp.get("content")
    if not content:
        if response.content:
            raise ContractViolationError(f"{where}: body present but contract has no content")
        return
    if ctype not in content:
        raise ContractViolationError(f"{where}: content-type {ctype!r} not in {list(content)}")
    schema = content[ctype].get("schema")
    if schema and ctype.endswith("json"):
        _validate(response.json(), schema, where)
