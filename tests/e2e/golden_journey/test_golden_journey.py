"""Golden journey (PLAN §6) as a real user, through the built SPA and the real API. Owner: A10.

Run with ``tests/e2e/golden_journey/run.sh`` (brings the stack up, bootstraps the first admin,
runs this file inside hibiscus-playwright:1.49.1, checks the bundle in the LeLab venv, tears
down). The steps run in file order and share one browser session.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any

import pytest
from conftest import ADMIN_EMAIL, BASE, PASSWORD, T, Totp, ensure_session, login, shot
from playwright.sync_api import Page, expect

WS_NAME = "QA Robots"
WS_SLUG = "qa-robots"
ARCHIVE = Path(os.environ.get("E2E_ARCHIVE", "/golden/Picknplace_20261114_221710.rar"))
# `hibiscus push` names the dataset after the directory, or the archive name up to the first dot
DATASET = os.environ.get("E2E_DATASET_NAME") or ARCHIVE.name.split(".")[0]
STEPS = int(os.environ.get("E2E_TRAIN_STEPS", "300"))
LOG_FREQ = int(os.environ.get("E2E_LOG_FREQ", "0"))  # 0 = keep what the wizard derives (QC-e2e-11)
RUN_TIMEOUT_S = int(os.environ.get("E2E_RUN_TIMEOUT_S", "1500"))
HIBISCUS = os.environ.get("E2E_HIBISCUS_BIN", "hibiscus")
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
TERMINAL = {"succeeded", "failed", "cancelled"}


def cli(*args: str, out_dir: Path, name: str, timeout: int = 900, stdin: str | None = None, ok: bool = True) -> str:
    env = {
        **os.environ,
        "HOME": "/tmp/clihome",
        "HIBISCUS_KEYRING": "0",
        "HIBISCUS_SERVER": BASE,
        "COLUMNS": "200",
        "NO_COLOR": "1",
    }
    p = subprocess.run(
        [HIBISCUS, *args], capture_output=True, text=True, env=env, timeout=timeout, check=False,
        input=stdin,
    )
    text = f"$ hibiscus {' '.join(args)}\n[exit {p.returncode}]\n{p.stdout}\n{p.stderr}"
    text = re.sub(r"hbp_[A-Za-z0-9_-]+", "hbp_<redacted>", text)
    (out_dir / f"cli-{name}.txt").write_text(text, encoding="utf-8")
    if ok:
        assert p.returncode == 0, text[-3000:]
    return p.stdout + p.stderr


def api_get(page: Page, path: str) -> Any:
    """GET through the page (same cookies/CSRF as the SPA; Secure cookies on plain http)."""
    res = page.evaluate(
        """async (p) => { const r = await fetch('/api/v1' + p, {credentials: 'same-origin'});
                         return {status: r.status, body: await r.text()}; }""",
        path,
    )
    assert res["status"] == 200, f"GET {path} -> {res['status']} {res['body'][:300]}"
    return json.loads(res["body"])


def still_logged_in(page: Page) -> None:
    """Reload twice: QC-e2e-02 (per-process JWT keys) shows up as a bounce to /login."""
    for _ in range(2):
        page.reload()
        page.wait_for_timeout(1500)
        assert "/login" not in page.url, f"session lost after reload: {page.url}"


# --------------------------------------------------------------------------------------------
def test_01_bootstrap_link_sets_password(page: Page, out_dir: Path) -> None:
    link = os.environ["E2E_BOOTSTRAP_LINK"]
    page.goto(link)
    page.get_by_label(T("auth.new_password")).fill(PASSWORD)
    page.get_by_label(T("auth.confirm_password")).fill(PASSWORD)
    shot(page, out_dir, "01-reset-password")
    page.get_by_role("button", name=T("auth.reset.submit")).click()
    expect(page.get_by_text(T("auth.reset.done", exact=False))).to_be_visible(timeout=15_000)


def test_02_login_and_enrol_totp(page: Page, out_dir: Path, journey: dict[str, Any]) -> None:
    totp: Totp = journey["totp"]
    login(page, totp)
    page.wait_for_url(re.compile(r"/account/security"), timeout=15_000)
    shot(page, out_dir, "02-enrolment-required")
    page.get_by_label(T("security.confirm_password")).fill(PASSWORD)
    page.get_by_role("button", name=T("security.setup_2fa")).click()
    secret = page.locator("code").first
    expect(secret).to_be_visible(timeout=15_000)
    totp.secret = re.sub(r"\s", "", secret.inner_text())
    shot(page, out_dir, "03-totp-qr")
    page.get_by_label(T("auth.mfa.code")).fill(totp.code())
    page.get_by_role("button", name=T("security.enable_2fa")).click()
    expect(page.get_by_text(T("security.enabled"))).to_be_visible(timeout=15_000)
    page.wait_for_timeout(1500)
    shot(page, out_dir, "04-after-enable-2fa")
    # Spec: recovery codes are shown exactly once right after enabling (QC-e2e-06).
    codes = page.get_by_label(T("security.recovery_codes"))
    expect(codes, "recovery codes never shown after enabling 2FA").to_be_visible(timeout=5_000)
    journey["recovery_codes_shown"] = codes.locator("li").count()
    assert journey["recovery_codes_shown"] >= 8, journey["recovery_codes_shown"]
    done = page.get_by_test_id("recovery-codes").get_by_role("button", name=T("security.recovery_codes_done"))
    expect(done).to_be_disabled()
    page.get_by_text(T("security.recovery_codes_saved")).click()
    expect(done).to_be_enabled()
    shot(page, out_dir, "04b-recovery-codes-saved")
    done.click()


def test_03_create_workspace(page: Page, out_dir: Path, journey: dict[str, Any]) -> None:
    if "/login" in page.url or page.url.endswith("/"):
        login(page, journey["totp"])
    page.goto(BASE + "/admin")
    page.get_by_role("button", name=T("admin.create_workspace")).click()
    dlg = page.get_by_role("dialog")
    dlg.get_by_label(T("workspace.name")).fill(WS_NAME)
    shot(page, out_dir, "05-create-workspace")
    dlg.get_by_role("button", name=T("admin.create_workspace")).click()
    page.wait_for_url(re.compile(rf"/w/{WS_SLUG}/settings"), timeout=15_000)
    page.wait_for_timeout(2000)
    shot(page, out_dir, "06-workspace-settings")
    assert "/login" not in page.url
    still_logged_in(page)


def test_04_create_pat(page: Page, out_dir: Path, journey: dict[str, Any]) -> None:
    if "/login" in page.url:
        login(page, journey["totp"])
    page.goto(BASE + "/account/tokens")
    page.get_by_role("button", name=T("tokens.create")).first.click()
    dlg = page.get_by_role("dialog")
    dlg.get_by_label(T("tokens.name")).fill("collect-pc")
    dlg.get_by_label(T("tokens.workspace")).select_option(label=WS_NAME)
    # CX-03: the "Máy collect" preset must cover every CLI command (push, train, logs, pull).
    dlg.get_by_text(T("tokens.presets.collect")).click()
    expect(dlg.locator("input[name=token-preset][value=collect]")).to_be_checked()
    checked = []
    for scope in ("datasets:read", "datasets:write", "runs:read", "runs:write", "models:read"):
        box = dlg.locator("label", has=page.locator("code", has_text=scope)).locator("input[type=checkbox]")
        if box.is_checked():
            checked.append(scope)
    journey["collect_preset_scopes"] = checked
    shot(page, out_dir, "07-create-pat")
    assert len(checked) == 5, f"'Máy collect' preset scopes: {checked}"
    dlg.get_by_role("button", name=T("tokens.create")).click()
    token = dlg.get_by_test_id("new-token")
    expect(token).to_be_visible(timeout=15_000)
    journey["pat"] = token.inner_text().strip()
    assert journey["pat"].startswith("hbp_")
    login_cmd = dlg.get_by_test_id("login-cmd").inner_text()
    journey["pat_login_hint"] = login_cmd
    assert "--token" not in login_cmd and "--server" in login_cmd, login_cmd
    shot(page, out_dir, "07b-pat-created")
    page.keyboard.press("Escape")  # must NOT discard the one-time token before the copied ack
    page.wait_for_timeout(500)
    expect(token, "Esc closed the dialog before 'I copied the token'").to_be_visible()
    done = dlg.get_by_role("button", name=T("tokens.done"))
    expect(done).to_be_disabled()
    dlg.get_by_text(T("tokens.copied_ack")).click()
    done.click()
    expect(page.get_by_role("dialog")).to_have_count(0)


def test_05_cli_push_golden_archive(out_dir: Path, journey: dict[str, Any]) -> None:
    pat = journey.get("pat")
    assert pat, "no PAT from the UI step"
    # as the dialog hint says: `hibiscus login --server <url>`, token pasted at the hidden prompt
    cli("login", "--server", BASE, out_dir=out_dir, name="login", stdin=pat + "\n")
    who = cli("whoami", out_dir=out_dir, name="whoami")
    assert WS_NAME in who
    t0 = time.monotonic()
    out = cli("push", str(ARCHIVE), "--wait", out_dir=out_dir, name="push", timeout=1800)
    journey["push_seconds"] = round(time.monotonic() - t0, 1)
    assert "Validation result: ready" in out, out[-2000:]
    show = cli("datasets", "show", DATASET, out_dir=out_dir, name="dataset-show")
    assert "validation: passed" in show
    m = UUID_RE.search(out.split("version ", 1)[1]) if "version " in out else None
    assert m, out
    journey["version_id"] = m.group(0)


def _open_dataset(page: Page, journey: dict[str, Any] | None = None) -> None:
    page.goto(f"{BASE}/w/{WS_SLUG}/datasets")
    page.wait_for_timeout(1500)
    if journey is not None and "/login" in page.url:  # QC-e2e-07 can revoke the session any time
        journey["frictions"].append(f"bounced to {page.url.removeprefix(BASE)}, logged in again")
        login(page, journey["totp"])
        page.goto(f"{BASE}/w/{WS_SLUG}/datasets")
    page.get_by_role("link", name=DATASET).first.click()
    expect(page.get_by_role("tab", name=T("datasets.tab.episodes"))).to_be_enabled(timeout=20_000)


def test_06_dataset_preview_plays(page: Page, out_dir: Path, journey: dict[str, Any], pw: Any) -> None:
    ensure_session(page, journey)
    _open_dataset(page, journey)
    shot(page, out_dir, "08-dataset-overview")
    page.get_by_role("tab", name=T("datasets.tab.validation")).click()
    page.wait_for_timeout(800)
    shot(page, out_dir, "09-dataset-validation")
    # The episode viewer is exercised in Firefox: Playwright's Chromium has no H.264, and its
    # <video> onError would call /auth/refresh (EpisodeViewer.tsx) - not what a Chrome user sees.
    ff = pw.firefox.launch()
    try:
        fpage = ff.new_context(locale="en-US", viewport={"width": 1400, "height": 1000}).new_page()
        login(fpage, journey["totp"])
        _open_dataset(fpage)
        fpage.get_by_role("tab", name=T("datasets.tab.episodes")).click()
        video = fpage.locator("video").first
        video.wait_for(timeout=20_000)
        probe = fpage.evaluate(
            """async (u) => { const r = await fetch(u, {headers: {Range: 'bytes=0-1023'}});
                             return {status: r.status, type: r.headers.get('content-type')}; }""",
            video.get_attribute("src") or "",
        )
        assert probe["status"] in (200, 206) and "video/mp4" in (probe["type"] or ""), probe
        state = fpage.evaluate(
            """async () => { const v = document.querySelector('video'); v.muted = true;
                 await v.play(); await new Promise(r => setTimeout(r, 2500));
                 return {t: v.currentTime, w: v.videoWidth, h: v.videoHeight, err: v.error && v.error.code,
                         h264: v.canPlayType('video/mp4; codecs="avc1.42E01E"')}; }"""
        )
        fpage.screenshot(path=str(out_dir / "screenshots" / "10-preview-playing-firefox.png"), full_page=True)
        journey["preview"] = state
        assert state["err"] is None and state["t"] > 0.5 and state["w"] > 0, state
    finally:
        ff.close()


def test_07_start_act_run_from_wizard(page: Page, out_dir: Path, journey: dict[str, Any]) -> None:
    ensure_session(page, journey)
    csp = page.request.get(BASE + "/").headers.get("content-security-policy", "")
    journey["spa_csp"] = csp
    assert "script-src" in csp and "unsafe-eval" not in csp, f"not the production CSP: {csp!r}"
    errors_before = len(journey["console_errors"])
    _open_dataset(page, journey)
    page.get_by_role("link", name=T("datasets.train")).or_(
        page.get_by_role("button", name=T("datasets.train"))
    ).first.click()
    page.wait_for_url(re.compile(r"/runs/new"), timeout=15_000)
    page.wait_for_timeout(2500)
    shot(page, out_dir, "12-wizard-policy")
    crash = [e for e in journey["console_errors"][errors_before:] if "unsafe-eval" in e or "EvalError" in e]
    assert not crash, f"wizard crashed (CSP blocks Ajv's code generation, QC-e2e-04): {crash[0]}"
    page.locator("input[name=policy][value=act]").check()
    page.get_by_role("button", name=T("common.next")).click()
    steps = page.locator("[data-field=steps] input").first
    expect(steps).to_be_visible(timeout=20_000)
    steps.fill(str(STEPS))
    page.get_by_role("tab", name=T("wizard.advanced")).click()
    log_freq = page.locator("[data-field=log_freq] input").first
    if log_freq.count():
        if LOG_FREQ:
            log_freq.fill(str(LOG_FREQ))
        journey["wizard_log_freq"] = log_freq.input_value()
    page.get_by_role("tab", name=T("wizard.basic")).click()
    gpu = page.locator("select", has=page.locator("option[value=cuda0]")).first
    gpu.select_option("cuda0")  # the RTX 3060; worker-cuda1 (P40) is up as well
    shot(page, out_dir, "13-wizard-params")
    page.get_by_role("button", name=T("wizard.review")).click()
    start = page.get_by_role("button", name=T("wizard.start"))
    expect(start).to_be_enabled(timeout=120_000)
    shot(page, out_dir, "14-wizard-review")
    start.click()
    page.wait_for_url(re.compile(r"/runs/[0-9a-f-]{36}"), timeout=30_000)
    journey["run_id"] = UUID_RE.search(page.url).group(0)  # type: ignore[union-attr]
    journey["run_started_by"] = "ui"
    crash = [e for e in journey["console_errors"][errors_before:] if "unsafe-eval" in e or "EvalError" in e]
    assert not crash, crash


def test_08_run_exists_or_cli_fallback(out_dir: Path, journey: dict[str, Any]) -> None:
    """If the wizard failed, start the same run with the CLI (what a user would do next)."""
    if journey.get("run_id"):
        return
    journey["frictions"].append("run started with `hibiscus train` because the UI wizard failed")
    out = cli(
        "train", "-d", DATASET, "-p", "act", "--set", f"train.steps={STEPS}",
        "--set", f"train.log_freq={LOG_FREQ or 20}", "--gpu", "cuda0", "--name", "golden-act",
        out_dir=out_dir, name="train",
    )
    m = re.search(r"\(id ([0-9a-f-]{36})", out)
    assert m, out
    journey["run_id"] = m.group(1)
    journey["run_started_by"] = "cli"


def test_09_watch_run_live_until_success(page: Page, out_dir: Path, journey: dict[str, Any]) -> None:
    run_id = journey.get("run_id")
    assert run_id, "no run"
    ensure_session(page, journey)
    sse: list[str] = []
    page.on("request", lambda r: sse.append(r.url) if f"/runs/{run_id}/events" in r.url else None)
    page.goto(f"{BASE}/w/{WS_SLUG}/runs/{run_id}")
    seen_steps: list[str] = []
    status = ""
    t0 = time.monotonic()
    i = 0
    reloaded_at: float | None = None
    while time.monotonic() - t0 < RUN_TIMEOUT_S:
        run = api_get(page, f"/runs/{run_id}")
        status = run["status"]
        step_now = (run.get("progress") or {}).get("current_step") or 0
        if reloaded_at is None and status == "running" and step_now >= STEPS // 3:
            # QC-e2e-07: an F5 in the middle of a live run (SSE open) must not cost the session.
            shot(page, out_dir, "15a-run-before-reload")
            journey["live_metrics_before_reload"] = {
                s["key"]: len(s["steps"]) for s in api_get(page, f"/runs/{run_id}/metrics")["series"]
            }
            page.reload()
            reloaded_at = time.monotonic()
            page.wait_for_timeout(3000)
            assert "/login" not in page.url, f"session lost on mid-run reload: {page.url}"
            shot(page, out_dir, "15b-run-after-reload")
            journey["reload_at_step"] = step_now
        m = re.search(r"(\d+)\s*/\s*" + str(STEPS), page.locator("main").inner_text())
        if m and (not seen_steps or seen_steps[-1] != m.group(1)):
            seen_steps.append(m.group(1))
        if i % 6 == 0:
            shot(page, out_dir, f"15-run-live-{i:03d}")
        if status in TERMINAL:
            break
        i += 1
        page.wait_for_timeout(5000)  # no reload: the page must update itself over SSE
    page.wait_for_timeout(3000)
    shot(page, out_dir, "16-run-final")
    journey["run_status"] = status
    journey["run_final"] = {k: run.get(k) for k in ("gpu_id", "mixed_precision_requested",
                                                     "mixed_precision_effective", "attempt", "error_code",
                                                     "infra_retries_used", "gpu_seconds")}
    journey["mid_run_reload_done"] = reloaded_at is not None
    me = page.evaluate("async () => (await fetch('/api/v1/auth/me')).status")
    assert me == 200 and "/login" not in page.url, f"session gone after the run (reload at {reloaded_at}): {me}"
    journey["ui_progress_seen"] = seen_steps
    history = api_get(page, f"/runs/{run_id}/events/history?limit=500")["items"]
    (out_dir / "run-events.json").write_text(json.dumps(history, indent=1), encoding="utf-8")
    assert any("/events" in u and "history" not in u for u in sse), "run page opened no SSE stream"
    assert status == "succeeded", f"run ended {status}"
    assert len(set(seen_steps)) >= 2, f"progress never moved live in the UI: {seen_steps}"
    lost = [e for e in history if e.get("data", {}).get("code") in ("worker_lost", "export_failed")]
    assert not lost, f"healthy worker declared lost during the run (QC-e2e-05): {lost[0]}"
    assert reloaded_at is not None, "run finished before the mid-run reload could happen"


def test_10_metrics_and_logs_visible(page: Page, out_dir: Path, journey: dict[str, Any]) -> None:
    run_id = journey["run_id"]
    series = {s["key"]: s for s in api_get(page, f"/runs/{run_id}/metrics")["series"]}
    assert "loss" in series, list(series)
    journey["loss_points"] = len(series["loss"]["steps"])
    journey["metric_series"] = {k: len(v["steps"]) for k, v in series.items()}
    page.get_by_role("tab", name=T("run.tab.metrics")).click()
    page.wait_for_timeout(2000)
    shot(page, out_dir, "16b-run-metrics-tab")
    journey["metrics_honesty_visible"] = page.get_by_text(T("run.metrics_honesty.title", exact=False)).count() > 0
    page.get_by_role("tab", name=T("run.tab.logs")).click()
    page.wait_for_timeout(2000)
    shot(page, out_dir, "17-run-logs-tab")
    # A finished run's Log tab starts empty ("no log lines yet"); the stored log needs a click.
    if page.get_by_text(T("logs.empty")).count():
        journey["frictions"].append("Log tab of a finished run shows 'no log lines yet' until 'Load log'")
        page.get_by_role("button", name=T("logs.load_full")).click()
        page.wait_for_timeout(2000)
    shot(page, out_dir, "17-run-logs")
    expect(page.get_by_text("lerobot-train", exact=False).first).to_be_visible(timeout=15_000)


def test_11_download_bundle_in_ui(page: Page, out_dir: Path, journey: dict[str, Any]) -> None:
    ensure_session(page, journey)
    run = api_get(page, f"/runs/{journey['run_id']}")
    assert run.get("model_id"), "run has no model"
    journey["model_id"] = run["model_id"]
    page.goto(f"{BASE}/w/{WS_SLUG}/models/{run['model_id']}")
    expect(page.get_by_role("link", name=T("model.download"))).to_be_visible(timeout=20_000)
    shot(page, out_dir, "18-model-detail")
    with page.expect_download(timeout=600_000) as dl:
        page.get_by_role("link", name=T("model.download")).first.click()
    zpath = out_dir / dl.value.suggested_filename
    dl.value.save_as(zpath)
    dest = out_dir / "ui-bundle"
    with zipfile.ZipFile(zpath) as z:
        z.extractall(dest)
    (bundle,) = [p for p in dest.iterdir() if p.is_dir()]
    manifest = json.loads((bundle / "MANIFEST.json").read_text(encoding="utf-8"))
    bad = [
        f["path"]
        for f in manifest["files"]
        if hashlib.sha256((bundle / f["path"]).read_bytes()).hexdigest() != f["sha256"]
    ]
    assert not bad, f"sha256 mismatch: {bad}"
    assert (bundle / "pretrained_model" / "model.safetensors").is_file()
    assert (bundle / "onnx" / "model.onnx").is_file()
    train_log = (bundle / "logs" / "train.log").read_text(encoding="utf-8", errors="replace")
    journey["bundle_train_log_bytes"] = len(train_log)
    assert "lerobot-train" in train_log or "step" in train_log, (
        f"bundle logs/train.log has no training output ({len(train_log)} bytes): {train_log[:200]!r}"
    )


def test_12_hibiscus_pull(out_dir: Path, journey: dict[str, Any]) -> None:
    model_id = journey.get("model_id")
    assert model_id
    out = cli("pull", model_id, "--to", str(out_dir / "pulled"), out_dir=out_dir, name="pull")
    assert "files verified" in out, out


def test_13_session_survives_reload_then_refresh(page: Page, out_dir: Path, journey: dict[str, Any]) -> None:
    """QC-e2e-07: reloading a page with an open SSE stream fires /auth/refresh (EventSource
    onerror), the navigation aborts it after the server rotated the token, and the browser keeps
    the old refresh cookie; the next refresh after the 10 s grace is "reuse" and revokes the
    whole session. A real user hits this at the first access-token expiry (15 min)."""
    ensure_session(page, journey)
    page.goto(f"{BASE}/w/{WS_SLUG}/datasets")  # workspace SSE stream opens on every page
    page.wait_for_timeout(3000)
    page.reload()
    page.wait_for_timeout(12_000)  # > refresh_reuse_grace_s (10 s)
    res = page.evaluate(
        """async () => { const csrf = (document.cookie.match(/hb_csrf=([^;]+)/) || [])[1] || '';
             const r = await fetch('/api/v1/auth/refresh', {method: 'POST', headers: {'X-CSRF-Token': csrf}});
             return {status: r.status, body: (await r.text()).slice(0, 300)}; }"""
    )
    journey["refresh_after_reload"] = res
    assert res["status"] == 204, f"session revoked by a normal reload + refresh: {res}"


def test_14_both_gpus_registered(page: Page, out_dir: Path, journey: dict[str, Any]) -> None:
    """QC-e2e-09: worker-cuda1 must register as cuda1 (the P40), without bf16 / fast fp16."""
    ensure_session(page, journey)
    gpus = {g["id"]: g for g in api_get(page, "/gpus")["items"]}
    journey["gpus"] = {k: {f: g.get(f) for f in ("name", "compute_capability", "supports_bf16",
                                                 "supports_fast_fp16", "status", "total_vram_mb")}
                       for k, g in gpus.items()}
    assert set(gpus) >= {"cuda0", "cuda1"}, list(gpus)
    assert "3060" in gpus["cuda0"]["name"] and "P40" in gpus["cuda1"]["name"], journey["gpus"]
    assert gpus["cuda1"]["supports_bf16"] is False and gpus["cuda1"]["supports_fast_fp16"] is False
    assert gpus["cuda0"]["status"] != "offline" and gpus["cuda1"]["status"] != "offline"
    page.goto(f"{BASE}/w/{WS_SLUG}/gpus")
    page.wait_for_timeout(2500)
    shot(page, out_dir, "19-gpus")


def test_15_short_run_on_p40_is_fp32(page: Page, out_dir: Path, journey: dict[str, Any]) -> None:
    """A bf16 request routed to cuda1 must train on the P40 in fp32 (ADR-0002, D10)."""
    out = cli(
        "train", "-d", DATASET, "-p", "act", "--set", "train.steps=40", "--set", "train.log_freq=10",
        "--set", "train.mixed_precision=bf16", "--gpu", "cuda1", "--name", "p40-fp32-check",
        out_dir=out_dir, name="train-cuda1",
    )
    m = re.search(r"\(id ([0-9a-f-]{36})", out)
    assert m, out
    rid = m.group(1)
    journey["p40_run_id"] = rid
    t0 = time.monotonic()
    run: dict[str, Any] = {}
    while time.monotonic() - t0 < RUN_TIMEOUT_S:
        run = api_get(page, f"/runs/{rid}")
        if run["status"] in TERMINAL:
            break
        time.sleep(5)
    journey["p40_run"] = {k: run.get(k) for k in ("status", "gpu_id", "mixed_precision_requested",
                                                   "mixed_precision_effective", "error_code", "attempt")}
    page.goto(f"{BASE}/w/{WS_SLUG}/runs/{rid}")
    page.wait_for_timeout(2500)
    shot(page, out_dir, "20-p40-run")
    hist = api_get(page, f"/runs/{rid}/events/history?limit=500")["items"]
    (out_dir / "run-events-p40.json").write_text(json.dumps(hist, indent=1), encoding="utf-8")
    assert run.get("gpu_id") == "cuda1", journey["p40_run"]
    assert run.get("mixed_precision_effective") in ("no", "fp32"), journey["p40_run"]
    assert run["status"] == "succeeded", journey["p40_run"]


def test_16_model_page_cx(page: Page, out_dir: Path, journey: dict[str, Any]) -> None:
    """CX-01/02/08/09/11 on the finished golden run and its model (vi UI, 1440 and 390 px)."""
    ensure_session(page, journey)
    run_id, model_id = journey["run_id"], journey.get("model_id")
    page.goto(f"{BASE}/w/{WS_SLUG}/models/{model_id}")
    page.wait_for_timeout(2500)
    shot(page, out_dir, "21-model-detail-vi")
    main = page.locator("main").inner_text()
    journey["cx_model_page"] = {
        "no_inference_warning": "LeLab" in main and "run_on_robot.sh" in main,
        "pull_cmd": re.findall(r"hibiscus pull \S+ --to \S+", main),
        "mae_disclaimer": page.get_by_text(T("eval.offline_not_success_rate", exact=False)).count() > 0,
    }
    page.goto(f"{BASE}/w/{WS_SLUG}/runs/{run_id}")
    page.wait_for_timeout(2500)
    shot(page, out_dir, "22-run-succeeded-vi")
    journey["cx_run_page_text"] = page.locator("main").inner_text()[:3000]
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(1000)
    shot(page, out_dir, "23-run-succeeded-390")
    page.goto(f"{BASE}/w/{WS_SLUG}/runs/new")
    page.wait_for_timeout(2500)
    shot(page, out_dir, "24-wizard-390")
    page.goto(f"{BASE}/w/{WS_SLUG}/models/{model_id}")
    page.wait_for_timeout(2500)
    shot(page, out_dir, "25-model-detail-390")
    page.set_viewport_size({"width": 1400, "height": 1000})


def test_17_password_reset_mail_goes_through_email_worker(page: Page, out_dir: Path, journey: dict[str, Any]) -> None:
    """SEC-infra-1 / QC-e2e-10: the API's cloudflare provider -> Email Worker (wrangler dev)."""
    if os.environ.get("E2E_EMAIL_STUB", "0") != "1":
        pytest.skip("no local Email Worker")
    res = page.evaluate(
        """async (email) => { const r = await fetch('/api/v1/auth/password/forgot', {method: 'POST',
             headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email})});
             return r.status; }""",
        ADMIN_EMAIL,
    )
    journey["forgot_password_status"] = res
    assert res == 202, res
    ensure_session(page, journey)
    page.goto(f"{BASE}/admin/system")
    page.wait_for_timeout(2500)
    shot(page, out_dir, "26-admin-system")


@pytest.fixture(scope="session", autouse=True)
def _write_summary(out_dir: Path, journey: dict[str, Any]) -> Any:
    yield
    summary = {k: v for k, v in journey.items() if k not in ("totp", "pat")}
    summary["admin"] = ADMIN_EMAIL
    (out_dir / "journey-summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    if os.environ.get("E2E_KEEP") == "1":
        # The stack stays up: hand the admin's credentials over so it can still be logged into
        # (the TOTP secret exists nowhere else). Owner-only file in the throwaway artifacts dir.
        keep = out_dir / "keep-session.json"
        keep.touch(mode=0o600)
        totp: Totp = journey["totp"]
        keep.write_text(json.dumps({"email": ADMIN_EMAIL, "password": PASSWORD, "totp_secret": totp.secret,
                                    "pat": journey.get("pat"), "workspace": WS_SLUG}), encoding="utf-8")
