# ADR-0003: Train with an unmodified `lerobot-train` subprocess, version pinned in the worker image

- **Status:** Accepted (2026-11-15)
- **Deciders:** A1 (Solution Architect)
- **Source:** PLAN.md §2, ADR-3

## Context

The output of Hibiscus must be a model that is byte-for-byte what LeRobot itself produces, so it loads
with `--policy.path` in `lerobot-record`, `lerobot-rollout`, `lerobot-eval` and future LeLab versions
(ADR-0011). Re-implementing the training loop would drift from upstream on every release. Observed
facts about LeRobot 0.7.1 that shape the integration:

- `lerobot-train` has **no wandb** flags; it logs to **trackio**.
- Mixed precision is `--accelerator.mixed_precision={no,fp16,bf16}`; the old `--policy.use_amp`
  (still used by LeLab) no longer exists.
- Its log line prints a **rounded** step (`step:5K`), so it cannot be used as the true step.

## Decision

- The worker image (`worker/`, package `worker`) pins **LeRobot 0.7.1, Python 3.12, torch 2.15**.
  The image digest and these versions are recorded in each run's manifest.
- `worker/train` launches `lerobot-train` as a **subprocess** with a CLI built from the validated
  run config (ADR-0005). The worker never imports LeRobot's training loop in-process.
- Always passed: `--trackio.enable=false`, `--output_dir=<run scratch dir>`, `--job_name=<run_id>`,
  `--seed`, `--accelerator.mixed_precision=<no|fp16|bf16>` (forced `no` on the P40, cuda1).
- The subprocess sees a single GPU (`CUDA_VISIBLE_DEVICES` = its node), runs in its own process
  group so cancel/pause can signal it, and has cgroup CPU/RAM limits from the container.
- **Metrics parsing:** the true step comes from the tqdm progress bar counter plus the initial step
  (non-zero on resume), never from the `step:` label. Spec: `docs/spec/log-parsing.md`.
- Pause = wait for/force a checkpoint then stop; resume = `--resume=true` from `checkpoints/last`.
- Checkpoints and `logs/train.log` are uploaded to `hibiscus-artifacts` (ADR-0004).
- Anomaly detection in the worker: NaN/Inf loss, no output for 5 min (hang), CUDA OOM, process exit.

## Consequences

### Positive
- 100% compatibility with upstream checkpoints and `pretrained_model/` layout.
- Upgrading LeRobot is an image bump plus the golden E2E run, not a code port.

### Negative
- Metrics come from parsing text output, which is brittle across LeRobot versions; the parser is
  version-specific and needs fixture tests.
- Less control over the inner loop (e.g. custom callbacks are impossible).

### Follow-ups agents must honor
- A4: the CLI builder is the only place that maps config to flags; unit tests assert the exact argv
  for each supported policy, including the P40 `mixed_precision=no` override.
- A4: log parser tests use captured real `lerobot-train` 0.7.1 output as fixtures, including a
  resumed run (initial step > 0) and step counts above 1000 (rounding case).
- A8: worker Dockerfile pins versions exactly; any LeRobot bump requires an ADR note and a green
  golden E2E (PLAN §6).
- Nobody vendors or monkey-patches LeRobot code.

## Rejected alternatives

- **Custom training loop importing LeRobot modules:** drifts from upstream, risks incompatible
  checkpoints.
- **Parsing trackio output:** adds a dependency on a logging backend we disable; log parsing of the
  progress bar is sufficient.

## Related

- ADR-0002, ADR-0005, ADR-0011
- `docs/spec/log-parsing.md`, `docs/spec/run-lifecycle.md`, `docs/spec/bundle.md`
