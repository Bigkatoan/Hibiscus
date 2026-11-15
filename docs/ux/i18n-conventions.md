# i18n conventions (vi / en)

Owner: A7 (wording). A6 adds keys when building screens; A7 owns the text. Enforced by the vitest
suite in `frontend/src/lib/i18n.test.ts` (runs with `pnpm test`, see §8).

## 1. Where copy lives (single source of truth)

```
frontend/src/i18n/
├── vi/translation.json   # Vietnamese — primary language, default for new users
└── en/translation.json   # English — secondary, also the runtime fallback
```

* **These two files are the only copy the app loads** (`frontend/src/lib/i18n.ts`, i18next default
  namespace `translation`). There are no other namespace files; do not add any without wiring them
  into `i18n.ts` *and* the test. (An earlier draft split copy into 15 namespace files —
  `common.json`, `errors.json`, … — that were never loaded; their Vietnamese wording was merged
  into `translation.json` and the files were deleted on 2026-11-15.)
* Runtime: i18next 24 + react-i18next, `keySeparator "."`, `fallbackLng "en"`,
  `supportedLngs ["vi","en"]`, `interpolation.escapeValue false` (React escapes). Call sites use
  `t("run.status.running")`.
* Locale choice: stored preference (`prefs.lang`), else `navigator.language` (`en*` → en, otherwise
  vi). `<html lang>` follows the active language.
* Encoding: UTF-8 without BOM, NFC. Use typographic characters: `…` (not `...`), `“ ”`, `›` for
  menu paths, `·` as a separator, `—` for clauses.
* Error copy, laid out per contract code, is generated into `error-catalogue.md` (§8).

## 2. Key naming

* Every segment is **snake_case** (contract-derived segments keep the contract spelling, e.g.
  `schema_form.error.exclusiveMaximum`); group by **screen or concept first, element second**:
  `run.pause_help`, `datasets.tab.episodes`, `wizard.step.params`.
* Leaf conventions: `title`, `description` (page subtitle), `<x>_help` (helper text), `empty` /
  `empty_help` (empty state), `<verb>` (button), `<verb>_confirm` (confirmation question).
* Never encode the language or the widget type in the key.
* **Reserved suffixes** `_zero _one _two _few _many _other` are plural forms (§4).
* Keys are **stable**: renaming a key is a breaking change for A6. Change the text, not the key.

## 3. Keys derived from the contract

The UI never shows server `title`/`detail`/`message` strings (English, for logs). It maps machine
codes to keys. Rule for turning a contract value into a key segment: `camelCase → snake_case`, then
every run of characters outside `[a-z0-9]` → `_` (`datasets:write` → `datasets_write`).

| Contract source (`api/openapi.yaml`) | Key |
|---|---|
| `ErrorCode` (Problem.code) | `errors.<code>` — one sentence: what happened + what to do next. `src/lib/errors.ts` interpolates `Problem.params` and `retry_after_s`; unknown codes fall back to `errors.unknown_error` |
| `FieldError.code` | `field_errors.<code>` (fallback `errors.<Problem.code>`) |
| `RunStatus` / `RunErrorCode` / `RunWarningEvent.code` | `run.status.<s>` / `run.error.<code>` / `run.warning.<code>` |
| `ValidationIssue.code` | `validation.issue.<code>` (interpolates `episode`, `feature`, `path`) |
| `ValidationStepId` / `ValidationStep.status` | `validation.step.<id>` / `validation.step_status.<s>` |
| `ValidationSummary.result` / `ValidationSeverity` | `validation.result.<r>` / `validation.severity.<s>` |
| `DatasetVersionStatus` / `DatasetSource` | `dataset.status.<s>` / `datasets.source_kind.<s>` |
| `ModelStatus` / `OnnxStatus` | `model.status.<s>` / `model.onnx.<s>` |
| `JobStatus` | `job.status.<s>` |
| `WorkspaceRole` | `role.<r>` |
| `OnnxSupport` / `PolicyType` | `policy.onnx.<v>` / `policy.summary.<type>` |
| `PreflightCheck.id` | `preflight.check.<id>`; row text `preflight.code.<code>` → `errors.<code>` → `run.warning.<code>` |
| `Notification.kind` | `notifications.kind.<kind>` (kind keeps its dot, e.g. `run.failed`) |
| `ResourceEstimate.source` | `wizard.estimate_source.<s>` |
| `PatScope` | `tokens.scope.<snake>` |
| `NotificationChannelKind` | `account.channel_kind.<k>` |
| `AuditEvent.outcome` | `admin.outcome_value.<o>` |

The test iterates these enums **from `api/openapi.yaml`**, so a contract bump that adds a value
fails CI until copy exists.

## 4. Interpolation and plurals

* Syntax `{{name}}`. vi and en must use exactly the same placeholders per key (tested); keep any
  markup tags identical too.
* Never interpolate server `detail` text. Numbers, sizes and dates are formatted with `Intl` for
  the active locale **before** interpolation (`vi`: `1.234,5`; `en`: `1,234.5`).
* Plurals follow each language's CLDR categories (`Intl.PluralRules`, which i18next ≥ 21 uses):
  en has `x_one` + `x_other`; **vi has only `x_other`** (Vietnamese has no plural inflection, and
  i18next never looks up `x_one` for vi). The test derives the expected vi keys from en this way.
* Do not build sentences by concatenating keys; a full sentence is one key.

## 5. Terminology (vi)

Domain terms stay in English where Vietnamese robotics users use them in practice; UI chrome is
translated. Canonical list in `copy-deck.md` §2 (dataset, episode, frame, feature, policy,
checkpoint, batch size, learning rate, loss, metric, log, preset, workspace, token, bundle, GPU,
ONNX, mixed precision, seed; "lượt train" for *run*, "episode giữ lại" for *held-out*,
"kiểm chứng" for *verified*, "kiểm tra" for *validation*, "tham số" for *hyperparameters*).
Statuses: run/job/model/upload failure = "Thất bại"; validation verdict = "Không đạt" / "Đạt".

## 6. Adding or changing copy

1. A6 adds the key to **both** `vi/translation.json` and `en/translation.json`.
2. The test fails when < 97 % of vi strings differ from en. Strings made only of product names and
   glossary terms kept in English (`SAME_IN_VI` in the test: "GPU", "Dataset", "Loss", "Version
   {{version}}" …) are exempt; extend that list only for genuine glossary terms.
3. A7 reviews wording against the copy deck. Check the 390 px screenshots (§8): Vietnamese runs
   ~20–30 % longer — fix overflow by tightening the copy, never by shrinking fonts.
4. If the key is an error/issue/warning, regenerate `error-catalogue.md` (§8).

## 7. Things the UI must not do

* Show `Problem.detail`, `ValidationIssue.message`, `RunErrorEvent` messages, or log text as the
  primary message (only inside a collapsed technical-detail area, with `lang="en"`).
* Hard-code user-facing strings, including `aria-label`, `alt`, `title` and toast text.
* Use flags for language choice; use the language's own name (`Tiếng Việt`, `English`).

## 8. Commands

```bash
# i18n tests (part of the normal frontend suite; Node runs in Docker)
frontend/scripts/node.sh pnpm test
# regenerate docs/ux/error-catalogue.md, and check docs links + catalogue freshness
env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run --no-project --python 3.12 --with pyyaml \
    python docs/ux/tools/gen_error_catalogue.py
env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run --no-project --python 3.12 \
    --with pytest --with pyyaml pytest -q docs/ux/tools
```
