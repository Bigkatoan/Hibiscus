# docs/ux/ (owner: A7 CX/UX)

| File | What | Main reader |
|---|---|---|
| [personas.md](personas.md) | Lab owner, team member, collection operator | everyone |
| [user-flows.md](user-flows.md) | Every PLAN feature end to end (F0 primary journey … F15), API operationIds, copy keys, error/empty/loading states | A6, A9, A10 |
| [wireframes.md](wireframes.md) | Low-fi ASCII wireframes S-00 … S-18 for every screen A6 builds | A6 |
| [copy-deck.md](copy-deck.md) | Voice, glossary vi/en, copy patterns, error-usage rules, honesty strings, email copy | A6, A2 |
| [error-catalogue.md](error-catalogue.md) | **Generated**: every `ErrorCode`, `FieldError.code`, `ValidationIssue.code`, `RunErrorCode`, run warning → vi + en | A6, A9, A2 |
| [i18n-conventions.md](i18n-conventions.md) | Files, key naming, contract-derived keys, interpolation, plural rules | A6 |
| [accessibility.md](accessibility.md) | WCAG 2.1 AA checklist tailored to these screens + test procedure | A6, A10 |
| [uat.md](uat.md) | Acceptance script the user runs (Vietnamese), 61 steps, ★ = blocking | user, A10 |
| [tools/gen_error_catalogue.py](tools/gen_error_catalogue.py) | Renders `error-catalogue.md` from `api/openapi.yaml` + `translation.json` | A7 |
| [tools/test_docs.py](tools/test_docs.py) | pytest: docs links resolve, user guides paired, catalogue up to date | A7 |

**Copy itself lives in exactly two files: `frontend/src/i18n/vi/translation.json` (primary) and
`frontend/src/i18n/en/translation.json`** — the only resources the app loads
(`frontend/src/lib/i18n.ts`). They are checked by the vitest suite (`frontend/src/lib/i18n.test.ts`:
key parity, placeholders, ≥ 97 % translated, no empties/duplicates, every contract enum covered).
Key names quoted in `user-flows.md` / `wireframes.md` come from an earlier namespace draft
(`datasets.issue.*`, `runs.error.*` …); the live key for a contract code is given by
`i18n-conventions.md` §3.
User guide: `docs/user-guide/` (vi primary, en secondary).

```bash
# tests (repo root)
frontend/scripts/node.sh pnpm test                     # includes the i18n checks
env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run --no-project --python 3.12 \
    --with pytest --with pyyaml pytest -q docs/ux/tools  # docs links + catalogue freshness
# regenerate the error catalogue after changing errors/issue/warning copy
env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run --no-project --python 3.12 --with pyyaml \
    python docs/ux/tools/gen_error_catalogue.py
```
