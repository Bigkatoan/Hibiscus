# Policy & training hyperparameter schemas (contract v0.1, ADR-0005)

Owner: A1 (generator prototype) → maintained by A4 · Consumers: A6 (form renderer), A4 (server-side
validation + argv builder), A9 (`hibiscus train --set key=value`).

## 1. Files

| File | Generated? | Content |
|---|---|---|
| `api/policy-schemas/<type>.json` for `act diffusion vqbet tdmpc smolvla pi0 pi05` | yes | JSON Schema 2020-12 of the policy config dataclass (`--policy.*`) |
| `api/policy-schemas/train.json` | yes | Whitelisted subset of `TrainPipelineConfig` (+ `accelerator.*`, `peft`) |
| `api/policy-schemas/index.json` | yes | lerobot version, generator version, policy list |
| `api/policy-schemas/presets.json` | **hand-written** | `quick` / `standard` / `finetune` presets, validated against the generated schemas by `backend/tests/contract` |

Generator: `backend/app/runs/policy_schema.py` (runs where LeRobot 0.7.1 is importable — worker
image or `~/lelab/leLab/.venv`; the API image never imports LeRobot):
```
env -u PYTHONPATH ~/lelab/leLab/.venv/bin/python backend/app/runs/policy_schema.py --out api/policy-schemas
env -u PYTHONPATH ~/lelab/leLab/.venv/bin/python backend/app/runs/policy_schema.py --out api/policy-schemas --check   # CI: exit 1 if stale
```
Upgrading LeRobot = bump pin → regenerate → review the diff → contract version bump if a field
disappears or changes type → golden E2E.

## 2. Mapping draccus dataclass → JSON Schema

Policies are draccus `ChoiceRegistry` subclasses of `PreTrainedConfig`; importing
`lerobot.policies.<p>.configuration_<p>` registers them, `PreTrainedConfig.get_choice_class(p)`
returns the dataclass. For each `dataclasses.fields(cls)` with `init=True`, using
`typing.get_type_hints(cls)`:

| Python type | JSON Schema |
|---|---|
| `bool` | `{"type": "boolean"}` |
| `int` | `{"type": "integer"}` (if the default is a `bool`, e.g. ACT `replace_final_stride_with_dilation: int = False`, `["boolean","integer"]` because LeRobot serialises `false`) |
| `float` | `{"type": "number"}` |
| `str` | `{"type": "string"}` |
| `X \| None` | `{"type": [X, "null"]}` for scalar X, else `anyOf: [X, null]` |
| `Enum` subclass | `{"type": "string", "enum": [member.value…]}` (e.g. `NormalizationMode`) |
| `Literal[...]` | `{"enum": [...]}` |
| `tuple[A, B]` | `array` with `prefixItems`, `minItems = maxItems = 2` |
| `tuple[A, ...]` | `array` with `items` |
| bare `tuple` | `array`, item type and length inferred from the default (`optimizer_betas → number × 2`) |
| `list[T]` | `array` / `items` |
| `dict[str, T]` | `object` / `additionalProperties: T` |
| nested dataclass | nested object (recursive, `additionalProperties: false`) |
| anything else (`torch.dtype`, `Path`, `PolicyFeature`) | field skipped with reason in `x-hibiscus.excluded` (only if not already excluded) |

Defaults: `field.default` or `field.default_factory()`; enums → `.value`, tuples → lists, Paths
→ str. Descriptions: the class docstring's Google-style `Args:` section (MRO merged, child wins),
else draccus `get_attribute_docstring` comment above/inline (TODO comments dropped).

Extra constraints that LeRobot enforces only in `__post_init__` are added from a reviewed table
(`EXTRA_CONSTRAINTS`, e.g. ACT `vision_backbone` pattern `^resnet`, `n_obs_steps` const 1,
diffusion `noise_scheduler_type ∈ {DDPM, DDIM}`, `prediction_type ∈ {epsilon, sample}`), and
cross-field rules that JSON Schema cannot express are listed in `x-hibiscus.cross_field_rules`
(e.g. `n_action_steps <= chunk_size`) and enforced server-side by A4 with code
`policy_config_invalid` (`FieldError.loc = ["body","config","policy","<field>"]`).

