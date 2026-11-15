# Model bundle specification (contract v0.1)

Owner: A1 · Implementer: A5 (`worker/export/`, `worker/eval/`) · Consumers: A4 (API download),
A6 (UI), A9 (`hibiscus pull`), users running LeRobot / LeLab (ADR-0011).

Normative JSON Schemas: `api/bundle-schemas/*.schema.json` (copied verbatim in the Appendix;
`backend/tests/contract/test_bundle_schemas.py` validates examples built from the real ACT
checkpoint `~/lelab/outputs/train/act_picknplace/checkpoints/010000/pretrained_model`,
see `docs/spec/examples/`).

## 1. Name and archive

* `bundle_name = <model_name>-r<run_number>-step<N>`; `model_name` = `ExportOptions.model_name` or
  `<dataset_slug>_<policy_type>` (lower-case, `[a-z0-9_-]`, ≤ 64), `N` = checkpoint step, not padded.
  Example: `so101_picknplace_act-r42-step10000`. (PLAN used `<run_id>`; a UUID is unreadable, the
  per-workspace run number is used instead — CONTRACT_NOTES §D4.)
* Download format: one zip `<bundle_name>.zip` whose single top-level directory is `<bundle_name>/`.
  `*.safetensors`, `*.onnx`, `*.png` are `ZIP_STORED`; everything else `ZIP_DEFLATED` level 6.
  Zip64 enabled. No symlinks, no absolute paths, Unix permissions 0644 (0755 for `*.sh`, `*.py`).
* Stored at `s3://hibiscus-artifacts/models/<model_id>/<bundle_name>.zip`; `models.bundle_sha256`
  = sha256 of the zip (HTTP `ETag`).

## 2. Tree (exact)

```
<bundle_name>/
├── pretrained_model/                       # byte-identical copy of checkpoints/<NNNNNN>/pretrained_model/
│   ├── config.json                         #   -> usable as --policy.path=<bundle>/pretrained_model
│   ├── model.safetensors
│   ├── train_config.json
│   ├── policy_preprocessor.json
│   ├── policy_preprocessor_step_<i>_normalizer_processor.safetensors      # name as written by lerobot
│   ├── policy_postprocessor.json
│   ├── policy_postprocessor_step_<j>_unnormalizer_processor.safetensors
│   └── <any other file lerobot wrote there, e.g. adapter_config.json / adapter_model.safetensors for PEFT>
├── onnx/                                   # present only when onnx_status = passed | failed
│   ├── model.onnx                          # onnx_support=full (act, vqbet)
│   ├── obs_encoder.onnx, denoiser.onnx     # onnx_support=split (diffusion) instead of model.onnx
│   ├── model.fp16.onnx                     # optional (ExportOptions.onnx_fp16), full only
│   ├── io_spec.json                        # §4, schema io_spec.schema.json
│   ├── normalization.json                  # §4.3, schema normalization.schema.json
│   ├── parity_report.json                  # §6, schema parity_report.schema.json
│   ├── infer_onnx.py                       # §7
│   └── requirements.txt                    # numpy, onnxruntime (pinned), opencv-python-headless
├── eval/                                   # present when ExportOptions.eval and held-out episodes exist
│   ├── metrics.json                        # schema = OpenAPI EvalMetrics
│   └── plots/
│       ├── per_joint_mae.png
│       └── episode_<idx:03d>.png           # pred vs GT per joint, one per held-out episode (max 10)
├── logs/
│   ├── train.log                           # all attempts concatenated, tqdm frames collapsed
│   └── metrics.csv                         # header: step,key,value,ts (full resolution, run_metrics)
├── run_on_robot.sh                         # §8
├── MODEL_CARD.md                           # §9
└── MANIFEST.json                           # §3 (written last)
```

`pretrained_model/` MUST be byte-identical to the checkpoint (`train_config.json` included, even
though it contains worker-local absolute paths such as `/cache/datasets/<id>`; LeRobot inference
only reads `config.json`, weights and processor files). Verification compares sha256 against the
checkpoint files in MinIO.

## 3. MANIFEST.json

* Lists every file in the bundle except itself, sorted by path (bytewise), with size and sha256.
* `checks.load_ok` / `checks.parity_ok` / `checks.onnx_status` record the results available
  before the zip is built; `manifest_ok` (re-hashing the files from the produced zip) is computed
  after zipping and stored in `models.verification` only.
