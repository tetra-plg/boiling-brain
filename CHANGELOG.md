# Changelog

All notable changes to this template are documented here. Format inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Versions are milestones, not strict semver. Breaking changes to `BOOTSTRAP.md` or `*.tpl` are flagged in the release notes.

---

## [Unreleased]

### Fixed

- **`scripts/scan-raw.sh` : 3 bugs de parsing causant des faux `NEW`** ([#3](https://github.com/tetra-plg/boiling-brain/issues/3)).
  - **Bug 1 (apostrophes mangées)** : `tr -d '"'"'` aux lignes 79, 106, 126 supprimait à la fois les guillemets YAML et les apostrophes des chemins. Tout `source_path` contenant une apostrophe (ex: `2026-01-30-claude-code-obsidian-cpr.md` qui mentionnait `BotFather to 'Hello'`) était mal indexé. Remplacé par `sed 's/^"//; s/"$//'` qui ne touche qu'aux guillemets en début/fin de chaîne.
  - **Bug 2 (parenthèses cassent les clés d'array assoc bash)** : un `source_path` ou `covered_paths` contenant `()` ou d'autres caractères spéciaux shell (`*`, `[`, `?`) cassait l'indexation. Neutralisé par une fonction `_safe_key` qui encode les clés via `printf '%q'` à l'écriture **et** au lookup, dans `path_to_slug`, `dir_to_slug` et `meta_to_slug`. Élimine toute la classe de bugs de quoting bash sans dépendance externe.
  - **Bug 3 (espaces multiples)** : couvert par le même `printf '%q'` — les espaces sont maintenant préservés exactement.
  - Tableau parallèle `indexed_paths` ajouté pour permettre l'itération sur les paths originaux (les clés encodées de `path_to_slug` ne sont pas réversibles).

### Added

- **`scripts/test-scan-raw.sh`** : fixture de test reproduisant les 3 cas (apostrophe, parenthèses, espaces multiples) + un cas combiné (apostrophe + parenthèses). Asserte que tous reportent `SKIP` au scan. Exit code 1 si régression.

### Removed

- **`RELEASE_NOTES.md`** : fichier supprimé. Il dupliquait le `CHANGELOG.md` et le body des releases GitHub, ce qui créait du drift à chaque release. La source unique pour les notes de release est désormais `CHANGELOG.md`. Le body GitHub est rédigé directement via `gh release create --notes-file <(extrait du CHANGELOG)` ou édité depuis l'interface.

## [v1.0.1] — hotfix

### Fixed

- **`/update-vault` inutilisable après bootstrap** : le bootstrap réinitialise l'historique git (`rm -rf .git/ && git init`), laissant le vault sans ancêtre commun avec le template. `git log HEAD..template-upstream/main` retournait alors tout l'historique du template, et `git cherry-pick` échouait sur les fichiers `.tpl` consommés au bootstrap.

- **`BOOTSTRAP.md` section 5.10** : enregistre désormais le SHA du template dans `.template-bootstrap-sha` avant de supprimer le `.git/`. Ce fichier sert de baseline pour les futures mises à jour via `/update-vault`.

- **`/update-vault`** : remplace `cherry-pick` par une approche fichier par fichier (`git show template-upstream/main:<fichier> > <fichier>`), indépendante de l'historique git. Exclut automatiquement les fichiers consommés au bootstrap (`*.tpl`, `BOOTSTRAP.md`, `PLACEHOLDERS.md`, etc.).

### Changed

- **`BOOTSTRAP.md` language-adaptive** : le bootstrap n'est plus hardcodé en français. Détection automatique de la langue via les premiers messages utilisateur, génération de tous les fichiers (`CLAUDE.md`, `wiki/index.md`, `wiki/log.md`, agents, hubs…) dans la langue détectée.

### Removed

- **`wiki/decisions/tiered-loading-wiki.md`** : la décision a été remplacée par l'implémentation directe dans `query.md` et les frontmatters `summary_l0` / `summary_l1`. La décision n'avait plus lieu d'exister en tant que document séparé.

### Documentation

- **README — section Prerequisites** : Claude Code, Obsidian (avec lien vers la graph view), gh CLI listés explicitement.
- **README — FAQ Web Clipper** : workflow Obsidian Web Clipper → `raw/clippings/` → `/ingest` documenté.
- **README — usage guidelines** : précisions sur la manière dont le repo est destiné à être utilisé (template, pas projet à cloner).

### Migration depuis v1.0.0

**Option A — automatique (recommandée) :**

```bash
git remote add template-upstream https://github.com/tetra-plg/boiling-brain.git 2>/dev/null; true
git fetch template-upstream --tags
git show template-upstream/main:.claude/commands/update-vault.md \
  > .claude/commands/update-vault.md
git add .claude/commands/update-vault.md
git commit -m "fix: update-vault retrocompat v1.0.0"
```

Puis lance `/update-vault` — le fallback détecte l'absence de `.template-bootstrap-sha` et utilise le tag `v1.0.0` comme baseline automatiquement.

**Option B — manuelle :**

```bash
git fetch template-upstream --tags
git rev-list -n 1 v1.0.0 > .template-bootstrap-sha
git add .template-bootstrap-sha
git commit -m "fix: add template bootstrap sha (retrocompat v1.0.0)"
```

## [v1.0.0] — 2026-04-30 (first public release)

### Repository

- Renamed from `tetra-plg/llm-wiki-template` to `tetra-plg/boiling-brain` and made public.
- All references in `BOOTSTRAP.md`, `README.md`, `CONTRIBUTING.md`, and `/update-vault` updated.
- All examples in `BOOTSTRAP.md` anonymized (Maria Dupont / Carlos Silva / Acme Corp / `data-science, ml-ops, devops, leadership, ecriture`).

### Added

- README section "How does this differ from Karpathy's LLM Wiki?" — comparative table covering source-of-truth, agent topology, idempotence, multimodal, queries, external code, self-improvement, decisions.
- `RELEASE_NOTES.md` — body for `gh release create` plus maintainer instructions.

### Bundled from prior phases (now first-shipped publicly)

Everything from the v0.2.0 phase below is part of v1.0.0. Listed for clarity.

## [v0.2.0] — 2026-04-30 (Phase 5c — feedback réel, internal)

### Added

- `raw/` directory structure pre-created via `.gitkeep` files (`raw/notes/`, `raw/transcripts/`, `raw/videos-meta/`, `raw/frames/`). Visible immediately after clone.
- `BOOTSTRAP.md` Section 5.8 creates conditional `raw/` subdirectories (`pdfs/`, `articles/`, `docs/`) based on Q5 source types, plus the matching `cache/` substructure.
- `BOOTSTRAP.md` Section 4.1 — color picker per domain (4 preset colors with pre-computed RGB values). Section 5.9 generates `.obsidian/graph.json` with the standard filter (`-path:"raw" path:"wiki"`) and `colorGroups` per domain, plus a minimal `.obsidian/app.json`.
- `/update-vault` slash-command — configures `template-upstream` remote, lists available commits, lets the user cherry-pick selectively. Documented in README.
- Exception `!raw/**/.gitkeep` in `.gitignore` so the structure ships with the template while user vaults still ignore `raw/` content.

### Changed

- Q4 (current projects) format replaced. The pipe-separated `slug | description` is gone — users now write natural prose, the LLM extracts the slug automatically.
- README.md — added `/update-vault` to the slash-commands table.

## [v0.1.0] — 2026-04-30 (Phase 4 — initial template)

### Added

- Initial scaffolding for the LLM Wiki bootstrap template.
- `BOOTSTRAP.md` portable prompt (~600 lines, language-adaptive) — 7-question interview, 6-heuristic deduction, per-domain validation, scaffolding, optional GitHub remote, onboarding recap.
- `*.tpl` files with 28 documented placeholders (see `PLACEHOLDERS.md`): `CLAUDE.md.tpl`, `wiki/index.md.tpl`, `wiki/log.md.tpl`, `wiki/overview.md.tpl`, `wiki/radar.md.tpl`, `wiki/domains/domain.md.tpl`, `.claude/agents/domain-expert.md.tpl`, `.claude/agent-memory/domain-memory.md.tpl`, `tracked-repos.config.json.tpl`.
- Generic slash-commands : `/ingest`, `/ingest-video`, `/query`, `/save`, `/lint`, `/evolve-agent`, optional `/sync-repos`.
- Generic scripts : `scan-raw.sh`, `transcribe.sh`, `sample-frames.sh`, `extract-frames.sh`, `diff-frames.py`, `backfill-summaries.py`, `enrich-hub.py`, optional `sync-repos.sh`.
- Architectural decisions in `wiki/decisions/` : `tracked-repos-immutable-snapshots.md`, `extraction-frames-induction-runbook.md`, `ingest-video-modes-a-b-generalisation.md`.
- README.md with usage flow + FAQ.
- MIT LICENSE.
