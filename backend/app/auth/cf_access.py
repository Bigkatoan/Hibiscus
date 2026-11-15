"""Optional Cloudflare Access gate for ``/api/v1/admin*`` (CONTRACT_NOTES §3, §4.4; off by default).

When ``HIBISCUS_CF_ACCESS_TEAM_DOMAIN`` and ``HIBISCUS_CF_ACCESS_AUD`` are set, admin requests must
carry ``Cf-Access-Jwt-Assertion``: an RS256 JWT signed by the team's keys
(``https://<team>/cdn-cgi/access/certs``), ``aud`` = the application AUD tag, ``iss`` =
``https://<team>``. Failure => 403 ``forbidden``. App-level auth (session + 2FA) still applies.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import jwt
from fastapi import Request

from app.core.errors import ErrorCode, ProblemError

log = logging.getLogger("hibiscus.cf_access")

HEADER = "Cf-Access-Jwt-Assertion"
JwksFetcher = Callable[[], Awaitable[dict[str, Any]]]


class CfAccessVerifier:
    def __init__(
        self, team_domain: str, aud: str, *, fetch_jwks: JwksFetcher | None = None, cache_ttl_s: int = 3600
    ) -> None:
        self.team_domain = team_domain.removeprefix("https://").rstrip("/")
        self.aud = aud
        self.issuer = f"https://{self.team_domain}"
        self._fetch = fetch_jwks or self._http_fetch
        self._ttl = cache_ttl_s
        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def _http_fetch(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{self.issuer}/cdn-cgi/access/certs")
            r.raise_for_status()
            data: dict[str, Any] = r.json()
            return data

    async def _key_for(self, kid: str | None) -> Any:
        async with self._lock:
            stale = time.monotonic() - self._fetched_at > self._ttl
            if stale or (kid is not None and kid not in self._keys):
                try:
                    jwks = await self._fetch()
                except (httpx.HTTPError, ValueError):
                    log.warning("cloudflare access certs unavailable")
                    jwks = {"keys": []}
                keys = {}
                for k in jwks.get("keys", []):
                    try:
                        keys[str(k.get("kid"))] = jwt.PyJWK.from_json(json.dumps(k)).key
                    except (jwt.PyJWTError, ValueError, TypeError):
                        continue
                if keys:
                    self._keys = keys
                    self._fetched_at = time.monotonic()
            return self._keys.get(str(kid)) if kid is not None else None

    async def verify_token(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as e:
            raise ProblemError(403, ErrorCode.FORBIDDEN, "Cloudflare Access assertion invalid") from e
        key = await self._key_for(header.get("kid"))
        if key is None:
            raise ProblemError(403, ErrorCode.FORBIDDEN, "Cloudflare Access assertion invalid")
        try:
            claims: dict[str, Any] = jwt.decode(
                token, key, algorithms=["RS256"], audience=self.aud, issuer=self.issuer, leeway=30
            )
        except jwt.InvalidTokenError as e:
            raise ProblemError(403, ErrorCode.FORBIDDEN, "Cloudflare Access assertion invalid") from e
        return claims

    async def verify_request(self, request: Request) -> dict[str, Any]:
        token = request.headers.get(HEADER)
        if not token:
            raise ProblemError(403, ErrorCode.FORBIDDEN, "Cloudflare Access assertion missing")
        return await self.verify_token(token)