* Schema: `api/bundle-schemas/manifest.schema.json`. Example: `docs/spec/examples/MANIFEST.example.json`
  (real hashes of the 7 files of the ACT checkpoint; other entries omitted in the example).

## 4. ONNX interface

### 4.1 Common rules
* Opset **17**, exported with `torch.onnx.export(..., dynamo=False)` from the eval-mode policy on
  CPU in float32, `do_constant_folding=True`, dynamic axis **only** the batch axis (`"batch"`).
* Graph input / output **names are the LeRobot feature keys verbatim** (`observation.state`,
  `observation.images.<cam>`, `observation.environment_state`, `action`). Internal tensors use the
  fixed names below. Graph inputs/outputs are **normalised** tensors (PLAN §3.6); pre/post
  processing uses `normalization.json`.
* Camera input order = order of `observation.images.*` keys in `pretrained_model/config.json`
  `input_features` (insertion order) = `io_spec.cameras` order.
* Images: input shape `[batch, 3, H, W]` (or `[batch, n_obs_steps, 3, H, W]`) with `H, W` from
  `config.json` `input_features[key].shape` — no resizing happens inside the graph unless the
  policy itself resizes/crops (diffusion/vqbet center-crop in eval is part of the graph).
* Pre-processing (`io_spec.image_preprocess.steps`): decoded RGB uint8 HWC → float32 → /255 →
  CHW → normalise with the feature's mode → add batch dim (→ stack `n_obs_steps` most recent frames
  for diffusion/vqbet, oldest first).
* Normalisation formulas (identical to `lerobot.processor.normalize_processor`, `eps = 1e-8`):
  `MEAN_STD: (x - mean) / (std + eps)`; `MIN_MAX: 2 * (x - min) / max(max - min, eps) - 1`;
  `QUANTILES: 2 * (x - q01) / max(q99 - q01, eps) - 1`; `QUANTILE10` likewise with q10/q90;
  `IDENTITY: x`. Un-normalisation is the exact inverse. Image stats broadcast per channel.

### 4.2 Per policy
| policy | graph id / file | inputs | outputs |
|---|---|---|---|
| act | `model` / `model.onnx` | `observation.state [batch, S]` (if in input_features), `observation.images.<cam> [batch,3,H,W]` ×C, `observation.environment_state [batch, E]` (if present) | `action [batch, chunk_size, A]` (VAE latent = zeros, eval path) |
| vqbet | `model` / `model.onnx` | `observation.state [batch, n_obs_steps, S]`, `observation.images.<cam> [batch, n_obs_steps, 3, H, W]`, `sampling_noise [batch, n_action_pred_token, 2]` (float32 uniform in [0,1); one value per primary/secondary code draw) | `action [batch, action_chunk_size, A]` |
| diffusion | `obs_encoder` / `obs_encoder.onnx` | `observation.state [batch, n_obs_steps, S]`, `observation.images.<cam> [batch, n_obs_steps, 3, H, W]` | `global_cond [batch, G]` |
| diffusion | `denoiser` / `denoiser.onnx` | `noisy_action [batch, horizon, A]` (float32), `timestep [batch]` (int64), `global_cond [batch, G]` | `model_output [batch, horizon, A]` (epsilon or sample per `prediction_type`) |
| tdmpc, smolvla, pi0, pi05 | — | — | no ONNX in v1 (`onnx_status = not_supported`) |

