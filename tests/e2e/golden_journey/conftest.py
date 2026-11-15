"""Shared fixtures for the golden journey (owner: A10 QC).

The journey is ONE user session walked through in file order; the steps share state through the
module-scoped ``journey`` dict. A failing step records why and later steps fall back where a real
user could (e.g. start the run with the CLI when the UI wizard is broken), so a single run reports
every broken stage instead of stopping at the first one.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyotp
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:18150").rstrip("/")
API = BASE + "/api/v1"
OUT = Path(os.environ.get("E2E_OUT", "/tmp/hibiscus-e2e"))
REPO = Path(os.environ.get("E2E_REPO", "/repo"))
ADMIN_EMAIL = os.environ.get("E2E_ADMIN_EMAIL", "qa-admin@example.com")
PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "Golden-Journey-Pass-2026!")

_I18N = {
    lang: json.loads((REPO / "frontend/src/i18n" / lang / "translation.json").read_text(encoding="utf-8"))
    for lang in ("en", "vi")
}


def tr(key: str, lang: str, **params: object) -> str:
    node: Any = _I18N[lang]
    for part in key.split("."):
        node = node[part]
    text = str(node)
    for k, v in params.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def T(key: str, *, exact: bool = True, **params: object) -> re.Pattern[str]:
    """Accessible-name matcher for an i18n key in either UI language.

    The SPA starts in the browser language (en here) and switches to the user's profile locale
    after login (the bootstrap admin is ``vi``), so selectors must not depend on the language.
    """
    alts = "|".join(re.escape(tr(key, lang, **params)) for lang in ("en", "vi"))
    return re.compile(f"^\\s*(?:{alts})\\s*\\*?\\s*$" if exact else f"(?:{alts})")


class Totp:
    """TOTP codes for the admin; never reuses a code (the API rejects replays in the same step)."""

    def __init__(self) -> None:
        self.secret: str | None = None
        self._last: str | None = None

    def code(self) -> str:
        assert self.secret, "TOTP not enrolled yet"
        totp = pyotp.TOTP(self.secret)
        while (c := totp.now()) == self._last:
            time.sleep(1)
        self._last = c
        return c


@pytest.fixture(scope="session")
def out_dir() -> Path:
    (OUT / "screenshots").mkdir(parents=True, exist_ok=True)
    return OUT


@pytest.fixture(scope="session")
def journey() -> dict[str, Any]:
    return {"totp": Totp(), "frictions": []}


@pytest.fixture(scope="session")
def pw() -> Iterator[Playwright]:
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(pw: Playwright) -> Iterator[Browser]:
    b = pw.chromium.launch()
    yield b
    b.close()


@pytest.fixture(scope="session")
def context(browser: Browser, out_dir: Path) -> Iterator[BrowserContext]:
    ctx = browser.new_context(
        locale="en-US", viewport={"width": 1400, "height": 1000}, accept_downloads=True
    )
    ctx.tracing.start(screenshots=True, snapshots=True)
    yield ctx
    ctx.tracing.stop(path=str(out_dir / "trace.zip"))
    ctx.close()


@pytest.fixture(scope="session")
def page(context: BrowserContext, journey: dict[str, Any]) -> Page:
    pg = context.new_page()
    journey["console_errors"] = errs = []
    journey["api_errors"] = api_errs = []
    pg.on("console", lambda m: errs.append(m.text[:300]) if m.type == "error" else None)
    pg.on(
        "response",
        lambda r: api_errs.append(f"{r.status} {r.request.method} {r.url.removeprefix(BASE)}")
        if "/api/" in r.url and r.status >= 400
        else None,
    )
    pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"[:300]))
    return pg


def shot(page: Page, out_dir: Path, name: str) -> None:
    page.screenshot(path=str(out_dir / "screenshots" / f"{name}.png"), full_page=True)


def login(page: Page, totp: Totp, email: str = ADMIN_EMAIL, password: str = PASSWORD) -> None:
    page.goto(BASE + "/login")
    page.get_by_label(T("auth.email")).fill(email)
    page.locator("input[type=password]").fill(password)
    page.get_by_role("button", name=T("auth.login.submit")).click()
    code_box = page.get_by_label(T("auth.mfa.code"))
    if totp.secret:
        code_box.wait_for(timeout=15_000)
        code_box.fill(totp.code())
        page.get_by_role("button", name=T("auth.mfa.verify")).click()
    page.wait_for_url(lambda u: "/login" not in u, timeout=15_000)


def ensure_session(page: Page, journey: dict[str, Any]) -> None:
    """Log in again if the session died in between (recorded as friction, see QC-e2e-07)."""
    if not page.url.startswith(BASE):
        page.goto(BASE + "/")
    res = page.evaluate(
        """async () => { const r = await fetch('/api/v1/auth/me');
                         return {status: r.status, body: (await r.text()).slice(0, 200)}; }"""
    )
    if res["status"] == 401:
        journey["frictions"].append(f"session lost mid-journey, logged in again: {res['body']}")
        login(page, journey["totp"])
