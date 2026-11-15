"""Real-browser screenshots of the pixel UI (mock mode), light + dark, at 1440 px and 390 px.

    frontend/scripts/node.sh pnpm build:mock
    # serve dist-mock on 127.0.0.1:18102 (pnpm preview:mock), then:
    docker run --rm --network host -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w \
      hibiscus-playwright:1.49.1 \
      python frontend/scripts/pixel_screenshots.py [--base http://127.0.0.1:18102] [--only name]

hibiscus-playwright:1.49.1 = FROM mcr.microsoft.com/playwright/python:v1.49.1-noble
                             RUN pip install --break-system-packages playwright==1.49.1

Writes docs/ux/screenshots/pixel/<screen>-<theme>-<width>.png and prints axe-core colour-contrast
violations per screen (axe is loaded from frontend/node_modules).
"""

from __future__ import annotations

import re
import argparse
import json
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "ux" / "screenshots" / "pixel"
AXE = ROOT / "frontend" / "node_modules" / "axe-core" / "axe.min.js"

DS = "33333333-3333-4333-8333-333333333333"
RUN = "66666666-6666-4666-8666-666666666666"
RUN_OK = "66666666-6666-4666-8666-777777777777"
RUN_QUEUED = "66666666-6666-4666-8666-000000000001"
RUN_FAILED = "66666666-6666-4666-8666-000000000002"
MODEL = "77777777-7777-4777-8777-777777777777"
W = "/w/robot-lab"


def click_text(page: Page, *names: str) -> None:
    for n in names:
        loc = page.get_by_role("button", name=n)
        if loc.count():
            loc.first.click()
            return
    raise RuntimeError(f"no button {names}")


def wizard(step: int):
    def go(page: Page) -> None:
        page.locator("select").first.select_option(DS)
        page.wait_for_timeout(300)
        if step >= 2:
            click_text(page, "Next", "Tiếp")
            page.wait_for_timeout(500)
        if step >= 3:
            page.get_by_role("radio", name="ACT").first.click()
            click_text(page, "Next", "Tiếp")
            page.wait_for_timeout(800)
        if step >= 4:
            page.get_by_role("button", name=re.compile(r"^(Review|Xem lại)$")).first.click()
            page.wait_for_timeout(800)

    return go


def episodes(page: Page) -> None:
    page.get_by_role("tab").nth(2).click()
    page.wait_for_timeout(800)


def token_dialog(page: Page) -> None:
    page.get_by_role("button", name=re.compile(r"^(Create token|Tạo token)$")).first.click()
    page.wait_for_timeout(400)


def open_menu(page: Page) -> None:
    page.get_by_role("button", name="Open menu").or_(page.get_by_role("button", name="Mở menu")).first.click()
    page.wait_for_timeout(200)


# name, url, optional action
SCREENS = [
    ("login", "/login?mock_auth=0", None),
    ("datasets", f"{W}/datasets", None),
    ("datasets-empty", f"{W}/datasets?mock_empty=1", None),
    ("dataset-detail", f"{W}/datasets/{DS}", None),
    ("dataset-episodes", f"{W}/datasets/{DS}", episodes),
    ("upload", f"{W}/datasets/upload", None),
    ("wizard-1-dataset", f"{W}/runs/new", wizard(1)),
    ("wizard-2-policy", f"{W}/runs/new", wizard(2)),
    ("wizard-3-config", f"{W}/runs/new", wizard(3)),
    ("wizard-4-review", f"{W}/runs/new", wizard(4)),
    ("runs", f"{W}/runs", None),
    ("run-running", f"{W}/runs/{RUN}", None),
    ("run-queued", f"{W}/runs/{RUN_QUEUED}", None),
    ("run-succeeded", f"{W}/runs/{RUN_OK}", None),
    ("run-failed", f"{W}/runs/{RUN_FAILED}", None),
    ("run-succeeded-logs", f"{W}/runs/{RUN_OK}?tab=logs", None),
    ("models", f"{W}/models", None),
    ("model-detail", f"{W}/models/{MODEL}", None),
    ("gpus", f"{W}/gpus", None),
    ("account-security", "/account/security", None),
    ("token-dialog", "/account/tokens", token_dialog),
    ("settings", f"{W}/settings", None),
    ("admin-users", "/admin/users", None),
    ("admin-system", "/admin/system", None),
    ("not-found", f"{W}/does-not-exist", None),
]
MOBILE_ONLY = [("mobile-menu", f"{W}/datasets", open_menu)]


