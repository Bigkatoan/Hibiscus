#!/usr/bin/env python3
"""Cloudflare edge configuration for Hibiscus as code (ADR-0008). Standard library only.

Desired state lives in ``edge.json`` next to this file; secrets come from the environment and are
never written to disk:

    CLOUDFLARE_API_TOKEN   token with Zone:WAF:Edit, Zone:Zone Settings:Edit, Zone:Bot Management:Edit
                           (+ Account:Turnstile:Edit / Account:Access: Apps and Policies:Edit if used)
    CF_ZONE_ID             zone id of example.com
    CF_ACCOUNT_ID          account id (turnstile / access only)

Commands::

    cf_edge.py plan                 # print the desired API payloads (no network)
    cf_edge.py diff                 # GET current zone rulesets and show what `apply` would change
    cf_edge.py apply [--yes]        # PUT the rulesets / settings (asks unless --yes)
    cf_edge.py turnstile-create     # create the Turnstile widget, print site key + secret ONCE
    cf_edge.py access-create        # create the optional Access app for /admin + /api/v1/admin

`apply` rewrites only the rules whose ``ref`` starts with ``hibiscus_`` in the zone entrypoint
rulesets (http_request_firewall_custom, http_ratelimit, http_request_cache_settings); any other
rule in those phases (e.g. for other hostnames of the zone) is preserved. Zone-wide settings and
Bot Fight Mode are touched only when edge.json sets them explicitly. The Cloudflare Tunnel itself is
remotely managed and is NOT touched (CONTRACT_NOTES §3); see docs/runbook/cloudflare.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

API = os.environ.get("CF_API_BASE", "https://api.cloudflare.com/client/v4")
CONFIG_PATH = Path(__file__).resolve().parent / "edge.json"
MANAGED_PHASES = ("http_request_firewall_custom", "http_ratelimit", "http_request_cache_settings")
FREE_MANAGED_RULESET = "77454fe2d30c4220b5701f6fdfb893ba"  # Cloudflare Free Managed Ruleset
CLOUDFLARE_MANAGED_RULESET = "efb7b8c949ac4650a09736fc376e9aee"  # Pro and above
HIBISCUS_REF_PREFIX = "hibiscus_"
ZONE_SETTINGS_ALLOWED = frozenset(
    {"always_use_https", "min_tls_version", "tls_1_3", "browser_check", "security_level"}
)
ALLOWED_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
PLAN_LIMITS: dict[str, dict[str, Any]] = {
    # rate-limiting rules allowed, allowed periods, max mitigation timeout
    "free": {"ratelimit_rules": 1, "periods": {10}, "max_timeout": 10},
    "pro": {"ratelimit_rules": 2, "periods": {10, 60}, "max_timeout": 3600},
    "business": {"ratelimit_rules": 5, "periods": {10, 60, 120, 300, 600}, "max_timeout": 86400},
}


class EdgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class RateLimit:
    requests: int
    period_seconds: int
    mitigation_timeout_seconds: int


@dataclass(frozen=True)
class AccessConfig:
    enabled: bool = False
    session_duration: str = "8h"
    allowed_emails: tuple[str, ...] = ()


@dataclass(frozen=True)
class EdgeConfig:
    hostname: str
    plan: str
    auth_rate_limit: RateLimit
    api_rate_limit: RateLimit
    allowed_countries: tuple[str, ...] = ()
    # None = leave the zone's Bot Fight Mode alone. NOTE: on the Free plan BFM cannot be skipped for
    # API clients and will challenge the `hibiscus` CLI / collect machines (docs/runbook/cloudflare.md).
    bot_fight_mode: bool | None = None
    zone_settings: tuple[tuple[str, str], ...] = ()
    access: AccessConfig = field(default_factory=AccessConfig)

    @staticmethod
    def from_mapping(data: Mapping[str, Any]) -> EdgeConfig:
        acc = data.get("access") or {}
        cfg = EdgeConfig(
            hostname=str(data["hostname"]),
            plan=str(data.get("plan", "free")),
            auth_rate_limit=RateLimit(**data["auth_rate_limit"]),
            api_rate_limit=RateLimit(**data["api_rate_limit"]),
            allowed_countries=tuple(str(c).upper() for c in data.get("allowed_countries", [])),
            bot_fight_mode=None if data.get("bot_fight_mode") is None else bool(data["bot_fight_mode"]),
            zone_settings=tuple((str(k), str(v)) for k, v in (data.get("zone_settings") or {}).items()),
            access=AccessConfig(
                enabled=bool(acc.get("enabled", False)),
                session_duration=str(acc.get("session_duration", "8h")),
                allowed_emails=tuple(str(e) for e in acc.get("allowed_emails", [])),
            ),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.plan not in PLAN_LIMITS:
            raise EdgeError(f"plan must be one of {sorted(PLAN_LIMITS)}")
        if not self.hostname or any(c in self.hostname for c in ' "\\'):
            raise EdgeError("invalid hostname")
        for c in self.allowed_countries:
            if len(c) != 2 or not c.isalpha():
                raise EdgeError(f"invalid ISO country code {c!r}")
        for key, _ in self.zone_settings:
            if key not in ZONE_SETTINGS_ALLOWED:
                raise EdgeError(f"zone setting {key!r} is not managed here ({sorted(ZONE_SETTINGS_ALLOWED)})")
        if self.access.enabled and not self.access.allowed_emails:
            raise EdgeError("access.enabled requires at least one allowed email")


def _q(value: str) -> str:
    """Quote a string literal for the Cloudflare Rules language."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def host_expr(cfg: EdgeConfig) -> str:
    return f"http.host eq {_q(cfg.hostname)}"


