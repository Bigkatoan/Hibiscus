"""SSRF guard: address classification, URL parsing, pinning, redirects, timeouts, size cap."""

from __future__ import annotations

import ipaddress
import time
from pathlib import Path

import pytest

from app.notifications.egress import (
    DeliveryError,
    EgressPolicy,
    TargetRejectedError,
    build_ssl_context,
    is_public_ip,
    parse_https_url,
    parse_networks,
)
from tests.notifications.helpers import HOOK_HOST, TEST_DNS, HookServer, fake_dns

BLOCKED = [
    "127.0.0.1",
    "127.255.255.254",
    "10.0.0.1",
    "172.16.5.4",
    "192.168.1.1",
    "169.254.169.254",  # cloud metadata
    "100.64.0.1",  # CGNAT
    "100.100.100.200",  # Alibaba metadata (CGNAT range)
    "0.0.0.0",  # noqa: S104 - an address under test, not a bind
    "224.0.0.1",
    "239.255.255.250",
    "255.255.255.255",
    "240.0.0.1",
    "198.18.0.1",
    "192.0.2.10",
    "::1",
    "::",
    "fe80::1",
    "fd00::1",
    "fd00:ec2::254",  # AWS IPv6 metadata
    "ff02::1",
    "::ffff:127.0.0.1",
    "::ffff:169.254.169.254",
    "64:ff9b::a00:1",  # NAT64 of 10.0.0.1
    "2002:a00:1::1",  # 6to4 of 10.0.0.1
    "2001:0:4136:e378:8000:63bf:3fff:fdd2",  # Teredo
    "2001:db8::1",
]
PUBLIC = ["93.184.215.14", "1.1.1.1", "8.8.8.8", "2606:4700:4700::1111", "::ffff:8.8.8.8"]


@pytest.mark.parametrize("ip", BLOCKED)
def test_blocked_addresses(ip: str) -> None:
    assert not is_public_ip(ipaddress.ip_address(ip))


@pytest.mark.parametrize("ip", PUBLIC)
def test_public_addresses(ip: str) -> None:
    assert is_public_ip(ipaddress.ip_address(ip))


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("http://example.com/hook", "https_required"),
        ("ftp://example.com/hook", "https_required"),
        ("https://user:pw@example.com/hook", "url_userinfo"),
        ("https://example.com/a b", "url_invalid"),
        ("https://example.com/#frag", "url_invalid"),
        ("https:///nohost", "url_invalid"),
        ("https://intranet/hook", "url_invalid"),
        ("https://example.com:99999/", "url_invalid"),
        ("https://example.com/" + "a" * 600, "url_too_long"),
    ],
)
def test_parse_rejects(url: str, reason: str) -> None:
    with pytest.raises(TargetRejectedError) as ei:
        parse_https_url(url)
    assert ei.value.reason == reason


def test_parse_normalises_idna() -> None:
    p = parse_https_url("https://BÜCHER.example/x?y=1")
    assert p.host == "xn--bcher-kva.example" and p.port == 443
    assert p.url == "https://xn--bcher-kva.example/x?y=1"
    assert parse_https_url("https://[2606:4700:4700::1111]:8443/h").host == "2606:4700:4700::1111"


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/hook",
        "https://10.0.0.8/hook",
        "https://169.254.169.254/latest/meta-data/",
        "https://[::1]/hook",
        "https://[::ffff:127.0.0.1]/hook",
        "https://private.test/hook",  # DNS name resolving to a private IP
        "https://mixed.test/hook",  # one public + one private answer => rejected
        "https://cgnat.test/hook",
        "https://v6local.test/hook",
        "https://localhost.localdomain/hook",
    ],
)
async def test_vet_rejects_private_targets(url: str) -> None:
    policy = EgressPolicy(resolver=fake_dns({**TEST_DNS, "localhost.localdomain": ["127.0.0.1"]}))
    with pytest.raises(TargetRejectedError) as ei:
        await policy.post_json(url, {"x": 1})
    assert ei.value.reason == "address_not_allowed"