For diffusion `io_spec.diffusion` carries the scheduler parameters (`noise_scheduler_type`,
`num_train_timesteps`, `num_inference_steps` (= config value or `num_train_timesteps` when null),
`beta_schedule`, `beta_start`, `beta_end`, `prediction_type`, `clip_sample`, `clip_sample_range`,
`horizon`); `infer_onnx.py` implements DDPM and DDIM stepping in numpy exactly like `diffusers`
(LeRobot's dependency) and takes actions `[n_obs_steps - 1 : n_obs_steps - 1 + n_action_steps]`.

VQ-BeT samples codes with `torch.multinomial` (stochastic). The ONNX graph replaces it by
inverse-CDF sampling driven by the explicit `sampling_noise` input
(`code = argmax(cumsum(softmax(logits / T)) > u)`); the parity reference is the PyTorch module
with `torch.multinomial` replaced by the same inverse-CDF on the same `u`. `infer_onnx.py` draws
`u` with `numpy.random.default_rng()`.

### 4.3 normalization.json
Values are taken from the bundle's `policy_preprocessor_step_*_normalizer_processor.safetensors`
(inputs) and `policy_postprocessor_step_*_unnormalizer_processor.safetensors` (`action`), only for
features in `input_features ∪ output_features`, only the stats needed by the feature's mode,
flattened (`[3,1,1] → [3]`), serialised as JSON numbers via `float(np.float32(v))` (no rounding).
Example (real ACT checkpoint): `docs/spec/examples/normalization.example.json`.

## 5. eval/metrics.json
Schema = OpenAPI `components.schemas.EvalMetrics`. Computed by `worker/eval` on held-out episodes
(run `heldout_episodes`): for every frame, `select_action`-equivalent single-step prediction
(policy `reset()` at episode start; ACT/VQ-BeT/diffusion queues replayed exactly as in rollout)
versus the recorded `action`, in **unnormalised** joint units. `mae`, `mse` per joint and overall
(mean over joints), `mae_normalized` = MAE in normalised space. `disclaimer_key =
eval.offline_not_success_rate` (UI must show it — PLAN §3.5).

## 6. Parity (gating for `verified`)

* Runtime: onnxruntime `CPUExecutionProvider` vs PyTorch eval mode on CPU, float32, identical
  normalised inputs, `torch.manual_seed(0)`.
* Samples: `n_samples = 32` frames drawn with `random.Random(0)` from held-out episodes (all
  episodes if none held out); real decoded frames from the dataset version (AV1 decoded once by
  torchcodec, the same tensor fed to both runtimes — decoder differences are out of scope).
* Pass criterion per comparison: `np.allclose(onnx, torch, atol, rtol)` on the graph output.

| comparison | policies | atol | rtol | gating |
|---|---|---|---|---|
| `model` | act, vqbet | 1e-4 | 1e-4 | yes |
| `obs_encoder` | diffusion | 1e-4 | 1e-4 | yes |
| `denoiser_single_step` | diffusion | 1e-4 | 1e-4 | yes (3 random timesteps per sample) |
| `full_denoise_loop` | diffusion | 1e-3 | 1e-3 | yes (same initial noise `np.random.default_rng(0)`, numpy loop in infer_onnx.py vs `policy.diffusion.conditional_sample`) |
| `model_fp16` | act, vqbet | 1e-2 | 1e-2 | no (informational) |

`parity_report.json.passed` = all gating comparisons passed.

## 7. infer_onnx.py (no LeRobot dependency)
* Python ≥ 3.10, imports only `numpy`, `onnxruntime`, `json`, `argparse`, optional `cv2`.
* API: `class OnnxPolicy(bundle_dir)`, `.reset()`, `.select_action(obs: dict[str, np.ndarray]) -> np.ndarray[A]`
  where `obs` holds `observation.state` (float32 `[S]`) and `observation.images.<cam>` (uint8
  HWC RGB). Implements normalisation, observation history, action chunk queue (`n_action_steps`),
  un-normalisation, and for diffusion the denoising loop.
* CLI self-test: `python infer_onnx.py --bundle .. --selftest` runs one random observation and
  prints the action and latency; exit 0 on finite output.

## 8. run_on_robot.sh
Generated from the dataset version (`robot_type`, `fps`, camera keys/shapes, first task) for the
LeRobot CLI inside the LeLab venv (ADR-11). Template (values filled at export):
```bash
#!/usr/bin/env bash
# Generated by Hibiscus for <bundle_name>. Edit PORT / camera indices, then run inside the LeLab venv:
#   source ~/lelab/leLab/.venv/bin/activate && ./run_on_robot.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-/dev/ttyACM0}"            # robot serial port
ROBOT_ID="${ROBOT_ID:-my_follower}"     # must match your calibration id
WRIST_CAM="${WRIST_CAM:-0}"             # one variable per camera key, upper-cased camera name
lerobot-rollout \
  --strategy.type=base \
  --policy.path="$HERE/pretrained_model" \
  --robot.type=so101_follower \
  --robot.port="$PORT" --robot.id="$ROBOT_ID" \
  --robot.cameras="{ wrist_cam: {type: opencv, index_or_path: ${WRIST_CAM}, width: 640, height: 360, fps: 30} }" \
  --task="<first task of the dataset>" \
  --fps=30 --duration="${DURATION:-60}"
```
Robot type mapping from dataset `robot_type`: `so_follower`/`so101_follower` → `so101_follower`,
`so100_follower` → `so100_follower`, `koch_follower` → `koch_follower`, anything else is written
verbatim with a `# TODO(user): verify --robot.type` comment **in the generated script** (the only
place a TODO may appear). A second commented block shows the `lerobot-record --policy.path=...`
variant for recording evaluation episodes.

## 9. MODEL_CARD.md
Sections (en, with vi translation below each heading): Summary (policy, dataset@version, step,
verified badge), Intended use & limitations (offline eval ≠ success rate), Training (hyperparameters
table = resolved config diff vs defaults, GPU, duration, mixed precision, seed, split), Results
(final loss, eval table, link to plots), How to run (LeRobot `--policy.path`, `run_on_robot.sh`,
ONNX `infer_onnx.py`, `hibiscus pull`), Reproducibility (versions, image digest, dataset hash),
Files (link to MANIFEST.json). For Hub pushes it is uploaded as `README.md` with YAML front matter
(`library_name: lerobot`, `tags: [lerobot, <policy>, robotics]`, `datasets: [<repo_id if public>]`).

## 10. Verification ("verified" badge, PLAN §3.6)
`verified = load_ok ∧ manifest_ok ∧ (parity_ok if onnx_support ≠ none and ExportOptions.onnx)`.
* `load_ok`: fresh subprocess in the worker image: `get_policy_class(type).from_pretrained(dir)`,
  `PolicyProcessorPipeline.from_pretrained(dir, "policy_preprocessor.json")` and postprocessor;
  one `select_action` on a real dataset frame returns a finite tensor of shape `[1, A]`.
* `manifest_ok`: unzip the produced archive to a temp dir, re-hash every file, compare with
  MANIFEST.json (and no extra / missing files).
* `parity_ok`: §6. `null` when ONNX is not supported/requested (does not block `verified`).

## 11. Policy support matrix (v1)

| policy | trainable on | ONNX | verified possible | notes |
|---|---|---|---|---|
| act | 3060, P40 | full | yes | golden E2E policy |
| vqbet | 3060, P40 | full | yes | code sampling via explicit `sampling_noise` input (§4.2) |
| diffusion | 3060, P40 | split | yes | loop in infer_onnx.py |
| tdmpc | 3060, P40 | none | yes (no parity) | requires `next.reward` in dataset (preflight `policy_requirements`) |
| smolvla | 3060 (limited, bf16), P40 (fp32) | none | yes (no parity) | VLM + tokenizer; needs Hub download at preparing |
| pi0, pi05 | P40 only, PEFT/LoRA only | none | yes (no parity) | experimental; full fine-tune blocked |

## Appendix A — JSON Schemas (verbatim copies of `api/bundle-schemas/`)

Generated; `backend/tests/contract/test_bundle_schemas.py::test_appendix_matches_files` fails if they drift.

### manifest.schema.json

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://hibiscus.local/api/bundle-schemas/manifest.schema.json",
  "title": "Hibiscus bundle MANIFEST.json v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "bundle_name", "created_at", "hibiscus_version", "model_id", "run", "checkpoint_step",
               "policy", "dataset", "software", "training", "checks", "files"],
  "properties": {
    "schema_version": {"const": "1"},
    "bundle_name": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,63}-r[0-9]+-step[0-9]+$"},
    "created_at": {"type": "string", "format": "date-time"},
    "hibiscus_version": {"type": "string"},
    "model_id": {"type": "string", "format": "uuid"},
    "run": {
      "type": "object", "additionalProperties": false, "required": ["id", "number", "name", "workspace_id"],
      "properties": {
        "id": {"type": "string", "format": "uuid"},
        "number": {"type": "integer", "minimum": 1},
        "name": {"type": "string"},
        "workspace_id": {"type": "string", "format": "uuid"}
      }
    },
    "checkpoint_step": {"type": "integer", "minimum": 1},
    "policy": {
      "type": "object", "additionalProperties": false, "required": ["type", "onnx_support", "chunk_size", "n_action_steps"],
      "properties": {
        "type": {"enum": ["act", "diffusion", "vqbet", "tdmpc", "smolvla", "pi0", "pi05"]},
        "onnx_support": {"enum": ["full", "split", "none"]},
        "chunk_size": {"type": ["integer", "null"], "minimum": 1, "description": "act/smolvla/pi0*: chunk_size; diffusion: horizon; vqbet: action_chunk_size; tdmpc: horizon"},
        "n_action_steps": {"type": ["integer", "null"], "minimum": 1},
        "peft": {"type": ["object", "null"]}
      }
    },
    "dataset": {
      "type": "object", "additionalProperties": false,
      "required": ["dataset_id", "version_id", "version", "name", "content_hash", "repo_id", "robot_type", "fps", "camera_keys", "state_names", "action_names", "tasks"],
      "properties": {
        "dataset_id": {"type": "string", "format": "uuid"},
        "version_id": {"type": "string", "format": "uuid"},
        "version": {"type": "integer", "minimum": 1},
        "name": {"type": "string"},
        "content_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "repo_id": {"type": "string"},
        "robot_type": {"type": ["string", "null"]},
        "fps": {"type": "number", "exclusiveMinimum": 0},
        "camera_keys": {"type": "array", "items": {"type": "string", "pattern": "^observation\\.images\\."}},
        "state_names": {"type": "array", "items": {"type": "string"}},
        "action_names": {"type": "array", "items": {"type": "string"}},
        "tasks": {"type": "array", "items": {"type": "string"}}
      }
    },
    "software": {
      "type": "object", "additionalProperties": false,
      "required": ["lerobot", "torch", "cuda", "python", "image_digest"],
      "properties": {
        "lerobot": {"type": "string"},
        "torch": {"type": "string"},
        "cuda": {"type": ["string", "null"]},
        "python": {"type": "string"},
        "onnx": {"type": ["string", "null"]},
        "onnxruntime": {"type": ["string", "null"]},
        "image_digest": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
      }
    },
    "training": {
      "type": "object", "additionalProperties": false,
      "required": ["seed", "total_steps", "batch_size", "mixed_precision", "gpu_name", "heldout_episodes", "train_episodes", "gpu_seconds"],
      "properties": {
        "seed": {"type": "integer"},
        "total_steps": {"type": "integer", "minimum": 1},
        "batch_size": {"type": "integer", "minimum": 1},
        "mixed_precision": {"enum": ["no", "fp16", "bf16"]},
        "gpu_name": {"type": "string"},
        "heldout_episodes": {"type": "array", "items": {"type": "integer", "minimum": 0}},
        "train_episodes": {"type": "array", "items": {"type": "integer", "minimum": 0}},
        "gpu_seconds": {"type": "number", "minimum": 0},
        "final_loss": {"type": ["number", "null"]}
      }
    },
    "checks": {
      "type": "object", "additionalProperties": false,
      "required": ["load_ok", "parity_ok", "onnx_status"],
      "description": "Results known when the manifest is written. manifest_ok (hash re-check of the zip) is recorded in the DB only.",
      "properties": {
        "load_ok": {"type": "boolean"},
        "lelab_compatible": {"type": "boolean", "description": "Loads and runs select_action in the LeLab venv (LeRobot 0.7.1 without optional extras) with no extra packages"},
        "lelab_check": {"enum": ["lelab_venv", "emulated"], "description": "lelab_venv = checked with a LeLab interpreter; emulated = worker interpreter with the packages LeLab lacks hidden"},
        "lelab_requirements": {"type": "array", "items": {"type": "string"}, "description": "pip requirements to install inside the LeLab venv before running this bundle (empty = none)"},
        "parity_ok": {"type": ["boolean", "null"]},
        "onnx_status": {"enum": ["not_supported", "passed", "failed", "skipped"]},
        "eval": {"type": ["object", "null"], "properties": {"action_mae": {"type": "number"}, "action_mse": {"type": "number"}}}
      }
    },
    "files": {
      "type": "array", "minItems": 1,
      "description": "Every file of the bundle except MANIFEST.json itself, sorted by path (bytewise).",
      "items": {
        "type": "object", "additionalProperties": false, "required": ["path", "size", "sha256"],
        "properties": {
          "path": {"type": "string", "pattern": "^(?!/)(?!.*\\.\\./)(?!MANIFEST\\.json$)[A-Za-z0-9_.@+/-]+$"},
          "size": {"type": "integer", "minimum": 0},
          "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
        }
      }
    }
  }
}
```

### io_spec.schema.json

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://hibiscus.local/api/bundle-schemas/io_spec.schema.json",
  "title": "Hibiscus bundle onnx/io_spec.json v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "policy_type", "onnx_support", "opset", "fps", "graphs", "cameras", "state", "action", "normalization_file", "image_preprocess"],
  "$defs": {
    "dim": {"oneOf": [{"type": "integer", "minimum": 1}, {"enum": ["batch"]}]},
    "tensor": {
      "type": "object", "additionalProperties": false, "required": ["name", "dtype", "shape", "role"],
      "properties": {
        "name": {"type": "string", "minLength": 1},
        "lerobot_key": {"type": ["string", "null"], "description": "LeRobot feature key this tensor carries (null for internal tensors such as timestep)"},
        "dtype": {"enum": ["float32", "float16", "int64"]},
        "shape": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/dim"}},
        "role": {"enum": ["state", "image", "action", "noisy_action", "timestep", "global_cond", "env_state", "sampling_noise", "model_output"]},
        "normalized": {"type": "boolean", "description": "true = value is in the policy's normalised space (see normalization.json)"}
      }
    }
  },
  "properties": {
    "schema_version": {"const": "1"},
    "policy_type": {"enum": ["act", "diffusion", "vqbet"]},
    "onnx_support": {"enum": ["full", "split"]},
    "opset": {"const": 17},
    "fps": {"type": "number", "exclusiveMinimum": 0},
    "n_obs_steps": {"type": "integer", "minimum": 1},
    "graphs": {
      "type": "array", "minItems": 1, "maxItems": 2,
      "items": {
        "type": "object", "additionalProperties": false, "required": ["id", "file", "inputs", "outputs"],
        "properties": {
          "id": {"enum": ["model", "obs_encoder", "denoiser"]},
          "file": {"type": "string", "pattern": "^[a-z_]+(\\.fp16)?\\.onnx$"},
          "fp16_file": {"type": ["string", "null"]},
          "inputs": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/tensor"}},
          "outputs": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/tensor"}}
        }
      }
    },
    "cameras": {
      "type": "array",
      "description": "Order = order of image inputs in the graph and in LeRobot config.input_features.",
      "items": {
        "type": "object", "additionalProperties": false, "required": ["key", "input_name", "height", "width", "channels_order", "source_codec"],
        "properties": {
          "key": {"type": "string", "pattern": "^observation\\.images\\."},
          "input_name": {"type": "string"},
          "height": {"type": "integer", "minimum": 1},
          "width": {"type": "integer", "minimum": 1},
          "channels_order": {"const": "RGB"},
          "source_codec": {"type": ["string", "null"]}
        }
      }
    },
    "state": {
      "type": ["object", "null"], "additionalProperties": false, "required": ["key", "dim", "names"],
      "properties": {"key": {"type": "string"}, "dim": {"type": "integer", "minimum": 1}, "names": {"type": "array", "items": {"type": "string"}}}
    },
    "action": {
      "type": "object", "additionalProperties": false, "required": ["key", "dim", "names", "chunk_size", "n_action_steps"],
      "properties": {
        "key": {"const": "action"},
        "dim": {"type": "integer", "minimum": 1},
        "names": {"type": "array", "items": {"type": "string"}},
        "chunk_size": {"type": "integer", "minimum": 1},
        "n_action_steps": {"type": "integer", "minimum": 1},
        "temporal_ensemble_coeff": {"type": ["number", "null"], "description": "ACT only: LeRobot ACTTemporalEnsembler coefficient. When set, select_action runs the graph every step and blends the overlapping chunks with weights exp(-coeff*i) (infer_onnx.py implements it); null = execute n_action_steps of each chunk"}
      }
    },
    "normalization_file": {"const": "normalization.json"},
    "image_preprocess": {
      "type": "object", "additionalProperties": false, "required": ["input", "steps"],
      "properties": {
        "input": {"const": "uint8 HWC RGB frame as decoded from the camera"},
        "steps": {"type": "array", "items": {"enum": ["to_float32", "divide_255", "hwc_to_chw", "normalize", "add_batch_dim", "stack_obs_steps"]}}
      }
    },
    "diffusion": {
      "type": ["object", "null"], "additionalProperties": false,
      "required": ["scheduler", "num_train_timesteps", "num_inference_steps", "beta_schedule", "beta_start", "beta_end", "prediction_type", "clip_sample", "clip_sample_range", "horizon"],
      "properties": {
        "scheduler": {"enum": ["DDPM", "DDIM"]},
        "num_train_timesteps": {"type": "integer"},
        "num_inference_steps": {"type": "integer"},
        "beta_schedule": {"type": "string"},
        "beta_start": {"type": "number"},
        "beta_end": {"type": "number"},
        "prediction_type": {"enum": ["epsilon", "sample"]},
        "clip_sample": {"type": "boolean"},
        "clip_sample_range": {"type": "number"},
        "horizon": {"type": "integer"}
      }
    }
  },
  "allOf": [
    {"if": {"properties": {"onnx_support": {"const": "split"}}}, "then": {"required": ["diffusion"], "properties": {"graphs": {"minItems": 2}}}}
  ]
}
```