### Excluded fields (set by Hibiscus, never in the form)
`input_features`, `output_features` (from dataset), `device` (always cuda), `dtype`,
`use_amp` (superseded by `train.mixed_precision`), `use_peft` (implied by `train.peft`),
`push_to_hub`, `repo_id`, `private`, `tags`, `license` (Hub push is a separate action),
`pretrained_path`, `pretrained_revision` (from `RunCreate.init_from`), `rtc_config` (inference),
`compile_model`, `compile_mode` (torch.compile disabled on this box). Each schema lists them under
`x-hibiscus.excluded` with the reason.

## 3. Hibiscus annotations (`x-hibiscus*`)

Per property:
* `x-hibiscus-group`: `basic` | `advanced` (Basic tab shows `basic` in `x-hibiscus.basic_order`).
* `x-hibiscus-cli`: the exact lerobot-train flag, e.g. `--policy.chunk_size`,
  `--accelerator.mixed_precision`.

Per document (`x-hibiscus`): `policy_type`, `config_class`, `lerobot_version`,
`generator_version`, `cli_prefix`, `basic_order`, `excluded`, `cross_field_rules`; train.json
also has `managed_by_hibiscus` (flags the worker always sets itself).

The UI renders labels from i18n keys `policy.<type>.<field>.label` / `.help` when present (A7
provides vi/en copy for basic fields), falling back to the field name and the English
`description`.

## 4. Request shape and validation

`RunCreate.config = {"policy": {...}, "train": {...}}`. Clients SHOULD send only values that
differ from defaults (UI sends the full basic set). Server pipeline (A4):
1. effective = schema defaults ← preset (`presets.json`, `train`/`policy` then `per_policy[type]`)
   ← user values (deep merge);
2. validate `policy` against `<type>.json`, `train` against `train.json` (`additionalProperties:
   false` => unknown keys rejected, 422 `validation_failed`);
3. cross-field rules → 422 `policy_config_invalid`;
4. preflight (`PreflightReport`): dataset ready, camera keys/feature dims, `requires_reward`
   (tdmpc), PEFT required (pi0/pi05 → `policy_requires_peft`), VRAM estimate vs GPU, mixed
   precision forcing on P40, quota, GPU availability;
5. argv: for every key in effective `policy` that differs from the schema default emit
   `<x-hibiscus-cli>=<value>`; values serialised for draccus: booleans `true/false`, `null`
   → `null`, lists/tuples → `[a,b]` (JSON without spaces), dicts → JSON object; train keys
   always emitted. Stored in `runs.resolved_args`.

## 5. train.json (Hibiscus limits)

`steps` 1…2 000 000 (default 100 000), `batch_size` 1…512 (default 8), `num_workers` 0…8 (worker
clamps to 4), `log_freq` 10…10 000 (default 200), `save_freq` ≥ 100 (default 10 000),
`mixed_precision` `no|fp16|bf16`, `grad_accum_steps` 1…64, `image_transforms` (bool, LeRobot
default augmentation set), `seed`, `cudnn_deterministic`, `tf32`, `use_policy_training_preset`
(true = optimizer/scheduler from the policy's `optimizer_*`/`scheduler_*` fields), `peft`
(PeftConfig: `target_modules`, `full_training_modules`, `method_type` default LORA, `init_type`,
`r` default 16, `lora_alpha`). Optimizer/scheduler choice classes are not exposed in v1.

## 6. Verification performed for v0.1
* Generated all 9 files from LeRobot 0.7.1 (`--check` passes).
* Every generated schema passes `Draft202012Validator.check_schema`; the defaults object of each
  schema validates against it; the real ACT `config.json` of
  `outputs/train/act_picknplace/checkpoints/010000/pretrained_model` (minus excluded keys and
  `type`) validates against `act.json`; all presets validate for all policies
  (`backend/tests/contract/test_contract_consistency.py`).
