"""``--set key=value`` parsing for ``hibiscus train`` into ``RunCreate.config``.

* ``policy.chunk_size=50`` / ``train.steps=300`` address the section explicitly; nested keys use
  dots (``train.peft.r=8``).
* A bare key (``steps=300``) is looked up in the policy's ``train_schema`` and ``policy_schema``
  properties (from ``GET /policies/{type}``); it must exist in exactly one of them.
* Values are parsed as JSON when possible (``true``, ``null``, ``0.5``, ``[1,2]``, ``{"a":1}``)
  and otherwise kept as strings (``vision_backbone=resnet18``).

Server-side validation (schema + cross-field rules) stays authoritative; this only builds the
request shape described in docs/spec/policy-schema.md §4.
"""

from __future__ import annotations

import json
from typing import Any

SECTIONS = ("policy", "train")


class OverrideError(ValueError):
    pass


def parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _set_path(target: dict[str, Any], keys: list[str], value: Any) -> None:
    cur = target
    for k in keys[:-1]:
        nxt = cur.setdefault(k, {})
        if not isinstance(nxt, dict):
            raise OverrideError(f"cannot set {'.'.join(keys)}: {k} is not an object")
        cur = nxt
    cur[keys[-1]] = value


def build_config(
    sets: list[str],
    *,
    policy_props: set[str] | None = None,
    train_props: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    config: dict[str, dict[str, Any]] = {"policy": {}, "train": {}}
    for item in sets:
        key, sep, raw = item.partition("=")
        key = key.strip()
        if not sep or not key:
            raise OverrideError(f"--set expects key=value, got {item!r}")
        parts = [p for p in key.split(".") if p]
        if not parts:
            raise OverrideError(f"empty key in {item!r}")
        if parts[0] in SECTIONS and len(parts) > 1:
            section, path = parts[0], parts[1:]
        else:
            in_train = train_props is not None and parts[0] in train_props
            in_policy = policy_props is not None and parts[0] in policy_props
            if in_train and in_policy:
                raise OverrideError(
                    f"{key!r} exists in both policy and train; write policy.{key} or train.{key}"
                )
            if in_train:
                section = "train"
            elif in_policy:
                section = "policy"
            elif policy_props is None and train_props is None:
                raise OverrideError(f"{key!r}: prefix with policy. or train.")
            else:
                raise OverrideError(f"unknown option {key!r} (not in the policy or train schema)")
            path = parts
        _set_path(config[section], path, parse_value(raw))
    return config
