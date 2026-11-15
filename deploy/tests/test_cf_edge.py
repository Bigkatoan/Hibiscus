"""Cloudflare edge-as-code: payload generation and the HTTP client against a local fake API server.

The fake server is a real HTTP server on 127.0.0.1 (random port) that records requests and serves
canned Cloudflare-style responses; it stands in for api.cloudflare.com, which tests must never call.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

import cf_edge

BASE_CFG: dict[str, Any] = json.loads((cf_edge.CONFIG_PATH).read_text())


def cfg(**overrides: Any) -> cf_edge.EdgeConfig:
    data = json.loads(json.dumps(BASE_CFG))
    data.update(overrides)
    return cf_edge.EdgeConfig.from_mapping(data)


class FakeCloudflare(BaseHTTPRequestHandler):
    calls: ClassVar[list[tuple[str, str, dict[str, Any] | None, str]]] = []
    existing: ClassVar[dict[str, list[dict[str, Any]]]] = {}

    def log_message(self, *_: Any) -> None:
        return

    def _reply(self, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length)) if length else None
        self.calls.append((self.command, self.path, body, self.headers.get("Authorization", "")))
        if self.headers.get("Authorization") != "Bearer test-token":
            self._reply(403, {"success": False, "errors": [{"code": 10000, "message": "auth"}]})
            return
        if self.command == "GET" and "/rulesets/phases/" in self.path:
            phase = self.path.split("/rulesets/phases/")[1].split("/")[0]
            if phase in self.existing:
                self._reply(200, {"success": True, "result": {"rules": self.existing[phase]}})
            else:
                self._reply(404, {"success": False, "errors": [{"code": 10003, "message": "not found"}]})
            return
        if self.path.endswith("/challenges/widgets"):
            self._reply(
                200, {"success": True, "result": {"sitekey": "0x4AAA-site", "secret": "0x4AAA-secret"}}
            )
            return
        if self.path.endswith("/access/apps"):
            self._reply(200, {"success": True, "result": {"id": "app-1", "aud": "aud-tag-123"}})
            return
        if "/rulesets/phases/http_ratelimit/" in self.path and body and len(body["rules"]) > 1:
            self._reply(400, {"success": False, "errors": [{"code": 20120, "message": "limit exceeded"}]})
            return
        self._reply(200, {"success": True, "result": {}})

    do_GET = _handle  # noqa: N815 (BaseHTTPRequestHandler API)
    do_PUT = _handle  # noqa: N815
    do_POST = _handle  # noqa: N815
    do_PATCH = _handle  # noqa: N815


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    FakeCloudflare.calls = []
    FakeCloudflare.existing = {}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeCloudflare)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    monkeypatch.setenv("CF_ZONE_ID", "zone123")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acct456")
    yield f"http://127.0.0.1:{srv.server_address[1]}/client/v4"
    srv.shutdown()


def test_committed_config_is_valid_and_conservative() -> None:
    c = cf_edge.load_config()
    assert c.hostname == "robot.example.com"
    assert c.plan == "free"
    assert c.bot_fight_mode is None, "BFM would challenge the CLI on the Free plan"
    assert c.zone_settings == ()
    assert not c.access.enabled


def test_free_plan_payloads_respect_plan_limits() -> None:
    state = cf_edge.desired_state(cfg())
    rl = state["rulesets"]["http_ratelimit"]
    assert len(rl) == 1
    assert rl[0]["ratelimit"]["period"] == 10
    assert rl[0]["ratelimit"]["mitigation_timeout"] <= 10
    assert rl[0]["ratelimit"]["characteristics"] == ["cf.colo.id", "ip.src"]
    assert '"/api/v1/auth/"' in rl[0]["expression"]
    exprs = " ".join(r["expression"] for rules in state["rulesets"].values() for r in rules)
    assert " matches " not in exprs, "regex needs Business plan"
    assert "http.request.body" not in exprs
    assert all(r["ref"].startswith("hibiscus_") for rules in state["rulesets"].values() for r in rules)
    assert all(
        'http.host eq "robot.example.com"' in r["expression"]
        for rules in state["rulesets"].values()
        for r in rules
    )
    assert state["settings"] == {}
    assert state["bot_management"] is None


def test_pro_plan_adds_api_limit_and_managed_waf() -> None:
    state = cf_edge.desired_state(cfg(plan="pro"))
    assert [r["ref"] for r in state["rulesets"]["http_ratelimit"]] == ["hibiscus_rl_auth", "hibiscus_rl_api"]
    assert state["rulesets"]["http_ratelimit"][1]["ratelimit"]["period"] == 60
    assert state["managed_waf"]["ruleset_id"] == cf_edge.CLOUDFLARE_MANAGED_RULESET


def test_internal_paths_and_cache_bypass() -> None:
    state = cf_edge.desired_state(cfg())
    custom = {r["ref"]: r for r in state["rulesets"]["http_request_firewall_custom"]}
    assert '"/metrics" "/readyz"' in custom["hibiscus_block_internal_paths"]["expression"]
    assert custom["hibiscus_block_internal_paths"]["action"] == "block"
    cache = state["rulesets"]["http_request_cache_settings"][0]
    assert cache["action_parameters"] == {"cache": False}


def test_geo_rule_only_when_countries_listed() -> None:
    refs = [r["ref"] for r in cf_edge.custom_rules(cfg())]
    assert "hibiscus_geo_challenge" not in refs
    rules = cf_edge.custom_rules(cfg(allowed_countries=["vn", "JP"]))
    geo = next(r for r in rules if r["ref"] == "hibiscus_geo_challenge")
    assert '{"VN" "JP"}' in geo["expression"] and geo["action"] == "managed_challenge"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"plan": "gold"}, "plan must be"),
        ({"allowed_countries": ["VNM"]}, "country"),
        ({"hostname": 'evil" or true'}, "hostname"),
        ({"zone_settings": {"ssl": "off"}}, "not managed"),
        ({"access": {"enabled": True, "allowed_emails": []}}, "allowed email"),
    ],
)
def test_invalid_config_rejected(override: dict[str, Any], message: str) -> None:
    with pytest.raises(cf_edge.EdgeError, match=message):
        cfg(**override)


def test_quoting_in_expressions() -> None:
    assert cf_edge._q('a"b\\c') == '"a\\"b\\\\c"'


def test_apply_keeps_foreign_rules_and_replaces_ours(server: str) -> None:
    foreign = {
        "id": "x1",
        "ref": "other_site_rule",
        "expression": 'http.host eq "blog.example.com"',
        "action": "block",
        "version": "3",
        "last_updated": "2026-01-01",
    }
    stale = {"id": "x2", "ref": "hibiscus_old_rule", "expression": "true", "action": "block"}
    FakeCloudflare.existing = {"http_request_firewall_custom": [foreign, stale]}
    call = cf_edge._bind(cf_edge.http_transport("test-token", server), "zone123", "acct456")
    out = cf_edge.apply(cfg(), call)
    puts = {c[1]: c[2] for c in FakeCloudflare.calls if c[0] == "PUT"}
    custom = puts["/client/v4/zones/zone123/rulesets/phases/http_request_firewall_custom/entrypoint"]
    assert custom is not None
    refs = [r["ref"] for r in custom["rules"]]
    assert refs[0] == "other_site_rule"
    assert "hibiscus_old_rule" not in refs
    assert "hibiscus_block_internal_paths" in refs
    assert "id" not in custom["rules"][0] and "version" not in custom["rules"][0]  # read-only fields dropped
    assert any("1 other rules kept" in line for line in out)
    # free plan: no managed WAF PUT, no zone settings, no bot management call
    paths = [c[1] for c in FakeCloudflare.calls]
    assert not any("firewall_managed" in p or "/settings/" in p or "bot_management" in p for p in paths)
    assert all(c[3] == "Bearer test-token" for c in FakeCloudflare.calls)


def test_apply_explicit_zone_settings_and_bfm(server: str) -> None:
    call = cf_edge._bind(cf_edge.http_transport("test-token", server), "zone123", "acct456")
    cf_edge.apply(cfg(zone_settings={"min_tls_version": "1.2"}, bot_fight_mode=False), call)
    calls = {(c[0], c[1]): c[2] for c in FakeCloudflare.calls}
    assert calls[("PATCH", "/client/v4/zones/zone123/settings/min_tls_version")] == {"value": "1.2"}
    assert calls[("PUT", "/client/v4/zones/zone123/bot_management")] == {"fight_mode": False}


def test_api_error_surfaces(server: str) -> None:
    call = cf_edge._bind(cf_edge.http_transport("wrong", server), "zone123", "acct456")
    with pytest.raises(cf_edge.EdgeError, match="HTTP 403"):
        cf_edge.apply(cfg(), call)


def test_plan_limit_error_from_api(server: str) -> None:
    FakeCloudflare.existing = {
        "http_ratelimit": [{"ref": "someone_else", "expression": "true", "action": "block", "ratelimit": {}}]
    }
    call = cf_edge._bind(cf_edge.http_transport("test-token", server), "zone123", "acct456")
    with pytest.raises(cf_edge.EdgeError, match="limit exceeded"):
        cf_edge.apply(cfg(), call)


def test_diff_reports_only_hibiscus_changes(server: str) -> None:
    FakeCloudflare.existing = {
        "http_request_firewall_custom": [
            {"ref": "other", "expression": "true", "action": "block"},
            {"ref": "hibiscus_old_rule", "expression": "true", "action": "block"},
        ]
    }
    call = cf_edge._bind(cf_edge.http_transport("test-token", server), "zone123", "acct456")
    changes = cf_edge.diff(cfg(), call)
    custom = changes["http_request_firewall_custom"]
    assert any(line.startswith("- hibiscus_old_rule") for line in custom)
    assert not any("other" in line.split(":")[0] for line in custom)
    assert "http_ratelimit" in changes  # entrypoint 404 -> everything is new


def test_cli_turnstile_and_access(server: str, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    transport = cf_edge.http_transport("test-token", server)
    assert cf_edge.main(["turnstile-create"], transport=transport) == 0
    out = capsys.readouterr().out
    assert "HIBISCUS_TURNSTILE_SITE_KEY=0x4AAA-site" in out
    widget = next(c for c in FakeCloudflare.calls if c[1].endswith("/challenges/widgets"))
    assert widget[1] == "/client/v4/accounts/acct456/challenges/widgets"
    assert widget[2] is not None and widget[2]["domains"] == ["robot.example.com"]

    conf = json.loads(json.dumps(BASE_CFG))
    conf["access"] = {"enabled": True, "allowed_emails": ["admin@example.com"], "session_duration": "4h"}
    path = tmp_path / "edge.json"
    path.write_text(json.dumps(conf))
    assert cf_edge.main(["access-create", "--config", str(path)], transport=transport) == 0
    assert "HIBISCUS_CF_ACCESS_AUD=aud-tag-123" in capsys.readouterr().out
    app = next(c for c in FakeCloudflare.calls if c[1].endswith("/access/apps"))
    assert app[2] is not None
    assert app[2]["self_hosted_domains"] == ["robot.example.com/admin", "robot.example.com/api/v1/admin"]
    policy = next(c for c in FakeCloudflare.calls if c[1].endswith("/policies"))
    assert policy[2] is not None and policy[2]["include"] == [{"email": {"email": "admin@example.com"}}]


def test_cli_plan_and_missing_token(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert cf_edge.main(["plan"]) == 0
    assert "hibiscus_rl_auth" in capsys.readouterr().out
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    assert cf_edge.main(["diff"]) == 2
    assert "CLOUDFLARE_API_TOKEN" in capsys.readouterr().err


def test_cli_apply_requires_confirmation(server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert cf_edge.main(["apply"], transport=cf_edge.http_transport("test-token", server)) == 1
    assert not any(c[0] == "PUT" for c in FakeCloudflare.calls)