def custom_rules(cfg: EdgeConfig) -> list[dict[str, Any]]:
    h = host_expr(cfg)
    methods = " ".join(_q(m) for m in ALLOWED_METHODS)
    rules: list[dict[str, Any]] = [
        {
            "ref": "hibiscus_block_internal_paths",
            "description": "Hibiscus: internal endpoints are never public (/metrics, /readyz)",
            "expression": (
                f'({h} and (http.request.uri.path in {{"/metrics" "/readyz"}} '
                'or starts_with(http.request.uri.path, "/metrics/")))'
            ),
            "action": "block",
        },
        {
            "ref": "hibiscus_block_methods",
            "description": "Hibiscus: only the HTTP methods the API uses",
            "expression": f"({h} and not http.request.method in {{{methods}}})",
            "action": "block",
        },
    ]
    # Body-size rules need `http.request.body.size` and regex `matches` (paid plans); the origin
    # proxy already enforces 1 MiB / 70 MiB (deploy/caddy/Caddyfile) and Cloudflare caps at 100 MB.
    if cfg.allowed_countries:
        countries = " ".join(_q(c) for c in cfg.allowed_countries)
        rules.append(
            {
                "ref": "hibiscus_geo_challenge",
                "description": "Hibiscus: managed challenge outside the allowed countries",
                "expression": f"({h} and not ip.src.country in {{{countries}}})",
                "action": "managed_challenge",
            }
        )
    return rules


def _ratelimit_rule(ref: str, desc: str, expr: str, rl: RateLimit, plan: str) -> dict[str, Any]:
    limits = PLAN_LIMITS[plan]
    period = rl.period_seconds if rl.period_seconds in limits["periods"] else max(limits["periods"])
    timeout = min(rl.mitigation_timeout_seconds, int(limits["max_timeout"]))
    return {
        "ref": ref,
        "description": desc,
        "expression": expr,
        "action": "block",
        "ratelimit": {
            "characteristics": ["cf.colo.id", "ip.src"],
            "period": period,
            "requests_per_period": rl.requests,
            "mitigation_timeout": timeout,
        },
    }


def ratelimit_rules(cfg: EdgeConfig) -> list[dict[str, Any]]:
    h = host_expr(cfg)
    rules = [
        _ratelimit_rule(
            "hibiscus_rl_auth",
            "Hibiscus: brute-force guard on /api/v1/auth/* (login, reset, 2FA)",
            f'({h} and starts_with(http.request.uri.path, "/api/v1/auth/") '
            'and http.request.method eq "POST")',
            cfg.auth_rate_limit,
            cfg.plan,
        )
    ]
    if PLAN_LIMITS[cfg.plan]["ratelimit_rules"] >= 2:
        rules.append(
            _ratelimit_rule(
                "hibiscus_rl_api",
                "Hibiscus: coarse per-IP API limit (upload parts excluded)",
                f'({h} and starts_with(http.request.uri.path, "/api/") and not '
                '(starts_with(http.request.uri.path, "/api/v1/uploads/") '
                'and http.request.uri.path contains "/parts/"))',
                cfg.api_rate_limit,
                cfg.plan,
            )
        )
    return rules


def cache_rules(cfg: EdgeConfig) -> list[dict[str, Any]]:
    return [
        {
            "ref": "hibiscus_bypass_api_cache",
            "description": "Hibiscus: never cache API responses or SSE streams",
            "expression": f'({host_expr(cfg)} and (starts_with(http.request.uri.path, "/api/") '
            'or http.request.uri.path eq "/healthz"))',
            "action": "set_cache_settings",
            "action_parameters": {"cache": False},
        }
    ]


