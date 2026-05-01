<!--
Before opening this PR, please make sure:
- The PR targets `develop` (releases happen via `develop` → `main`).
- The branch is named `feature/<issue>-slug`, `fix/<issue>-slug`, or `docs/<topic>`.
- An issue describes the problem or feature (link it below).
-->

## What this changes

<!-- Concise summary. Reference the issue if there is one (e.g. "fixes #12"). -->

## Why

<!-- The motivation. What problem does this solve? -->

## How to verify

<!-- For BOOTSTRAP.md / *.tpl changes: describe the manual test. Ideally clone into a scratch dir, run the bootstrap, paste relevant output. -->

## Checklist

- [ ] PR targets `develop`
- [ ] Branch named `feature/…`, `fix/…`, or `docs/…`
- [ ] Change is **generic** (not domain-specific tooling — see CONTRIBUTING.md)
- [ ] If a new placeholder was added, it's documented in `PLACEHOLDERS.md`
- [ ] If a slash-command was added/modified, the README.md table is updated
- [ ] If `BOOTSTRAP.md` flow changed, an entry is added to `CHANGELOG.md` under `[Unreleased]`
- [ ] Commit messages follow the project convention (`<phase>: <what>` or `fix: <what>` / `feat: <what>`)
- [ ] All review conversations resolved before merge

## Notes for reviewers

<!-- Anything subtle, anything you're unsure about. -->
