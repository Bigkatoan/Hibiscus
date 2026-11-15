# ADR-0011: Do not patch LeLab; integrate through the LeRobot-standard bundle format

- **Status:** Accepted (2026-11-15)
- **Deciders:** A1 (Solution Architect), confirmed by owner (PLAN §10.5)
- **Source:** PLAN.md §2, ADR-11; §3.6, §3.7

## Context

LeLab (in `~/lelab/leLab`) has a `/start-training` endpoint with outdated LeRobot flags and **no
inference / "run policy" feature**. The owner decided LeLab will not be modified. Models trained by
Hibiscus must still be usable on the robot from the LeLab environment, and remain compatible when
LeLab upstream adds inference.

## Decision

- Compatibility is achieved through **file format only**. Each model is delivered as a bundle
  `<model_name>-<run_id>-step<N>/` (spec: `docs/spec/bundle.md`):
  - `pretrained_model/` — **identical** to LeRobot's output (`config.json`, `model.safetensors`,
    `train_config.json`, pre/postprocessor JSON + safetensors), usable directly with
    `--policy.path=<bundle>/pretrained_model` in `lerobot-record`, `lerobot-rollout`, `lerobot-eval`.
  - `onnx/` — `model.onnx` (opset 17), optional `model.fp16.onnx`, `io_spec.json`,
    `normalization.json`, `parity_report.json`, `infer_onnx.py` (ACT/VQ-BeT full; Diffusion UNet +
    external denoise loop; SmolVLA/Pi0 not exported in v1).
  - `eval/` (`metrics.json`, `plots/*.png`), `logs/` (`train.log`, `metrics.csv`).
  - `MODEL_CARD.md`, `MANIFEST.json` (sha256 of every file, software versions, `dataset@version`).
  - `run_on_robot.sh` — a generated `lerobot-record` command with camera keys, fps, `robot.type` and
    task filled from the dataset; the user edits only the serial port.
- Inference runs with the **LeRobot CLI inside LeLab's venv** (`~/lelab/leLab/.venv`).
  `hibiscus pull <model> --to <dir>` places the bundle where that venv can read it; optional HF Hub
  push allows loading by `repo_id`.
- A bundle is "verified" only if: `PreTrainedPolicy.from_pretrained` loads it, ONNX parity passes
  (atol 1e-4 fp32) where ONNX applies, and `MANIFEST.json` hashes match.
- PLAN §8.2's "patch LeLab" items for A9 and M6 are superseded by this ADR: A9 delivers CLI and
  `run_on_robot.sh` integration instead; no `hibiscus-integration` LeLab branch is created.

## Consequences

### Positive
- Zero coupling to LeLab's codebase and release cycle; bundles work with any LeRobot tooling.
- Forward compatible with upstream LeLab inference since the format is LeRobot-standard.

### Negative
- No one-click "run on robot" from LeLab's UI in v1; users run a shell script/CLI.
- `run_on_robot.sh` must track LeRobot 0.7.1 CLI flags; drift requires regeneration.

### Follow-ups agents must honor
- A5: bundle builder in `worker/export` produces exactly the layout in `docs/spec/bundle.md`;
  tests load `pretrained_model/` with LeRobot 0.7.1 and check `MANIFEST.json`.
- A9: no files under `~/lelab/leLab` are modified by any agent or by `hibiscus` (pull writes only to
  the target directory); M6 acceptance = push → train → pull → `run_on_robot.sh` dry-run in LeLab venv.
- A7: user guide documents the LeLab-venv inference path and the current LeLab limitation.

## Rejected alternatives

- **Patch LeLab (import/run-policy features):** rejected by the owner; maintenance burden on a fork.

## Related

- ADR-0003 (unmodified LeRobot), ADR-0004 (artifacts bucket)
- `docs/spec/bundle.md`, `docs/user-guide/`