SPECIMEN = """
<div style="padding:24px;background:#f3dfb2;color:#3b2027;font-family:Nunito">
<p style="font-size:24px;font-weight:800;line-height:32px">Tập dữ liệu · Huấn luyện · Mô hình</p>
<p style="font-size:20px;font-weight:800">Tiếng Việt: ặ ữ ẫ ỡ ự ổ ề ứ ở Đ đ Ư ư Ơ ơ</p>
<p style="font-size:16px;font-weight:700">Lượt train đã hoàn thành — Đang chờ GPU — Thất bại</p>
<p style="font-size:16px;font-variant-numeric:tabular-nums">Bước 2.500/10.000 · tốc độ 9,1 bước/giây · 0123456789</p>
<p style="font-size:16px">Hibi đang chăm vườn — cánh tay robot học cách gắp đặt khối gỗ. ặ ữ ẫ ỡ ự ổ ề</p>
<p style="font-size:14px;font-family:ui-monospace,monospace">logs: step=2500 loss=0.0421 lr=1e-4</p>
</div>"""


def specimen(browser, base: str) -> None:
    """Vietnamese diacritics in the self-hosted Nunito (rendered inside the built app)."""
    page = browser.new_page(viewport={"width": 900, "height": 330}, device_scale_factor=1)
    page.goto(base + "/login?mock_auth=0", wait_until="networkidle")
    page.evaluate("html => { document.body.innerHTML = html; }", SPECIMEN)
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "fonts-vietnamese-specimen.png"))
    page.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:18102")
    ap.add_argument("--only", default="")
    ap.add_argument("--widths", default="1440,390")
    ap.add_argument("--themes", default="light,dark")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    axe_src = AXE.read_text() if AXE.exists() else None
    report: dict[str, list[str]] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        if not args.only or "specimen" in args.only:
            specimen(browser, args.base)
        for theme in args.themes.split(","):
            for width in [int(w) for w in args.widths.split(",")]:
                screens = SCREENS + (MOBILE_ONLY if width < 768 else [])
                for name, url, action in screens:
                    if args.only and args.only not in name:
                        continue
                    ctx = browser.new_context(
                        viewport={"width": width, "height": 900},
                        device_scale_factor=1,
                        color_scheme=theme,
                        locale="vi-VN",
                        reduced_motion="reduce",
                    )
                    page = ctx.new_page()
                    page.goto(args.base + url, wait_until="networkidle")
                    page.wait_for_timeout(600)
                    if action:
                        action(page)
                    page.evaluate("document.fonts.ready")
                    page.wait_for_timeout(200)
                    shot = OUT / f"{name}-{theme}-{width}.png"
                    page.screenshot(path=str(shot), full_page=True)
                    # horizontal overflow check (360/390 px requirement)
                    overflow = page.evaluate(
                        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
                    )
                    issues: list[str] = []
                    if overflow > 0:
                        issues.append(f"horizontal overflow {overflow}px")
                    if axe_src:
                        page.add_script_tag(content=axe_src)
                        res = page.evaluate(
                            """async () => {
                              const r = await axe.run(document, {runOnly: ['wcag2a','wcag2aa']});
                              return r.violations.map(v => v.id + ' x' + v.nodes.length + ': ' +
                                v.nodes.slice(0,3).map(n => n.target.join(' ') + ' ' +
                                  (n.any[0] && n.any[0].data ? JSON.stringify({fg:n.any[0].data.fgColor,bg:n.any[0].data.bgColor,r:n.any[0].data.contrastRatio}) : '')).join(' | '));
                            }"""
                        )
                        issues += res
                    report[shot.name] = issues
                    print(shot.name, "OK" if not issues else issues, flush=True)
                    ctx.close()
        browser.close()
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
