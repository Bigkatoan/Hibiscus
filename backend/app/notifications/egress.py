"""SSRF-safe outbound HTTPS for user-supplied webhook targets (the API is internet-facing).

Rules enforced on every request (and on channel creation):

* ``https`` only, no userinfo, no fragments, printable ASCII after IDNA, <= 512 chars.
* The host is resolved here; **every** resolved address must be publicly routable: loopback,
  RFC 1918, link-local (incl. ``169.254.169.254`` metadata), CGNAT ``100.64/10``, multicast,
  reserved/benchmark/documentation ranges, ULA ``fc00::/7``, IPv4-mapped / 6to4 / NAT64 / Teredo
  wrappers of any of those are rejected (IPv4 + IPv6).
* The connection is **pinned** to the vetted IP (URL host = IP, ``Host`` header + TLS SNI /
  certificate verification = original name), so DNS cannot rebind between check and connect.
* No redirects (3xx is a non-retryable failure), proxies from the environment are ignored,
  connect/total timeouts, the response body is read at most ``max_response_bytes`` and never
  echoed back to the caller (no read oracle).
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
import ssl
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
Resolver = Callable[[str, int], Awaitable[list[str]]]

MAX_URL_LEN = 512
USER_AGENT = "Hibiscus-Notifier/0.1"

_BLOCKED: tuple[IPNetwork, ...] = tuple(
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "255.255.255.255/32",
        "::/128",
        "::1/128",
        "::ffff:0:0/96",
        "64:ff9b:1::/48",
        "100::/64",
        "2001::/23",
        "2001:db8::/32",
        "fc00::/7",
        "fe80::/10",
        "fec0::/10",
        "ff00::/8",
    )
)
_NAT64 = ipaddress.ip_network("64:ff9b::/96")


class TargetRejectedError(Exception):
    """The target is not acceptable (syntax or SSRF policy). ``reason`` is a stable code."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


class DeliveryError(Exception):
    """Delivery attempt failed. ``retryable`` decides between backoff and permanent failure."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable


def _embedded_v4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip.sixtofour is not None:
        return ip.sixtofour
    if ip in _NAT64:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def is_public_ip(ip: IPAddress) -> bool:
    """True only for globally routable unicast addresses (see module docstring)."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.teredo is not None:
            return False
        v4 = _embedded_v4(ip)
        if v4 is not None and not is_public_ip(v4):
            return False
        if ip.ipv4_mapped is not None:
            return True  # public v4 behind ::ffff: (already vetted above)
    if any(ip in net for net in _BLOCKED):
        return False
    return bool(
        ip.is_global
        and not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    )


