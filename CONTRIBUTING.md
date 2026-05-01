# Contributing

Thanks for your interest in BoilingBrain. This project is opinionated — the opinions come from real usage in a personal vault — but generic improvements are welcome.

## What belongs here

- **Generic improvements** to the bootstrap interview, scaffolding, slash-commands shipped by default, scripts, or architectural decisions.
- **Bug fixes** in `BOOTSTRAP.md`, `*.tpl` files, or scripts.
- **Documentation clarifications** when something is ambiguous to a first-time reader.

## What doesn't belong here

- **Domain-specific tooling** (poker OCR, LaTeX renderer, k8s validator, etc.). Keep these in your own vault instance — that's the whole point of the template/instance separation. Add a note in your vault's README about what you built.
- **Cosmetic refactors** without a behavioral motivation.
- **Renaming sweeps** that don't change semantics.

## Branching model (git flow)

This repo uses a simple [git flow](https://nvie.com/posts/a-successful-git-branching-model/) layout:

| Branch | Role |
|---|---|
| `main` | Tagged releases only (`vX.Y.Z`). Updated by merging `develop` at release time. Protected. |
| `develop` | **Default branch.** Integration line — all contributions land here first. Protected. |
| `feature/<issue>-slug` | New feature, branched from `develop`, merged back to `develop`. |
| `fix/<issue>-slug` | Bug fix, branched from `develop`, merged back to `develop`. |
| `docs/<topic>` | Doc-only change, branched from `develop`, merged back to `develop`. |

Contributor flow:

1. **Open an issue** describing the bug or feature (skip only for trivial doc fixes).
2. **Fork** the repo (external contributors) or create a branch directly (maintainers).
3. **Branch from `develop`** with the naming convention above. Example: `feature/42-add-spanish-bootstrap`.
4. **Commit** using [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, …). Describe the *why*, not the *what*.
5. **Open a PR targeting `develop`** (not `main`). Fill the PR template, link the issue.
6. CI must pass and at least one approval is required before merge.
7. Merges into `develop` use **squash merge** (one clean commit per PR).
8. The maintainer periodically merges `develop` → `main` and tags a new release (`vX.Y.Z`) following [semver](https://semver.org/).

## How to propose a change

1. Open an issue first if the change is non-trivial. Describe what's broken or missing and why.
2. For a fix : PR directly against `develop`. Keep it scoped — one fix per PR.
3. For a feature : align in the issue thread first, then PR against `develop`.

## Testing changes to `BOOTSTRAP.md`

The most consequential file is `BOOTSTRAP.md`. To test a change:

1. Clone the template into a scratch directory: `gh repo clone tetra-plg/boiling-brain ~/scratch-vault`.
2. Open Claude Code in that directory.
3. Run `Lis BOOTSTRAP.md et exécute le prompt.` (FR) or `Read BOOTSTRAP.md and execute the prompt.` (EN).
4. Walk through the interview and verify the scaffolded output.
5. Delete the scratch vault when done.

## Conventions

- All in-prompt user-facing text in `BOOTSTRAP.md` is **French**. Translations (English, Spanish, etc.) would be a separate effort — not blocking for v1.
- `*.tpl` files use `{{placeholder}}` syntax. New placeholders must be documented in `PLACEHOLDERS.md`.
- No emojis in code or wiki files unless requested. Status indicators in BOOTSTRAP.md (✅, ⭐, etc.) are an exception.
- Commit messages : describe the *why*, not the *what*. Reference the relevant phase if applicable (`phase 5c: <fix>`).

## Code of Conduct

By participating, you agree to abide by the project [Code of Conduct](CODE_OF_CONDUCT.md).

## Security

If you discover a security issue, please follow the [security policy](SECURITY.md) — do not open a public issue.

## License

By contributing, you agree your contributions are released under the same MIT license as the project.
