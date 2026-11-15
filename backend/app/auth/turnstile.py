"""Server-side Cloudflare Turnstile verification (login, forgot-password, register-invite)."""

from __future__ import annotations

import logging

import httpx

from app.core.errors import ErrorCode, ProblemError

log = logging.getLogger("hibiscus.turnstile")


class TurnstileVerifier:
    """Disabled (always passes) when no secret key is configured (dev/tests)."""

    def __init__(
        self,
        secret_key: str | None,
        verify_url: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 5.0,
    ) -> None:
        self._secret = secret_key
        self._url = verify_url
        self._transport = transport
        self._timeout = timeout_s

    @property
    def enabled(self) -> bool:
        return bool(self._secret)

    async def verify(self, token: str | None, remote_ip: str | None) -> None:
        if not self._secret:
            return
        if not token:
            raise ProblemError(400, ErrorCode.TURNSTILE_FAILED, "Turnstile token missing")
        data = {"secret": self._secret, "response": token}
        if remote_ip:
            data["remoteip"] = remote_ip
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as c:
                r = await c.post(self._url, data=data)
            ok = r.status_code == 200 and bool(r.json().get("success"))
        except (httpx.HTTPError, ValueError):
            log.warning("turnstile verification unavailable")
            ok = False
        if not ok:
            raise ProblemError(400, ErrorCode.TURNSTILE_FAILED)