def desired_state(cfg: EdgeConfig) -> dict[str, Any]:
    managed = FREE_MANAGED_RULESET if cfg.plan == "free" else CLOUDFLARE_MANAGED_RULESET
    return {
        "rulesets": {
            "http_request_firewall_custom": custom_rules(cfg),
            "http_ratelimit": ratelimit_rules(cfg),
            "http_request_cache_settings": cache_rules(cfg),
        },
        "managed_waf": {
            "phase": "http_request_firewall_managed",
            "ruleset_id": managed,
            "note": "free plan: deployed automatically by Cloudflare; pro+: apply deploys it",
        },
        # Zone-wide (affect every hostname of the zone) -> only what edge.json lists explicitly.
        "settings": dict(cfg.zone_settings),
        "bot_management": None if cfg.bot_fight_mode is None else {"fight_mode": cfg.bot_fight_mode},
    }


# --------------------------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------------------------
Transport = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]


def http_transport(token: str, base: str = API) -> Transport:
    def call(method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(  # noqa: S310 (fixed https API base or test override)
            base + path,
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                payload: dict[str, Any] = json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as err:
            try:
                payload = json.loads(err.read() or b"{}")
            except json.JSONDecodeError:
                payload = {}
            if err.code == 404:
                return {"success": False, "status": 404, "errors": payload.get("errors", [])}
            raise EdgeError(f"{method} {path}: HTTP {err.code} {payload.get('errors')}") from err
        if not payload.get("success", False):
            raise EdgeError(f"{method} {path}: {payload.get('errors')}")
        return payload

    return call


def _rules_for_compare(rules: list[dict[str, Any]]) -> list[tuple[str, str, str, str]]:
    return [
        (
            str(r.get("ref", "")),
            str(r.get("expression")),
            str(r.get("action")),
            json.dumps(r.get("ratelimit") or r.get("action_parameters") or {}, sort_keys=True),
        )
        for r in rules
    ]


def _is_ours(rule: Mapping[str, Any]) -> bool:
    return str(rule.get("ref", "")).startswith(HIBISCUS_REF_PREFIX)


def _current_rules(call: Transport, phase: str) -> list[dict[str, Any]]:
    current = call("GET", f"/zones/{{zone}}/rulesets/phases/{phase}/entrypoint", None)
    if not current.get("success"):
        return []  # 404: the phase entrypoint does not exist yet
    rules: list[dict[str, Any]] = (current.get("result") or {}).get("rules") or []
    return rules


_WRITABLE_RULE_KEYS = (
    "ref",
    "description",
    "expression",
    "action",
    "action_parameters",
    "ratelimit",
    "enabled",
)


def merged_rules(current: list[dict[str, Any]], ours: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Foreign rules (no `hibiscus_` ref) are kept, in their order, ahead of ours; ours replace all
    previous `hibiscus_*` rules. This never deletes a rule someone else added for another hostname."""
    foreign = [{k: r[k] for k in _WRITABLE_RULE_KEYS if k in r} for r in current if not _is_ours(r)]
    return [*foreign, *ours]


def diff(cfg: EdgeConfig, call: Transport) -> dict[str, list[str]]:
    desired = desired_state(cfg)["rulesets"]
    changes: dict[str, list[str]] = {}
    for phase in MANAGED_PHASES:
        have = _rules_for_compare([r for r in _current_rules(call, phase) if _is_ours(r)])
        want = _rules_for_compare(desired[phase])
        lines = [f"- {h[0]}: {h[1]}" for h in have if h not in want]
        lines += [f"+ {w[0]}: {w[1]}" for w in want if w not in have]
        if lines:
            changes[phase] = lines
    return changes


def apply(cfg: EdgeConfig, call: Transport) -> list[str]:
    done: list[str] = []
    state = desired_state(cfg)
    phases: dict[str, list[dict[str, Any]]] = dict(state["rulesets"])
    if cfg.plan != "free":
        phases["http_request_firewall_managed"] = [
            {
                "ref": "hibiscus_managed_waf",
                "description": "Hibiscus: Cloudflare Managed Ruleset",
                "expression": "true",
                "action": "execute",
                "action_parameters": {"id": state["managed_waf"]["ruleset_id"]},
            }
        ]
    for phase, ours in phases.items():
        rules = merged_rules(_current_rules(call, phase), ours)
        call(
            "PUT",
            f"/zones/{{zone}}/rulesets/phases/{phase}/entrypoint",
            {"description": f"zone entrypoint ({phase})", "rules": rules},
        )
        done.append(f"ruleset {phase}: {len(ours)} hibiscus rules, {len(rules) - len(ours)} other rules kept")
    for key, value in state["settings"].items():
        call("PATCH", f"/zones/{{zone}}/settings/{key}", {"value": value})
        done.append(f"setting {key}={value}")
    if state["bot_management"] is not None:
        call("PUT", "/zones/{zone}/bot_management", state["bot_management"])
        done.append(f"bot fight mode={cfg.bot_fight_mode}")
    return done


def turnstile_create(cfg: EdgeConfig, call: Transport) -> dict[str, str]:
    res = call(
        "POST",
        "/accounts/{account}/challenges/widgets",
        {
            "name": "Hibiscus login",
            "domains": [cfg.hostname],
            "mode": "managed",
            "bot_fight_mode": False,
            "region": "world",
        },
    )["result"]
    return {"sitekey": str(res["sitekey"]), "secret": str(res["secret"])}


def access_create(cfg: EdgeConfig, call: Transport) -> dict[str, str]:
    if not cfg.access.enabled:
        raise EdgeError("access.enabled is false in edge.json")
    app = call(
        "POST",
        "/accounts/{account}/access/apps",
        {
            "name": "Hibiscus admin",
            "type": "self_hosted",
            "domain": f"{cfg.hostname}/admin",
            "self_hosted_domains": [f"{cfg.hostname}/admin", f"{cfg.hostname}/api/v1/admin"],
            "session_duration": cfg.access.session_duration,
            "app_launcher_visible": False,
            "http_only_cookie_attribute": True,
            "same_site_cookie_attribute": "lax",
        },
    )["result"]
    app_id = str(app["id"])
    call(
        "POST",
        f"/accounts/{{account}}/access/apps/{app_id}/policies",
        {
            "name": "Hibiscus platform admins",
            "decision": "allow",
            "include": [{"email": {"email": e}} for e in cfg.access.allowed_emails],
        },
    )
    return {"app_id": app_id, "aud": str(app["aud"])}


def _bind(call: Transport, zone: str, account: str) -> Transport:
    def bound(method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        if "{zone}" in path and not zone:
            raise EdgeError("CF_ZONE_ID is not set")
        if "{account}" in path and not account:
            raise EdgeError("CF_ACCOUNT_ID is not set")
        return call(method, path.replace("{zone}", zone).replace("{account}", account), body)

    return bound


def load_config(path: Path = CONFIG_PATH) -> EdgeConfig:
    return EdgeConfig.from_mapping(json.loads(path.read_text()))


def main(argv: list[str] | None = None, transport: Transport | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hibiscus Cloudflare edge configuration")
    parser.add_argument("command", choices=["plan", "diff", "apply", "turnstile-create", "access-create"])
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.config)
        if args.command == "plan":
            print(json.dumps(desired_state(cfg), indent=2))
            return 0
        if transport is None:
            token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
            if not token:
                raise EdgeError("CLOUDFLARE_API_TOKEN is not set")
            transport = http_transport(token)
        call = _bind(transport, os.environ.get("CF_ZONE_ID", ""), os.environ.get("CF_ACCOUNT_ID", ""))
        if args.command == "diff":
            changes = diff(cfg, call)
            for phase, lines in changes.items():
                print(f"[{phase}]")
                print("\n".join(lines))
            if not changes:
                print("no changes")
            return 0
        if args.command == "apply":
            if not args.yes:
                answer = input(f"Replace Hibiscus edge rules on zone for {cfg.hostname}? [y/N] ")
                if answer.strip().lower() != "y":
                    print("aborted")
                    return 1
            for line in apply(cfg, call):
                print(line)
            return 0
        if args.command == "turnstile-create":
            out = turnstile_create(cfg, call)
            print(f"HIBISCUS_TURNSTILE_SITE_KEY={out['sitekey']}")
            print(f"HIBISCUS_TURNSTILE_SECRET_KEY={out['secret']}")
            print("# store both in deploy/.env now; the secret is not shown again", file=sys.stderr)
            return 0
        out = access_create(cfg, call)
        print(f"HIBISCUS_CF_ACCESS_AUD={out['aud']}")
        print("# also set HIBISCUS_CF_ACCESS_TEAM_DOMAIN=<team>.cloudflareaccess.com", file=sys.stderr)
        return 0
    except EdgeError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