### normalization.schema.json

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://hibiscus.local/api/bundle-schemas/normalization.schema.json",
  "title": "Hibiscus bundle onnx/normalization.json v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "eps", "features"],
  "properties": {
    "schema_version": {"const": "1"},
    "eps": {"type": "number", "description": "lerobot NormalizerProcessorStep.eps (1e-8)"},
    "features": {
      "type": "object",
      "description": "Only features the policy normalises (inputs + action). Arrays have the stat's natural shape flattened per channel/dim: state/action [dim]; images [3] (per channel).",
      "additionalProperties": {
        "type": "object", "additionalProperties": false, "required": ["type", "mode"],
        "properties": {
          "type": {"enum": ["STATE", "VISUAL", "ACTION", "ENV"]},
          "mode": {"enum": ["MEAN_STD", "MIN_MAX", "QUANTILES", "QUANTILE10", "IDENTITY"]},
          "mean": {"type": "array", "items": {"type": "number"}},
          "std": {"type": "array", "items": {"type": "number"}},
          "min": {"type": "array", "items": {"type": "number"}},
          "max": {"type": "array", "items": {"type": "number"}},
          "q01": {"type": "array", "items": {"type": "number"}},
          "q99": {"type": "array", "items": {"type": "number"}},
          "q10": {"type": "array", "items": {"type": "number"}},
          "q90": {"type": "array", "items": {"type": "number"}}
        }
      }
    }
  }
}
```

### parity_report.schema.json

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://hibiscus.local/api/bundle-schemas/parity_report.schema.json",
  "title": "Hibiscus bundle onnx/parity_report.json v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "passed", "provider", "n_samples", "sample_source", "seed", "graphs"],
  "properties": {
    "schema_version": {"const": "1"},
    "passed": {"type": "boolean", "description": "All gating comparisons passed"},
    "provider": {"const": "CPUExecutionProvider"},
    "torch_device": {"const": "cpu"},
    "n_samples": {"type": "integer", "minimum": 1},
    "sample_source": {"enum": ["heldout", "train"]},
    "seed": {"type": "integer"},
    "graphs": {
      "type": "array",
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["comparison", "file", "atol", "rtol", "max_abs_diff", "max_rel_diff", "passed", "gating"],
        "properties": {
          "comparison": {"enum": ["model", "obs_encoder", "denoiser_single_step", "full_denoise_loop", "model_fp16"]},
          "file": {"type": "string"},
          "atol": {"type": "number"},
          "rtol": {"type": "number"},
          "max_abs_diff": {"type": "number"},
          "max_rel_diff": {"type": "number"},
          "mean_abs_diff": {"type": "number"},
          "max_abs_diff_unnormalized": {"type": ["number", "null"], "description": "Action space (joint units) after unnormalisation"},
          "passed": {"type": "boolean"},
          "gating": {"type": "boolean", "description": "false => informational only (fp16)"}
        }
      }
    }
  }
}
```
