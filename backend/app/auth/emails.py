"""Transactional email bodies (vi / en). Plain text + minimal escaped HTML."""

from __future__ import annotations

import html

from app.core.email import EmailMessage

_T: dict[str, dict[str, str]] = {
    "invite": {
        "vi": 'Bạn được mời vào workspace "{workspace}" trên Hibiscus với vai trò {role}.\n\n'
        "Mở liên kết sau để chấp nhận (hết hạn sau 72 giờ, chỉ dùng một lần):\n{url}\n",
        "en": 'You have been invited to the workspace "{workspace}" on Hibiscus as {role}.\n\n'
        "Open this link to accept (expires in 72 hours, single use):\n{url}\n",
    },
    "invite_subject": {
        "vi": "Lời mời tham gia Hibiscus: {workspace}",
        "en": "Hibiscus invitation: {workspace}",
    },
    "reset": {
        "vi": "Có yêu cầu đặt lại mật khẩu cho tài khoản Hibiscus của bạn.\n\n"
        "Mở liên kết sau trong vòng 30 phút để đặt mật khẩu mới:\n{url}\n\n"
        "Nếu bạn không yêu cầu, hãy bỏ qua email này.\n",
        "en": "A password reset was requested for your Hibiscus account.\n\n"
        "Open this link within 30 minutes to choose a new password:\n{url}\n\n"
        "If you did not request this, ignore this email.\n",
    },
    "reset_subject": {"vi": "Đặt lại mật khẩu Hibiscus", "en": "Reset your Hibiscus password"},
    "verify": {
        "vi": "Xác nhận địa chỉ email của bạn cho Hibiscus (liên kết hết hạn sau 24 giờ):\n{url}\n",
        "en": "Confirm your email address for Hibiscus (link expires in 24 hours):\n{url}\n",
    },
    "verify_subject": {"vi": "Xác nhận email Hibiscus", "en": "Confirm your Hibiscus email"},
}


def _loc(locale: str | None) -> str:
    return locale if locale in ("vi", "en") else "vi"


def _html(text: str, url: str) -> str:
    body = html.escape(text).replace(
        html.escape(url), f'<a href="{html.escape(url, quote=True)}">{html.escape(url)}</a>'
    )
    return (
        '<!doctype html><html><body><pre style="font-family:sans-serif;white-space:pre-wrap">'
        + body
        + "</pre></body></html>"
    )


def _msg(kind: str, to: str, locale: str | None, url: str, **params: str) -> EmailMessage:
    loc = _loc(locale)
    text = _T[kind][loc].format(url=url, **params)
    subject = _T[f"{kind}_subject"][loc].format(**params)
    return EmailMessage(to=to, subject=subject, text=text, html=_html(text, url))


def invite_email(to: str, locale: str | None, workspace: str, role: str, url: str) -> EmailMessage:
    return _msg("invite", to, locale, url, workspace=workspace, role=role)


def reset_email(to: str, locale: str | None, url: str) -> EmailMessage:
    return _msg("reset", to, locale, url)


def verify_email(to: str, locale: str | None, url: str) -> EmailMessage:
    return _msg("verify", to, locale, url)
