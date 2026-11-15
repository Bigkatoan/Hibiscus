"""Channel targets: validation, encryption at rest, redaction, delivery per kind.

Targets (``NotificationChannelCreate.target``):

* ``email`` — must be the caller's own **verified** account address (no relay to third parties);
  delivered with ``app.core.email.EmailSender`` to the address the account has at send time.
* ``discord`` — ``https://discord.com/api/webhooks/<id>/<token>`` (host allow-list
  ``HIBISCUS_NOTIFY_DISCORD_HOSTS``), body ``{"content", "allowed_mentions": {"parse": []}}``.
* ``webhook`` — any public ``https`` URL; generic JSON body (see :func:`webhook_payload`).
* ``telegram`` — ``<bot_token>:<chat_id>`` (the bot token itself contains one ``:``); sent with
  the Bot API ``sendMessage`` as plain text.

All outbound HTTP goes through :class:`app.notifications.egress.EgressPolicy` (SSRF guard).
Targets are stored AES-256-GCM encrypted (``DataCipher``, AAD bound to user + channel id) and
never returned; responses carry ``target_hint`` only.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.core.crypto import DataCipher
from app.core.email import EmailError, EmailMessage, EmailSender
from app.db.models import NotificationChannelKind
from app.notifications.egress import DeliveryError, EgressPolicy, TargetRejectedError, parse_https_url
from app.notifications.render import Rendered
from app.notifications.settings import NotificationSettings

#: ``NotificationChannelCreate.events`` enum.
SUBSCRIBABLE_EVENTS = (
    "run.succeeded",
    "run.failed",
    "run.stalled",
    "model.ready",
    "dataset.ready",
    "dataset.invalid",
)
_TG_TOKEN = re.compile(r"^\d{3,20}:[A-Za-z0-9_-]{20,128}$")
_TG_CHAT = re.compile(r"^(-?\d{1,20}|@[A-Za-z][A-Za-z0-9_]{4,31})$")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")


def _aad(user_id: uuid.UUID, channel_id: uuid.UUID) -> bytes:
    return f"notification_channel:{user_id}:{channel_id}".encode()


def encrypt_target(cipher: DataCipher, user_id: uuid.UUID, channel_id: uuid.UUID, target: str) -> bytes:
    blob = json.dumps({"v": 1, "target": target}, separators=(",", ":")).encode()
    return cipher.encrypt(blob, _aad(user_id, channel_id))


def decrypt_target(cipher: DataCipher, user_id: uuid.UUID, channel_id: uuid.UUID, blob: bytes) -> str:
    data = json.loads(cipher.decrypt(blob, _aad(user_id, channel_id)))
    return str(data["target"])


def target_hint(kind: NotificationChannelKind | str, target: str) -> str:
    kind = NotificationChannelKind(kind)
    if kind == NotificationChannelKind.EMAIL:
        local, _, domain = target.partition("@")
        return f"{local[:1]}***@{domain}"
    if kind == NotificationChannelKind.TELEGRAM:
        chat = target.rsplit(":", 1)[-1]
        return f"telegram chat …{chat[-4:]}"
    try:
        p = parse_https_url(target)
    except TargetRejectedError:
        return "…"
    if kind == NotificationChannelKind.DISCORD:
        return f"{p.host}/api/webhooks/…/{target.rstrip('/')[-4:]}"
    return f"{p.host}/…{target.rstrip('/')[-4:]}"


def split_telegram(target: str) -> tuple[str, str]:
    token, sep, chat = target.rpartition(":")
    if not sep or not _TG_TOKEN.match(token) or not _TG_CHAT.match(chat):
        raise TargetRejectedError("telegram_target_invalid", "Telegram target must be <bot_token>:<chat_id>")
    return token, chat


async def validate_target(
    kind: NotificationChannelKind,
    raw: str,
    *,
    user_email: str,
    user_verified: bool,
    settings: NotificationSettings,
    policy: EgressPolicy,
) -> str:
    """Normalise and check a target; raises :class:`TargetRejectedError`."""
    target = raw.strip()
    if kind == NotificationChannelKind.EMAIL:
        addr = target.lower()
        if not _EMAIL.match(addr):
            raise TargetRejectedError("email_invalid", "Not an email address")
        if addr != user_email.lower():
            raise TargetRejectedError(
                "email_not_own", "Email channels can only target your own account address"
            )
        if not user_verified:
            raise TargetRejectedError("email_not_verified", "Verify your email address first")
        return addr
    if kind == NotificationChannelKind.TELEGRAM:
        split_telegram(target)
        return target
    parsed = parse_https_url(target)
    if kind == NotificationChannelKind.DISCORD:
        hosts = {h.lower() for h in settings.discord_hosts}
        if parsed.host not in hosts or not parsed.parts.path.startswith("/api/webhooks/"):
            raise TargetRejectedError(
                "discord_url_invalid", "Discord target must be a https://discord.com/api/webhooks/... URL"
            )
    await policy.vet(parsed)
    return parsed.url


def webhook_payload(notification: dict[str, Any], rendered: Rendered) -> dict[str, Any]:
    return {
        "event": notification["kind"],
        "text": rendered.text,
        "title": rendered.title,
        "url": rendered.url,
        "notification": notification,
    }


class ChannelSender:
    def __init__(self, email: EmailSender, settings: NotificationSettings, policy: EgressPolicy) -> None:
        self.email = email
        self.settings = settings
        self.policy = policy

    async def send(
        self,
        kind: NotificationChannelKind,
        target: str,
        rendered: Rendered,
        *,
        notification: dict[str, Any],
        user_email: str,
        user_verified: bool,
    ) -> None:
        """Deliver one message; raises :class:`DeliveryError` (or :class:`TargetRejectedError`)."""
        if kind == NotificationChannelKind.EMAIL:
            await self._email(target, rendered, user_email, user_verified)
        elif kind == NotificationChannelKind.DISCORD:
            await self.policy.post_json(
                target, {"content": rendered.text[:2000], "allowed_mentions": {"parse": []}}
            )
        elif kind == NotificationChannelKind.TELEGRAM:
            token, chat = split_telegram(target)
            base = self.settings.telegram_api_base.rstrip("/")
            await self.policy.post_json(
                f"{base}/bot{token}/sendMessage",
                {"chat_id": chat, "text": rendered.text[:4000], "disable_web_page_preview": True},
            )
        else:
            await self.policy.post_json(
                target,
                webhook_payload(notification, rendered),
                headers={"X-Hibiscus-Event": str(notification.get("kind", ""))},
            )

    async def _email(self, target: str, rendered: Rendered, user_email: str, user_verified: bool) -> None:
        if target.lower() != user_email.lower() or not user_verified:
            raise DeliveryError("account email changed or is not verified", retryable=False)
        if not self.email.enabled:
            raise DeliveryError("email delivery is disabled on this server", retryable=False)
        try:
            await self.email.send(EmailMessage(to=user_email, subject=rendered.subject, text=rendered.text))
        except EmailError as e:
            raise DeliveryError(str(e)[:200], retryable=True) from e
