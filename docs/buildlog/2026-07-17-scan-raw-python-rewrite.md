# scan-raw-python-rewrite (build log) : réécriture Python + améliorations pipeline

- **Date** : 2026-07-17
- **Spec** : `docs/superpowers/specs/2026-07-17-scan-raw-python-rewrite-design.md`
- **Plan** : `docs/superpowers/plans/2026-07-17-scan-raw-python-rewrite.md`
- **Objectif** : corriger le timeout de `scan-raw.sh` sur vault mature (#70) en réécrivant le moteur en Python mono-processus, + améliorations additives (JSON, `--force`/`--orphans`/`--pending`, lint d'index, détection composite), parité stdout par défaut octet-pour-octet.
- **Statut** : 🚧 en cours — Task 6/16 livrée. **#70 corrigé** : `scan-raw.sh` est un wrapper mince vers `scan-raw.py`, parité golden via wrapper prouvée. Reste : améliorations additives (flags, lint, composite) + docs + validation réelle.

> Journal vivant : une ligne `## Livré` par tâche squash-mergée dans `fix/70-scan-raw-perf`. La section `## Validation RÉELLE` finale (chiffres sur le vault BoilingBrain réel) est remplie à la Task 15. Aucun chiffre inventé.

## Modèle d'exécution

Norme projet (cf. mémoire `feedback_superpowers_plan_worktree_flow`) : worktree dédié `../llm-wiki-template-wt`, une branche `fix/70-tNN-<slug>` par tâche forkée depuis `fix/70-scan-raw-perf`, commit à chaque step, squash-merge dans la branche du plan (pathspec limité aux fichiers de la tâche pour exclure le `.gitignore` stagé de l'utilisateur), push de la branche du plan, suppression de la branche de tâche.

## Livré

| Tâche | Livrable | Fichier | Notes |
| --- | --- | --- | --- |
| 1 | Baseline de parité golden | `scripts/wiki-maint/scan_raw_fixture.py`, `scripts/wiki-maint/fixtures/scan-raw/default.golden`, `scripts/wiki-maint/test_scan_raw.py` | Fixture déterministe (chemins ASCII, tri stable) ; golden figé depuis le **bash actuel** avant toute réécriture ; `GoldenParityTest` branché sur le wrapper. Squash-merge `dc80977`. |
| 2 | Squelette du moteur | `scripts/wiki-maint/scan-raw.py`, `scripts/wiki-maint/test_scan_raw.py` | Collecte (filtres `.sync-meta.json`/binaires, tri UTF-8 stable), `parse_args` (`--force`/`--orphans`/`--pending`/`--format`), UTF-8 forcé, `--help`. Chargement in-process du moteur (importlib). `CollectFilesTest` 4/4. |
| 3 | Normalisation + index primaire | `scripts/wiki-maint/scan-raw.py`, `scripts/wiki-maint/test_scan_raw.py` | `normalize_path` (NFC + U+2019), parsing frontmatter **strict** (bloc `---` uniquement), `Index` + `build_index` (source_path scalaire/liste, covered_paths, `sources:` legacy, sha 1er source_path, dossiers implicites ≥4 slashes, map videos-meta→transcript, matériel lint/composite/orphans). `NormalizeTest`+`FrontmatterTest`+`BuildIndexTest` 7/7. |
| 4 | Arbitrage + sortie texte + `--force` | `scripts/wiki-maint/scan-raw.py`, `scripts/wiki-maint/test_scan_raw.py` | `Verdict`, `classify` (cascade exact→dir→dir-implicite→transcript→NEW), `format_text_line` (formats octet-exacts), `run` (signature `idx=None` posée dès maintenant pour la Task 10). Moteur produit le stdout complet ; **parité fonctionnelle prouvée** : moteur direct == golden octet-pour-octet. `ClassifyTest`+`StrictFrontmatterDivergenceTest` 6/6, suite 23. |
| 5 | Checkpoint (sans artefact) | — | Suite moteur complète verte avant le flip du wrapper. Pas de commit (checkpoint plan). |
| 6 | **Flip du wrapper → #70 corrigé** | `scripts/wiki-maint/scan-raw.sh`, `scripts/wiki-maint/test_scan_raw.py` | `scan-raw.sh` 276→50 lignes : bloc `PYTHON_BIN` (#64) préservé verbatim + `export VAULT_ROOT` + `exec …/scan-raw.py "$@"`. `_make_vault` copie aussi le moteur. `GoldenParityTest` **via le wrapper** ✅. Suite 23 en ~1,0 s (vs ~3,4 s quand les hermétiques lançaient le bash complet) — moteur nettement plus rapide. |

## Validation RÉELLE

Tests réellement exécutés (worktree, Python 3.14.4) :

- `GoldenParityTest.test_default_output_matches_frozen_golden` ✅ (le wrapper full-bash reproduit son propre golden — harnais prouvé correct, 1 test, ~2,3 s).
- `PythonResolutionTest` (suite hermétique existante) ✅ 5/5 — inchangée.

_(Validation perf réelle + run différentiel bash-vs-Python sur le vault BoilingBrain : Task 15.)_

## Gotchas de la passe

- **Snippet « eyeball » du plan (Task 4) imparfait** : `python3 scan-raw.py` avec `cwd` sur le vault fixture échoue (le moteur n'y est pas → stdout vide, faux négatif de parité). Corrigé en pointant le chemin absolu du moteur + `VAULT_ROOT`. Sans impact sur le code : la vraie garde de parité est `GoldenParityTest` via le wrapper (Task 6).
- **Seuil dir-implicite mal compris dans la fixture** : le cas « shallow » conçu comme profondeur 3 (non-matché) était en réalité à **4 slashes** dans son `idir` (`raw/shallow/a/b/` → `raw/ shallow/ a/ b/` = 4 ≥ 4), donc matché comme dossier implicite → le sibling ressortait `SKIP` au lieu du `NEW` attendu. Le bash compte les `/` de `${indexed_path%/*}/` et matche si ≥ 4. Corrigé en `raw/shallow/b/` (3 slashes < 4 → non-matché, sibling `NEW`). **Le golden généré depuis le vrai bash a révélé l'erreur avant toute réécriture** — exactement la raison de figer la baseline en premier. Le plan (test unitaire Task 3) a été corrigé en conséquence.

## Décisions / restes

- Mémoïsation / cache d'index : **différé** (pas écarté) — seuil de déclenchement = full scan réel > ~5 s malgré le moteur Python ; design de secours (cache de hashes fail-open) documenté dans la spec §hors-périmètre.
- Promotion `composite-mismatch` → verdict `MODIFIED` : différée post-convergence du vault.
- Reste à livrer : Tasks 2-16 (moteur, wrapper, flags, guard, docs, validation réelle).
