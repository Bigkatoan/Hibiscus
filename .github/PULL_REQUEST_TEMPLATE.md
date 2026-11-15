<!-- Thanks for contributing to Hibiscus! 🌺  Title: Conventional Commits, e.g. `feat(train): resume from last checkpoint` -->

## What and why

<!-- What does this PR change, and why? Link the issue it resolves. -->

Closes #

## How was it tested?

<!-- Commands you ran and their result (e.g. `uv run pytest`, `pnpm test`, manual steps on a GPU). -->

## Screenshots

<!-- UI changes: before / after, day and night themes, and 390 px mobile width if the layout changed. -->

## Checklist

- [ ] Lint, type-check and tests pass locally (`make ci` or the per-project commands in CONTRIBUTING.md)
- [ ] New behaviour is covered by tests (GPU-only tests are marked `@pytest.mark.gpu`)
- [ ] API changes start in `api/openapi.yaml` and generated clients are regenerated, not hand-edited
- [ ] New UI strings exist in both `vi` and `en`
- [ ] No secrets, tokens, private hostnames or personal paths in code, tests, fixtures or logs
- [ ] Docs and `CHANGELOG.md` (`## [Unreleased]`) updated for user-visible changes