async def test_real_dns_names_resolving_to_loopback_rejected() -> None:
    policy = EgressPolicy()  # system resolver (glibc / /etc/hosts)
    with pytest.raises(TargetRejectedError) as ei:  # bare "localhost" is not even a valid target
        await policy.post_json("https://localhost/x", {})
    assert ei.value.reason == "url_invalid"
    import socket

    try:
        socket.getaddrinfo("localhost.localdomain", 443)
    except OSError:
        pytest.skip("localhost.localdomain does not resolve here")
    with pytest.raises(TargetRejectedError) as ei:
        await policy.post_json("https://localhost.localdomain/x", {})
    assert ei.value.reason == "address_not_allowed"
    with pytest.raises(TargetRejectedError) as ei:
        await policy.vet(parse_https_url("https://does-not-exist.invalid/x"))
    assert ei.value.reason == "dns_failed"


def _policy(hook: HookServer, **kw: object) -> EgressPolicy:
    return EgressPolicy(
        resolver=fake_dns(TEST_DNS),
        allow=parse_networks(["127.0.0.1/32"]),
        ssl_context=build_ssl_context(str(hook.ca)),
        connect_timeout_s=2.0,
        timeout_s=2.0,
        **kw,  # type: ignore[arg-type]
    )


async def test_pinned_request_keeps_host_and_sni(hook: HookServer) -> None:
    calls: list[str] = []

    async def resolver(host: str, port: int) -> list[str]:
        calls.append(host)
        return ["127.0.0.1"]

    policy = _policy(hook)
    policy.resolver = resolver
    status = await policy.post_json(hook.url("/in?x=1"), {"hello": "wörld"})
    assert status == 200 and calls == [HOOK_HOST]  # resolved exactly once, then pinned
    got = hook.received[-1]
    assert got.path == "/in?x=1" and got.body == {"hello": "wörld"}
    assert got.headers["host"] == f"{HOOK_HOST}:{hook.port}"
    assert got.headers["user-agent"].startswith("Hibiscus-Notifier")


async def test_tls_is_verified(hook: HookServer) -> None:
    policy = _policy(hook)
    policy.ssl_context = None  # system trust store does not know the test CA
    with pytest.raises(DeliveryError) as ei:
        await policy.post_json(hook.url("/in"), {})
    assert ei.value.retryable
    assert str(hook.port) not in ei.value.message and HOOK_HOST not in ei.value.message


async def test_redirect_not_followed(hook: HookServer) -> None:
    hook.responder = lambda p: (
        (302, {"Location": "https://169.254.169.254/latest/meta-data/"}, b"") if p == "/r" else (200, {}, b"")
    )
    with pytest.raises(DeliveryError) as ei:
        await _policy(hook).post_json(hook.url("/r"), {})
    assert not ei.value.retryable and "redirect" in ei.value.message
    assert [r.path for r in hook.received] == ["/r"]


async def test_status_classification(hook: HookServer) -> None:
    for status, retryable in ((500, True), (503, True), (429, True), (404, False), (400, False)):

        def respond(_p: str, s: int = status) -> tuple[int, dict[str, str], bytes]:
            return s, {}, b"nope"

        hook.responder = respond
        with pytest.raises(DeliveryError) as ei:
            await _policy(hook).post_json(hook.url("/s"), {})
        assert ei.value.retryable is retryable, status
        assert "nope" not in ei.value.message  # response bodies are never echoed


async def test_timeout_and_size_cap(hook: HookServer) -> None:
    def slow(_p: str) -> tuple[int, dict[str, str], bytes]:
        time.sleep(1.5)
        return 200, {}, b""

    hook.responder = slow
    p = _policy(hook)
    p.timeout_s = 0.5
    p.connect_timeout_s = 0.5
    t0 = time.monotonic()
    with pytest.raises(DeliveryError) as ei:
        await p.post_json(hook.url("/slow"), {})
    assert ei.value.retryable and time.monotonic() - t0 < 1.4
    hook.responder = lambda _p: (200, {}, b"x" * (4 * 1024 * 1024))
    assert await _policy(hook, max_response_bytes=1024).post_json(hook.url("/big"), {}) == 200


def test_ca_bundle_loads(tmp_path: Path, hook: HookServer) -> None:
    assert build_ssl_context(None) is None
    assert build_ssl_context(str(hook.ca)) is not None


async def test_certificate_must_match_original_host_name(hook: HookServer) -> None:
    p = _policy(hook)
    p.resolver = fake_dns({"other.test": ["127.0.0.1"]})  # pinned to the hook, cert is for hook.test
    with pytest.raises(DeliveryError) as ei:
        await p.post_json(hook.url("/in", host="other.test"), {})
    assert ei.value.retryable and hook.received == []
