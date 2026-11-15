# Changelog

All notable changes to Hibiscus are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until 1.0.0, minor versions
may contain breaking changes; they are always called out under **Changed** or **Removed**.

## [Unreleased]

## [0.1.0] - 2026-11-16

The first public release: **Hibiscus Trainer**.

### Added

- **Datasets**: resumable chunked upload (≤ 64 MiB parts, sha256 per part) of folders, zip, tar,
  tar.zst and RAR5 archives from the browser or the CLI; import from the Hugging Face Hub; sandboxed
  unpacking; deep LeRobot v3.0 validation; immutable dataset versions; episode preview with video and
  joint plots.
- **Training**: 4-step wizard (dataset → policy → hyper-parameters → review) with forms generated
  from LeRobot 0.7.1 config dataclasses via JSON Schema; quick / standard / fine-tune presets; VRAM and
  duration estimate; pre-flight checks (camera keys vs. policy input features, VRAM, dataset state).
- **Policies**: ACT, Diffusion, VQ-BeT, TD-MPC, SmolVLA, π0 and π0.5 (LoRA/PEFT), trained with the
  unmodified `lerobot-train` subprocess.
- **Scheduler**: Postgres `FOR UPDATE SKIP LOCKED` queue, one worker container per GPU, fair-share
  between workspace members, per-user quotas, pause / resume / cancel / clone, automatic fp32 on
  pre-Ampere GPUs.
- **Live monitoring**: loss, L1, KLD, grad-norm, LR and throughput over SSE with heartbeats; NVML GPU
  telemetry; searchable raw logs; NaN / OOM / hang detection; multi-run comparison.
- **Notifications**: in-app, email (Cloudflare Email Worker), Discord, Telegram and generic webhooks.
- **Model bundles**: `pretrained_model/` (standard LeRobot), ONNX export with parity report (ACT,
  Diffusion), held-out offline evaluation with per-joint plots, generated `run_on_robot.sh`,
  `MODEL_CARD.md`, sha256 `MANIFEST.json`, optional push to the Hugging Face Hub.
- **`hibiscus` CLI**: `login`, `push`, `watch` (auto-upload finished recordings exactly once),
  `datasets`, `train`, `runs`, `logs -f`, `models`, `pull` (sha256-verified).
- **Teams and security**: workspaces, RBAC, invitations, personal access tokens with scopes, Argon2id
  passwords, TOTP 2FA with recovery codes, session management, audit log, rate limiting.
- **Web UI**: original pixel-art "robot garden" design system (Hibi, a robot arm holding a hibiscus;
  animated pixel icons; Nunito text), day and night modes, Vietnamese and English, WCAG 2.1 AA
  contrast checks. Art is © Bigkatoan, see `ASSETS-LICENSE`.
- **Hibiscus Station** (`station/`): local robot-side app for SO-100/SO-101: port detection,
  calibration, cameras, teleoperation, LeRobot dataset recording with keyboard episode controls,
  upload to a Hibiscus server, model import / pull and running a policy on the robot with live
  camera feeds, per-motor temperature / voltage / current / load telemetry, thermal auto-stop and a
  keyboard e-stop. Validated with mock hardware; real-hardware UAT checklist included.
- **Operations**: Docker Compose stack with a loopback-only port policy, Caddy, Prometheus, Grafana,
  Loki, nightly Postgres backups with restore drills, Cloudflare Tunnel and edge rules as code,
  runbooks for install, upgrade, backups, GPUs, secrets and incidents.
- **Open-source packaging**: AGPL-3.0 license, contributing guide, code of conduct, security policy,
  issue and PR templates, CI, CodeQL, gitleaks, Dependabot, GHCR image publishing, and a
  mkdocs-material documentation site.

[Unreleased]: https://github.com/Bigkatoan/Hibiscus/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Bigkatoan/Hibiscus/releases/tag/v0.1.0
