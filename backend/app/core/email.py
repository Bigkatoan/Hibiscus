"""Outgoing email: pluggable ``EmailSender`` (PLAN §3.1, CONTRACT_NOTES §4.1).

Providers
---------
* ``cloudflare`` (production default): HMAC-signed JSON ``POST`` to a Cloudflare Worker that owns
  the ``send_email`` binding (Worker source: ``deploy/cloudflare/email-worker/``, owner A8).
  Wire protocol (v1)::

      POST <HIBISCUS_EMAIL_WORKER_URL>
      Content-Type: application/json
      X-Hibiscus-Timestamp: <unix seconds>
      X-Hibiscus-Signature: v1=<hex(HMAC-SHA256(secret, "<timestamp>." + raw_body))>
      {"message_id": "<uuid>", "from": "...", "to": "...", "subject": "...",
       "text": "...", "html": "..." | null, "reply_to": null}

  The Worker must reject a timestamp outside ±300 s, compare the signature in constant time and
  answer ``2xx`` on success. Any other status / network error raises :class:`EmailError`.
* ``smtp``: stdlib ``smtplib`` (STARTTLS or implicit TLS) in a worker thread.
* ``none``: nothing is sent; flows fall back to admin-shared links (``accept_url``,
  ``POST /admin/users/{id}/password-reset-link``).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import smtplib
import ssl
import time
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, parseaddr
from typing import Protocol

import httpx

from app.core.settings import Settings

log = logging.getLogger("hibiscus.email")

SIGNATURE_HEADER = "X-Hibiscus-Signature"
TIMESTAMP_HEADER = "X-Hibiscus-Timestamp"
REPLAY_WINDOW_S = 300


class EmailError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class EmailSender(Protocol):
    provider: str

    @property
    def enabled(self) -> bool: ...

    async def send(self, message: EmailMessage) -> None: ...


class NoneEmailSender:
    """Delivery disabled. Keeps the last messages in memory (dev / tests visibility only)."""

    provider = "none"

    def __init__(self) -> None:
        self.outbox: list[EmailMessage] = []

    @property
    def enabled(self) -> bool:
        return False

    async def send(self, message: EmailMessage) -> None:
        self.outbox = [*self.outbox[-49:], message]
        log.info("email delivery disabled; message dropped", extra={"message_id": message.message_id})


def sign_body(secret: str, timestamp: int, body: bytes) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"v1={mac}"


def verify_signature(
    secret: str, timestamp: str, body: bytes, signature: str, *, now: float | None = None
) -> bool:
    """Reference verifier (mirrors what the Worker must do); used by tests."""
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs((now if now is not None else time.time()) - ts) > REPLAY_WINDOW_S:
        return False
    return hmac.compare_digest(sign_body(secret, ts, body), signature)


class CloudflareWorkerEmailSender:
    provider = "cloudflare"

    def __init__(
        self,
        url: str,
        secret: str,
        sender: str,
        *,
        timeout_s: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not url.startswith(("https://", "http://")):
            raise ValueError("email worker url must be http(s)")
        self._url = url
        self._secret = secret
        self._from = sender
        self._timeout = timeout_s
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return True

    async def send(self, message: EmailMessage) -> None:
        body = json.dumps(
            {
                "message_id": message.message_id,
                "from": self._from,
                "to": message.to,
                "subject": message.subject,
                "text": message.text,
                "html": message.html,
                "reply_to": None,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        ts = int(time.time())
        headers = {
            "Content-Type": "application/json",
            TIMESTAMP_HEADER: str(ts),
            SIGNATURE_HEADER: sign_body(self._secret, ts, body),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as c:
                r = await c.post(self._url, content=body, headers=headers)
        except httpx.HTTPError as e:
            raise EmailError(f"email worker unreachable: {type(e).__name__}") from e
        if r.status_code // 100 != 2:
            raise EmailError(f"email worker returned HTTP {r.status_code}")
        log.info("email sent", extra={"message_id": message.message_id, "provider": self.provider})


class SmtpEmailSender:
    provider = "smtp"

    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        *,
        username: str | None = None,
        password: str | None = None,
        starttls: bool = True,
        use_ssl: bool = False,
        timeout_s: float = 10.0,
    ) -> None:
        self._host, self._port, self._from = host, port, sender
        self._username, self._password = username, password
        self._starttls, self._ssl, self._timeout = starttls, use_ssl, timeout_s

    @property
    def enabled(self) -> bool:
        return True

    def _build(self, message: EmailMessage) -> MimeMessage:
        mime = MimeMessage()
        name, addr = parseaddr(self._from)
        mime["From"] = formataddr((name, addr))
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime["Message-ID"] = f"<{message.message_id}@{addr.split('@')[-1] or 'hibiscus'}>"
        mime.set_content(message.text)
        if message.html:
            mime.add_alternative(message.html, subtype="html")
        return mime

    def _send_sync(self, mime: MimeMessage) -> None:
        ctx = ssl.create_default_context()
        smtp: smtplib.SMTP
        if self._ssl:
            smtp = smtplib.SMTP_SSL(self._host, self._port, timeout=self._timeout, context=ctx)
        else:
            smtp = smtplib.SMTP(self._host, self._port, timeout=self._timeout)
        with smtp:
            if self._starttls and not self._ssl:
                smtp.starttls(context=ctx)
            if self._username:
                smtp.login(self._username, self._password or "")
            smtp.send_message(mime)

    async def send(self, message: EmailMessage) -> None:
        try:
            await asyncio.to_thread(self._send_sync, self._build(message))
        except (OSError, smtplib.SMTPException) as e:
            raise EmailError(f"smtp delivery failed: {type(e).__name__}") from e
        log.info("email sent", extra={"message_id": message.message_id, "provider": self.provider})


def create_email_sender(settings: Settings) -> EmailSender:
    if settings.email_provider == "cloudflare":
        if not settings.email_worker_url:
            raise ValueError("email_provider=cloudflare needs HIBISCUS_EMAIL_WORKER_URL")
        return CloudflareWorkerEmailSender(
            settings.email_worker_url,
            settings.email_worker_secret,
            settings.email_from,
            timeout_s=settings.email_timeout_s,
        )
    if settings.email_provider == "smtp":
        return SmtpEmailSender(
            settings.smtp_host,
            settings.smtp_port,
            settings.email_from,
            username=settings.smtp_username,
            password=settings.smtp_password,
            starttls=settings.smtp_starttls,
            use_ssl=settings.smtp_ssl,
            timeout_s=settings.email_timeout_s,
        )
    return NoneEmailSender()


async def send_safely(sender: EmailSender, message: EmailMessage) -> bool:
    """Send and swallow delivery errors (logged). Returns True when delivered."""
    if not sender.enabled:
        await sender.send(message)
        return False
    try:
        await sender.send(message)
        return True
    except EmailError:
        log.exception("email delivery failed", extra={"message_id": message.message_id})
        return False
