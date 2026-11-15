"""Real client IP (ADR-0008): ``CF-Connecting-IP`` is trusted only when the TCP peer is a trusted
proxy (the reverse-proxy container / Docker gateway of the tunnel's loopback port, configured in
``HIBISCUS_TRUSTED_PROXY_CIDRS``). Otherwise the socket peer is used and the header is ignored."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


class ClientIpResolver:
    def __init__(self, trusted_cidrs: Iterable[str]) -> None:
        self._nets: list[IPNetwork] = [ipaddress.ip_network(c, strict=False) for c in trusted_cidrs]

    def is_trusted(self, peer: str | None) -> bool:
        if not peer:
            return False
        try:
            addr = ipaddress.ip_address(peer)
        except ValueError:
            return False
        return any(addr in n for n in self._nets)

    def resolve(self, peer: str | None, cf_connecting_ip: str | None) -> str | None:
        """Return the client IP as a normalised string, or None if unknown."""
        if cf_connecting_ip and self.is_trusted(peer):
            try:
                return str(ipaddress.ip_address(cf_connecting_ip.strip()))
            except ValueError:
                pass  # malformed header from a trusted peer: fall back to the peer
        if peer:
            try:
                return str(ipaddress.ip_address(peer))
            except ValueError:
                return None
        return None
