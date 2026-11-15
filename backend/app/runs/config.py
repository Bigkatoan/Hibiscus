"""Effective config resolution + validation (docs/spec/policy-schema.md §4 steps 1-3)."""

from __future__ import annotations

import ast
import copy
import operator
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

from app.core.errors import ErrorCode, ProblemError
from app.runs.catalog import Catalog


def deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


@dataclass(slots=True)
class ResolvedConfig:
    policy: dict[str, Any]
    train: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"policy": self.policy, "train": self.train}


def _field_errors(validator: Draft202012Validator, doc: dict[str, Any], section: str) -> list[dict[str, Any]]:
    errs = []
    for e in sorted(validator.iter_errors(doc), key=lambda e: list(map(str, e.absolute_path))):
        errs.append(
            {
                "loc": ["body", "config", section, *list(e.absolute_path)],
                "code": str(e.validator),
                "message": e.message[:500],
            }
        )
    return errs


def resolve_config(
    cat: Catalog,
    policy_type: str,
    user: dict[str, Any],
    *,
    preset: str | None,
    seed: int | None = None,
    base: dict[str, Any] | None = None,
) -> ResolvedConfig:
    """defaults <- preset (or ``base`` for clones) <- user; validate; cross-field rules."""
    pschema = cat.policy_schema(policy_type)
    tschema = cat.train_schema
    policy = cat.defaults(pschema)
    train = cat.defaults(tschema)
    if base is not None:
        policy = deep_merge(policy, base.get("policy", {}))
        train = deep_merge(train, base.get("train", {}))
    if preset is not None:
        p = cat.preset(policy_type, preset)
        if p is None:  # pragma: no cover - enum-guarded by the request model
            raise ProblemError(422, ErrorCode.VALIDATION_FAILED, f"unknown preset {preset}")
        policy = deep_merge(policy, p["policy"])
        train = deep_merge(train, p["train"])
    user_policy = user.get("policy", {})
    user_train = user.get("train", {})
    policy = deep_merge(policy, user_policy) if isinstance(user_policy, dict) else policy
    train = deep_merge(train, user_train) if isinstance(user_train, dict) else train
    if seed is not None:
        train["seed"] = seed
    errors = _field_errors(Draft202012Validator(pschema), policy, "policy")
    errors += _field_errors(Draft202012Validator(tschema), train, "train")
    if errors:
        raise ProblemError(
            422, ErrorCode.VALIDATION_FAILED, "config does not match the policy schema", errors=errors
        )
    cross = cross_field_errors(pschema, policy)
    if cross:
        raise ProblemError(422, ErrorCode.POLICY_CONFIG_INVALID, cross[0]["message"], errors=cross)
    return ResolvedConfig(policy, train)


# --- cross-field rules: tiny whitelisted expression evaluator (no eval) --------------------------
_CMP: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
    ast.LtE: operator.le,
    ast.Lt: operator.lt,
    ast.GtE: operator.ge,
    ast.Gt: operator.gt,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}
_BIN: dict[type[ast.operator], Callable[[Any, Any], Any]] = {ast.Add: operator.add, ast.Sub: operator.sub}


def _eval(node: ast.AST, env: dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.BoolOp):
        vals = [_eval(v, env) for v in node.values]
        return any(vals) if isinstance(node.op, ast.Or) else all(vals)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval(node.operand, env)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, env)
        for op, comp in zip(node.ops, node.comparators, strict=True):
            right = _eval(comp, env)
            if left is None or right is None:
                if type(op) not in (ast.Eq, ast.NotEq):
                    return True  # comparisons against unset values are not enforced
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.Name):
        if node.id == "null":
            return None
        return env.get(node.id)
    if isinstance(node, ast.Constant):
        return node.value
    raise ValueError(f"unsupported rule syntax: {ast.dump(node)}")


def eval_rule(rule: str, values: dict[str, Any]) -> bool:
    return bool(_eval(ast.parse(rule, mode="eval"), values))


def cross_field_errors(schema: dict[str, Any], values: dict[str, Any]) -> list[dict[str, Any]]:
    errs = []
    for r in schema.get("x-hibiscus", {}).get("cross_field_rules", []):
        rule = r["rule"]
        if not eval_rule(rule, values):
            first = next(
                (n.id for n in ast.walk(ast.parse(rule, mode="eval")) if isinstance(n, ast.Name)), ""
            )
            errs.append(
                {
                    "loc": ["body", "config", "policy", first],
                    "code": r.get("code", "policy_config_invalid"),
                    "message": f"rule violated: {rule}",
                }
            )
    return errs


# --- held-out split (run-lifecycle §10) ------------------------------------------------------------
def heldout_split(
    n_episodes: int, fraction: float, seed: int, explicit: list[int] | None = None
) -> tuple[list[int], list[int]]:
    if explicit is not None:
        bad = [e for e in explicit if e < 0 or e >= n_episodes]
        if bad or len(set(explicit)) >= n_episodes:
            raise ProblemError(
                422,
                ErrorCode.VALIDATION_FAILED,
                "heldout_episodes out of range or leaves no training episode",
                errors=[{"loc": ["body", "heldout_episodes"], "code": "range", "message": f"invalid: {bad}"}],
            )
        held = sorted(set(explicit))
    else:
        k = 0 if fraction == 0 else max(1, round(n_episodes * fraction))
        k = min(k, max(n_episodes - 1, 0))
        held = sorted(random.Random(seed).sample(range(n_episodes), k))  # noqa: S311 - reproducible split
    hs = set(held)
    return held, [i for i in range(n_episodes) if i not in hs]
