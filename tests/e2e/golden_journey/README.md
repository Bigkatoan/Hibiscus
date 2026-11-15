# Golden journey E2E (owner: A10 QC)

The PLAN §6 golden path, walked like a real user against the **real** stack:

1. `python -m app.admin.bootstrap` → open the one-time link → set the password
2. log in → forced 2FA enrolment (TOTP via pyotp) → recovery codes shown once
3. admin → create workspace "QA Robots" (session must survive reloads)
4. account → access tokens → PAT with the "Máy collect" preset (all 5 scopes); Esc must not
   discard the one-time token before "I copied the token"
5. CLI from `cli/`: `hibiscus login --server <url>` (token pasted at the hidden prompt),
   `hibiscus push Picknplace_20261114_221710.rar --wait` → `ready`
6. dataset page → validation report → episode viewer; the H.264 preview is fetched (206
   `video/mp4`) and **played in Firefox** (Playwright's Chromium has no H.264)
7. "Train with this version" → wizard (production CSP, no `unsafe-eval`) → ACT, `steps=300`,
   GPU cuda0 → review → start
8. if the wizard is broken, the same run is started with `hibiscus train` (recorded as friction)
9. run page: live progress over SSE, one F5 mid-run (session must survive), until `succeeded`;
   no `worker_lost` / `export_failed` event
10. metrics API has a `loss` series; Log tab shows the `lerobot-train` command
11. model page → Download → zip; every file matches MANIFEST.json sha256; train log present
12. `hibiscus pull <model>` → all files verified
13. reload + refresh after the 10 s grace → 204 (QC-e2e-07)
14. `/gpus`: cuda0 = RTX 3060, cuda1 = Tesla P40 (no bf16 / fast fp16)
15. `hibiscus train --gpu cuda1 --set train.mixed_precision=bf16` → succeeds in fp32 on the P40
16. model / run pages in Vietnamese at 1440 and 390 px (CX checks, screenshots)
17. password reset → API `cloudflare` provider → Email Worker under `wrangler dev` (202)
18. (`run.sh`, on the host) both bundles load in the LeLab venv with LeRobot's own
    `from_pretrained` + processors and return an action (`lelab_load_check.py`); the bundle's
    `onnx/infer_onnx.py --selftest` runs with onnxruntime (throwaway uv env, Python 3.12); the
    Email Worker log shows the `send_email` call for the admin

## Run

```bash
tests/e2e/golden_journey/run.sh                          # images hibiscus/*:e2e must exist
E2E_BUILD=1 tests/e2e/golden_journey/run.sh              # build api/web/worker-cpu/worker-gpu first
E2E_TAG=dev E2E_KEEP=1 tests/e2e/golden_journey/run.sh   # reuse :dev images, keep the stack up
E2E_EMAIL_STUB=0 tests/e2e/golden_journey/run.sh        # no local Email Worker (provider none)
```

* Project `hibiscus-e2e`, proxy on `127.0.0.1:$E2E_PORT_BASE` (default 18150; all ports stay in
  18150-18156, never 8000/18000), subnets 172.31.230/231.0/24 (override with `E2E_*_SUBNET`).
* The full documented stack is started with `up -d --wait` and `--profile gpu` (both GPU workers,
  gpu-exporter, observability, backup). The real Email Worker runs under `wrangler dev --local`
  (node:22.12-bookworm) on the stack's `egress` network as `email-worker`.
* Secrets: generated into a `mktemp -d` dir, deleted on exit. Nothing is written to `deploy/`.
* Artifacts in `$E2E_OUT` (default `/tmp/hibiscus-e2e-<timestamp>`): `screenshots/`,
  `trace.zip` (`npx playwright show-trace`), `junit.xml`, `cli-*.txt`, `run-events.json`,
  `journey-summary.json`, `ui-bundle/`, `pulled/`, `lelab_load_check.txt`, `compose.log`.
* Total time ≈ 12 min warm (up --wait 1 min, push 1.5 min, ACT 300 steps + export ≈ 2.5 min, P40 check ≈ 2 min).

No configuration workaround overlay is used any more (deleted after the phase-5 re-verification,
`docs/qa/e2e-2026-11-15-reverify/README.md`); `compose.e2e.yml` only moves ports and the base URL.
