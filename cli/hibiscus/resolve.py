"""Resolve user-friendly references (names, ``#42``) to API ids."""

from __future__ import annotations

import re
import uuid
from typing import Any

from hibiscus.api import ApiError, HibiscusApi

RUN_NUMBER_RE = re.compile(r"^#?(\d{1,9})$")


class ResolveError(Exception):
    pass


def as_uuid(ref: str) -> str | None:
    try:
        return str(uuid.UUID(ref))
    except ValueError:
        return None


def resolve_dataset(api: HibiscusApi, ref: str) -> dict[str, Any]:
    """Dataset by id, exact name or slug. Returns ``Dataset`` as dict."""
    rid = as_uuid(ref)
    if rid:
        return api.get_dataset(rid).to_dict()
    matches: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        page = api.list_datasets(q=ref[:100], limit=200, cursor=cursor).to_dict()
        for d in page["items"]:
            if d["name"] == ref or d["slug"] == ref:
                matches.append(d)
        cursor = page.get("next_cursor")
        if not cursor:
            break
    if not matches:
        raise ResolveError(f"no dataset named {ref!r} in this workspace (see `hibiscus datasets ls`)")
    if len(matches) > 1:
        raise ResolveError(f"{ref!r} is ambiguous ({len(matches)} datasets); use the dataset id")
    return matches[0]


def resolve_dataset_version(
    api: HibiscusApi, ref: str, version: int | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(Dataset, DatasetVersion) for ``ref`` = dataset id/name, or a dataset-version id."""
    rid = as_uuid(ref)
    if rid and version is None:
        try:
            ds = api.get_dataset(rid).to_dict()
        except ApiError as exc:
            if exc.status != 404:
                raise
            ver = api.get_dataset_version(rid)
            return api.get_dataset(str(ver["dataset_id"])).to_dict(), ver
    else:
        ds = resolve_dataset(api, ref)
    if version is None:
        latest = ds.get("latest_version")
        if not latest:
            raise ResolveError(f"dataset {ds['name']!r} has no versions yet (push one with `hibiscus push`)")
        return ds, api.get_dataset_version(str(latest["id"]))
    cursor: str | None = None
    while True:
        page = api.list_dataset_versions(str(ds["id"]), limit=200, cursor=cursor).to_dict()
        for v in page["items"]:
            if int(v["version"]) == version:
                return ds, api.get_dataset_version(str(v["id"]))
        cursor = page.get("next_cursor")
        if not cursor:
            break
    raise ResolveError(f"dataset {ds['name']!r} has no version {version}")


def resolve_run_id(api: HibiscusApi, ref: str, max_pages: int = 50) -> str:
    rid = as_uuid(ref)
    if rid:
        return rid
    m = RUN_NUMBER_RE.match(ref.strip())
    if not m:
        raise ResolveError(f"run reference {ref!r} must be a run id or a run number like #42")
    number = int(m.group(1))
    cursor: str | None = None
    for _ in range(max_pages):
        page = api.list_runs(limit=200, cursor=cursor).to_dict()
        for r in page["items"]:
            if int(r["number"]) == number:
                return str(r["id"])
        cursor = page.get("next_cursor")
        if not cursor:
            break
    raise ResolveError(f"run #{number} not found in this workspace")


def resolve_model_id(api: HibiscusApi, ref: str) -> str:
    rid = as_uuid(ref)
    if rid:
        return rid
    page = api.list_models(q=ref[:100], limit=200).to_dict()
    exact = [m for m in page["items"] if m["name"] == ref]
    if len(exact) == 1:
        return str(exact[0]["id"])
    if not exact and len(page["items"]) == 1:
        return str(page["items"][0]["id"])
    if not exact and not page["items"]:
        raise ResolveError(f"no model matching {ref!r} (see `hibiscus models ls`)")
    raise ResolveError(f"{ref!r} matches several models; use the model id")
