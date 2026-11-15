# ADR-0005: Hyperparameter forms generated from LeRobot draccus dataclasses via JSON Schema

- **Status:** Accepted (2026-11-15)
- **Deciders:** A1 (Solution Architect)
- **Source:** PLAN.md §2, ADR-5

## Context

LeLab hard-codes its training form and CLI flags; after LeRobot upgrades it emits flags that no longer
exist (`--policy.use_amp`, `--use_policy_training_preset`). Hibiscus supports ACT, Diffusion, VQ-BeT,
TD-MPC, SmolVLA and Pi0/Pi0.5 (LoRA, experimental), each with dozens of fields. LeRobot 0.7.1
defines these as draccus config dataclasses (policy configs, `TrainPipelineConfig`, optimizer,
scheduler, accelerator). We want the form, validation and CLI argv to follow LeRobot automatically.

## Decision

- A generator walks the pinned LeRobot's draccus dataclasses and emits one **JSON Schema (2020-12)**
  per policy plus a shared schema for train-level options (steps, batch size, `num_workers`, seed,
  `accelerator.mixed_precision`, eval split, save frequency).
- Generated schemas are committed under `api/policy-schemas/` (`<policy>.json` for act, diffusion,
  vqbet, tdmpc, smolvla, pi0, pi05; `train.json`; `index.json`) plus the hand-written
  `presets.json`, all owned by A1 as contract files (docs/spec/policy-schema.md). They are
  regenerated only when the LeRobot pin changes (`policy_schema.py --check` in CI).
- Field metadata: dataclass docstrings/comments become `description`; Hibiscus-specific hints use
  `x-hibiscus-*` keywords (`x-hibiscus-group: basic|advanced`, `x-hibiscus-cli`; per document
  `x-hibiscus.{basic_order, excluded, cross_field_rules}`). Hidden fields are omitted, not flagged.
- Excluded from forms: anything Hibiscus controls (`output_dir`, `job_name`, `dataset.repo_id`/root,
  `trackio.*`, `resume`, device selection).
- Presets per policy: "Quick (10k)", "Standard (100k)", "Fine-tune from checkpoint".
- `GET /api/v1/policies` and `GET /api/v1/policies/{policy}` serve the schema, UI hints and presets.
- The API validates submitted configs against the same schema (server side is authoritative), then
  the worker maps them to argv in exactly one CLI builder (ADR-0003).

## Consequences

### Positive
- Upgrading LeRobot updates forms, validation and flags together; no hand-maintained drift.
- Frontend renders any policy generically; adding a policy is mostly data.

### Negative
- draccus types (unions, nested choice types, enums) need careful mapping; some fields need manual
  `x-hibiscus-*` overrides kept in a small, reviewed overrides file.
- Schema diffs on a LeRobot bump must be reviewed as a contract change.

### Follow-ups agents must honor
- A4: server-side validation uses the committed schemas; unknown keys are rejected
  (`additionalProperties: false`); config errors are never retried (ADR-0002).
- A4: pre-flight checks beyond schema: dataset camera keys vs. policy `input_features`, VRAM estimate
  vs. selected GPU, dataset version validated; Pi0/Pi0.5 full fine-tune blocked (LoRA only, P40).
- A6: the form renderer is schema-driven; no policy-specific hard-coded fields; ordering comes from
  `x-hibiscus.basic_order`; labels/help text go through i18n keys `policy.<type>.<field>.*`.
- A9: CLI `hibiscus train --preset` resolves presets from the same endpoint.
- Changes to `api/policy-schemas/` only via contract change request (CONTRIBUTING).

## Rejected alternatives

- **Hard-coded forms (LeLab approach):** already broken against current LeRobot.
- **Free-form YAML/JSON config editor only:** no guidance, no validation UX; kept only as an
  "advanced: view raw config" read-only view.

## Related

- ADR-0003, ADR-0001, ADR-0007
- `api/policy-schemas/`, `api/openapi.yaml` (`/policies`), `docs/spec/run-lifecycle.md`
