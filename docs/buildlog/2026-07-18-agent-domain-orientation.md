# agent-domain-orientation (build log) : orientation domaine self-service des agents experts

- **Date** : 2026-07-18
- **Spec** : `docs/superpowers/specs/2026-07-17-agent-domain-orientation-design.md` (local, gitignoré)
- **Plan** : `docs/superpowers/plans/2026-07-17-agent-domain-orientation.md` (local, gitignoré)
- **Objectif** : donner à chaque agent domain-expert une connaissance self-service de son domaine via le tiered loading déjà livré (`wiki-cli`), et remplacer la liste de titres injectée au spawn par un snapshot `scan-domain`. Cibler autant l'ingestion que l'usage général de l'agent.
- **Statut** : livré — PR #72 squash-mergée dans `develop` (commit `7f04391`), issue #71 fermée.

## Livré

| Livrable                   | Fichier                                                                  | Notes                                                                                                                                                                                   |
| -------------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Wrapper portable CLI       | `scripts/mcp/wiki-cli.sh`                                                | Résolution `python3`/`python` calquée sur `scan-raw.sh` (stub Store Windows). String d'invocation unique partagée par 4 consommateurs.                                                  |
| Section Domain orientation | `.claude/agents/domain-expert.md.tpl`                                    | `scan-domain → drill-down ciblé → preview/read`, wikilinks vérifiés, idempotence step 0 via `scan-sources`, fallback `Glob`/`Grep`. Bullet « current wiki context » réécrit (snapshot). |
| Snapshot au spawn          | `.claude/commands/ingest.md`                                             | Étape 3 : le main injecte `scan-domain <d>` par spawn ; plus de construction de liste de titres.                                                                                        |
| Guard headless durci       | `scripts/mcp/ingest-headless-guard.sh` + `scripts/mcp/test_wiki_core.py` | Allowlist du sous-ensemble charset-safe (`scan-domain`, `scan-<type>` sans `--query`, `list-domains`, `preview`, `read`) ; `--query`/`search` refusés. +10 tests (5 allow / 5 deny).    |
| Migration vaults existants | `scripts/migrations/v1.1.2-domain-orientation.md`                        | Interactive, idempotente. Insère la section (rendue **dans la langue de l'agent**) + ajoute l'allowlist au `settings.json`. Ancre de placement **par rôle** (langue-agnostique).        |
| Release                    | `.claude/template-version`, `CHANGELOG.md`, `BOOTSTRAP.md`               | Bump 1.1.2 + entrée CHANGELOG + note allowlist bootstrap.                                                                                                                               |

## Validation RÉELLE

- **Suite mcp** (branche de plan) : `python3 -m unittest test_wiki_core test_wiki_cli` → **Ran 109 tests — OK (skipped=25)** ✅ (skips = tests fastmcp-gated, attendus).
- **Guard** : classe seule 45 tests OK ✅ ; les 5 cas hostiles (`--query "…"`, `search "…"`, `; rm -rf /`, `$(whoami)`, `..`) refusés par construction (exit 2) ✅.
- **Parité wrapper ↔ CLI** : `diff <(wiki-cli.sh scan-domain ia) <(wiki-cli.py scan-domain ia)` vide ✅ ; chemin d'échec `PYTHON_BIN=/nonexistent` → exit 1 + message ✅.
- **Smoke `/ingest` live** (worktree jetable de BoilingBrain, agent ia-expert FR réel, sans snapshot fourni) :
  - auto-orientation : `scan-domain ia` lancé de lui-même ✅
  - idempotence step 0 : `scan-sources ia --query "smoke-ado"` (pas de devinette de chemin) ✅
  - drill-down ciblés (`scan-concepts`, `scan-decisions`, `preview`) avant décision ✅
  - a trouvé `model-context-protocol` (120 backlinks) + `progressive-disclosure-agents` → **liés/enrichis, pas dupliqués** ✅
  - 7 `[[wikilinks]]` écrits → 7 cibles réelles existantes ✅
  - enrichissement additif (+1 ligne), `source_sha256` correct, `raw/` intact ✅
  - dégradation propre : `scan-raw.sh` timeout 120s (problème connu de fix/70, orthogonal) → fallback ciblé, comme prévu par le prompt ✅

## Gotchas de la passe

- **`docs/superpowers/` gitignoré** : spec et plan sont des artefacts locaux, jamais commités (le premier `git commit` de la spec fut un no-op silencieux). Découvert en cours ; les livrables réels sont les seuls commités.
- **Ancre de migration EN-only** : la 1re version cherchait `## What you produce`, absent d'un agent FR (« Ce que tu produis ») → fallback dégradé. **Corrigé** (T07) : détection par rôle (section qui énumère `wiki/sources`/`concepts`/`entities`) + rendu de la section dans la langue de l'agent, calqué sur `v1.0.3-vault-language.md`. Validé contre le vrai agent FR de BB.
- **Papercut format de chemin** (non corrigé, noté) : la sortie `scan` affiche `concepts/x` mais `preview`/`read` attendent `wiki/concepts/x.md` ; l'agent a heurté « Page introuvable » 2× puis s'est auto-corrigé. Refinement futur : soit un mot dans la section, soit aligner le format de sortie — à faire dans les DEUX fichiers en lockstep (`.tpl` + texte de la migration).
- **Merge bloqué** : `REVIEW_REQUIRED` (impossible d'approuver sa propre PR) → squash-merge admin sur autorisation explicite.

## Décisions / restes

- **Approche retenue** : orientation autonome via CLI + snapshot injecté. **Écartées** : (C) outils MCP dans le frontmatter des sous-agents — parité identique via CLI sans dépendre d'un serveur MCP connecté (fragile en headless/CI) ; (D) tous les `summary_l0` dans le system prompt — ~14k tokens/spawn sur `ia`, état périmé intra-batch, churn git. Rationale complet en spec §2.
- **Headless drill-down filtré délibérément non allowlisté** : `--query`/`search` portent du texte quoté non charset-anchrable. Le headless obtient snapshot + top-N + preview/read ; il retombe sur `Glob`/`Grep` pour les recherches filtrées. Reste possible : un schéma `--query-file` sûr si le besoin émerge.
- **Hors scope, rendu possible par cette passe** : délégation de `/query` à l'agent expert du domaine.
- **Exécution** : 7 tâches, une branche + squash-merge chacune (T02/T03/T04 parallélisées via un worktree par tâche + subagents). Commits sans attribution IA.
