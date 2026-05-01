# Changelog

All notable changes to this template are documented here. Format inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Versions are milestones, not strict semver. Breaking changes to `BOOTSTRAP.md` or `*.tpl` are flagged in the release notes.

---

## [Unreleased] — v1.0.2

### Added

- **`.claude/rules/`** : trois conventions transverses formalisées (frontmatter, pages-wiki, raw-vs-cache) avec frontmatter `paths:` qui permet l'auto-chargement par Claude Code quand un agent travaille sur un path matchant. Pattern documenté par Anthropic (Boris Cherny, 24 mars 2026). Propagé par `/update-vault` aux vaults existants.
- **`.claude/template-version`** : fichier de versionning explicite du template (format `template-version: X.Y.Z` + `template-sha:` + `last-updated:`). Source de vérité unique pour la machine de migration de `/update-vault`. Créé au bootstrap (BOOTSTRAP 5.10), mis à jour à chaque `/update-vault` réussi.
- **`scripts/migrations/`** : nouveau dossier pour les migrations breaking entre versions du template. Pattern `v<X.Y.Z>-<description>.md` (slash-commands Claude Code interactifs). Premier exemple : `v1.0.2-claude-md-slim.md`. Invoqués par `/update-vault` dans la chaîne entre version locale et cible.

### Changed

- **`CLAUDE.md.tpl` réduit à 111 lignes** (depuis 268, soit −59 %), conformément à la recommandation Anthropic « < 200 lignes » pour préserver l'adhérence aux instructions. Les sections Workflows détaillés (~143 lignes) sont remplacées par une table compacte qui pointe vers `.claude/commands/*.md`. La section Conventions (22 lignes) devient un pointeur vers `.claude/rules/`. Les sections instance-specific (Domaines, Agents experts, Architecture) restent inchangées.
- **`/update-vault` refactoré en machine de migration versionnée** : lit `.claude/template-version` (avec fallback rétrocompat sur `.template-bootstrap-sha` pour v1.0.1 et sur le tag `v1.0.0` pour v1.0.0), compare avec la version cible upstream, propage les fichiers nouveaux (incluant `.claude/rules/**` et `scripts/migrations/**`), exécute la chaîne de migrations applicables, bumpe `.claude/template-version` à la fin si toutes les migrations sont acceptées.
- **`BOOTSTRAP.md` section 5.10** : enrichit `.claude/template-version` avec le SHA et la date du bootstrap (en plus de `.template-bootstrap-sha` historique conservé pour rétrocompat).

### Fixed

- **Trou de propagation des conventions vers les vaults existants** : avant v1.0.2, toute évolution de convention (frontmatter, immutabilité `raw/`, etc.) vivait dans `CLAUDE.md.tpl` consommé au bootstrap, sans mécanisme de propagation. Cas concret : 18 pages du vault de référence ont eu `source_sha256` rempli avec un placeholder par les agents experts (batch 2026-04-29) — non corrigeable sans patch manuel par vault. Avec v1.0.2, la règle « `source_sha256` toujours via `shasum -a 256` » vit dans `.claude/rules/frontmatter.md` et est propagée automatiquement par `/update-vault`.

### Removed

- **`RELEASE_NOTES.md`** : fichier supprimé. Il dupliquait le `CHANGELOG.md` et le body des releases GitHub, ce qui créait du drift à chaque release. La source unique pour les notes de release est désormais `CHANGELOG.md`. Le body GitHub est rédigé directement via `gh release create --notes-file <(extrait du CHANGELOG)` ou édité depuis l'interface.

### Migration depuis v1.0.x

La migration vers v1.0.2 est **gérée par `/update-vault`** :

```bash
# Dans ton vault bootstrappé :
/update-vault
```

`/update-vault` détecte automatiquement la version locale (via `.claude/template-version`, ou via fallback rétrocompat sur `.template-bootstrap-sha` pour v1.0.1, ou tag `v1.0.0` pour v1.0.0), propage les fichiers nouveaux (`.claude/rules/`, `scripts/migrations/`, `.claude/template-version`), puis invoque la migration `v1.0.2-claude-md-slim` qui :

1. Lit le `CLAUDE.md` actuel.
2. Identifie les sections à compacter (Workflows détaillés dupliqués, Conventions verbeuses).
3. **Préserve les customizations utilisateur** (sections ajoutées hors template).
4. Propose un diff via `AskUserQuestion` (3 options : appliquer / éditer manuellement / skip).
5. Si appliqué : commit dédié `chore: migrate CLAUDE.md to v1.0.2 slim structure`.

`CLAUDE.md` n'est jamais réécrit silencieusement — il est user-owned.

Si tu préfères migrer manuellement, lis [scripts/migrations/v1.0.2-claude-md-slim.md](scripts/migrations/v1.0.2-claude-md-slim.md) qui décrit exactement quoi modifier.

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