async def system_resolve(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    return [str(info[4][0]) for info in infos]


@dataclass(frozen=True)
class ParsedUrl:
    parts: SplitResult
    host: str  # IDNA (ASCII) host name or IP literal, no brackets
    port: int

    @property
    def url(self) -> str:
        return urlunsplit(self.parts)


def parse_https_url(url: str) -> ParsedUrl:
    if len(url) > MAX_URL_LEN:
        raise TargetRejectedError("url_too_long", "URL is longer than 512 characters")
    if any(c.isspace() or ord(c) < 0x20 or ord(c) == 0x7F for c in url):
        raise TargetRejectedError("url_invalid", "URL contains whitespace or control characters")
    try:
        parts = urlsplit(url)
        port = parts.port or 443
    except ValueError as e:
        raise TargetRejectedError("url_invalid", "URL is not valid") from e
    if parts.scheme.lower() != "https":
        raise TargetRejectedError("https_required", "Only https:// URLs are allowed")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise TargetRejectedError("url_userinfo", "Credentials in the URL are not allowed")
    if parts.fragment:
        raise TargetRejectedError("url_invalid", "URL fragments are not allowed")
    raw_host = parts.hostname or ""
    if not raw_host:
        raise TargetRejectedError("url_invalid", "URL has no host")
    try:
        ipaddress.ip_address(raw_host)
        host = raw_host
    except ValueError:
        try:
            host = raw_host.rstrip(".").encode("idna").decode("ascii").lower()
        except UnicodeError as e:
            raise TargetRejectedError("url_invalid", "Host name is not valid") from e
    if not host or len(host) > 253 or ("." not in host and ":" not in host):
        raise TargetRejectedError("url_invalid", "Host name is not valid")
    if not 0 < port < 65536:
        raise TargetRejectedError("url_invalid", "Port is not valid")
    netloc = f"[{host}]" if ":" in host else host
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    clean = SplitResult("https", netloc, parts.path or "/", parts.query, "")
    return ParsedUrl(parts=clean, host=host, port=port)


@dataclass
class EgressPolicy:
    resolver: Resolver = system_resolve
    #: Exempt networks (tests only; refused in prod by ``setup_app``).
    allow: Sequence[IPNetwork] = ()
    ssl_context: ssl.SSLContext | None = None
    connect_timeout_s: float = 5.0
    timeout_s: float = 10.0
    max_response_bytes: int = 64 * 1024
    transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = field(default=None, repr=False)

    def allowed(self, ip: IPAddress) -> bool:
        if any(ip.version == net.version and ip in net for net in self.allow):
            return True
        return is_public_ip(ip)

    async def vet(self, parsed: ParsedUrl) -> str:
        """Resolve and check every address; returns the IP to pin the connection to."""
        try:
            literal: IPAddress | None = ipaddress.ip_address(parsed.host)
        except ValueError:
            literal = None
        if literal is not None:
            addrs = [str(literal)]
        else:
            try:
                addrs = await asyncio.wait_for(
                    self.resolver(parsed.host, parsed.port), timeout=self.connect_timeout_s
                )
            except (OSError, TimeoutError, UnicodeError) as e:
                raise TargetRejectedError("dns_failed", "Host name does not resolve") from e
        if not addrs:
            raise TargetRejectedError("dns_failed", "Host name does not resolve")
        ips: list[IPAddress] = []
        for a in addrs:
            try:
                ips.append(ipaddress.ip_address(a.split("%", 1)[0]))
            except ValueError as e:
                raise TargetRejectedError("dns_failed", "Host name resolved to an invalid address") from e
        for ip in ips:
            if not self.allowed(ip):
                raise TargetRejectedError(
                    "address_not_allowed", "Target resolves to a private or reserved network address"
                )
        return str(ips[0])

    async def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None
    ) -> int:
        """POST ``payload`` to ``url`` (pinned, no redirects). Returns the 2xx status code."""
        parsed = parse_https_url(url)
        ip = await self.vet(parsed)
        pinned_host = f"[{ip}]" if ":" in ip else ip
        netloc = pinned_host if parsed.parts.port is None else f"{pinned_host}:{parsed.parts.port}"
        target = urlunsplit(parsed.parts._replace(netloc=netloc))
        host_header = parsed.host if parsed.parts.port is None else f"{parsed.host}:{parsed.parts.port}"
        if ":" in parsed.host and not parsed.host.startswith("["):
            host_header = f"[{parsed.host}]" + ("" if parsed.parts.port is None else f":{parsed.parts.port}")
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        req_headers = {
            "Host": host_header,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            **(headers or {}),
        }
        verify: ssl.SSLContext | bool = self.ssl_context if self.ssl_context is not None else True
        timeout = httpx.Timeout(self.timeout_s, connect=self.connect_timeout_s)
        transport = self.transport_factory() if self.transport_factory else None
        try:
            async with asyncio.timeout(self.timeout_s + self.connect_timeout_s):
                async with httpx.AsyncClient(
                    verify=verify,
                    timeout=timeout,
                    follow_redirects=False,
                    trust_env=False,
                    transport=transport,
                ) as client:
                    request = client.build_request(
                        "POST",
                        target,
                        content=body,
                        headers=req_headers,
                        extensions={"sni_hostname": parsed.host},
                    )
                    response = await client.send(request, stream=True)
                    try:
                        read = 0
                        async for chunk in response.aiter_raw():
                            read += len(chunk)
                            if read >= self.max_response_bytes:
                                break
                    finally:
                        await response.aclose()
        except TimeoutError as e:
            raise DeliveryError("timed out", retryable=True) from e
        except httpx.HTTPError as e:
            # never include the URL (it may embed a token)
            raise DeliveryError(f"connection failed ({type(e).__name__})", retryable=True) from e
        except ssl.SSLError as e:
            raise DeliveryError("TLS handshake failed", retryable=True) from e
        status = response.status_code
        if 200 <= status < 300:
            return status
        if 300 <= status < 400:
            raise DeliveryError(f"HTTP {status}: redirects are not followed", retryable=False)
        retryable = status == 429 or status >= 500 or status == 408
        raise DeliveryError(f"HTTP {status}", retryable=retryable)


def build_ssl_context(ca_file: str | None) -> ssl.SSLContext | None:
    if not ca_file:
        return None
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cafile=ca_file)
    return ctx


def parse_networks(cidrs: Sequence[str]) -> tuple[IPNetwork, ...]:
    return tuple(ipaddress.ip_network(c, strict=False) for c in cidrs)
