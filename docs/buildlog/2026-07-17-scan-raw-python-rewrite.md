# scan-raw-python-rewrite (build log) : réécriture Python + améliorations pipeline

- **Date** : 2026-07-17
- **Spec** : `docs/superpowers/specs/2026-07-17-scan-raw-python-rewrite-design.md`
- **Plan** : `docs/superpowers/plans/2026-07-17-scan-raw-python-rewrite.md`
- **Objectif** : corriger le timeout de `scan-raw.sh` sur vault mature (#70) en réécrivant le moteur en Python mono-processus, + améliorations additives (JSON, `--force`/`--orphans`/`--pending`, lint d'index, détection composite), parité stdout par défaut octet-pour-octet.
- **Statut** : 🚧 en cours — Task 1/16 livrée.

> Journal vivant : une ligne `## Livré` par tâche squash-mergée dans `fix/70-scan-raw-perf`. La section `## Validation RÉELLE` finale (chiffres sur le vault BoilingBrain réel) est remplie à la Task 15. Aucun chiffre inventé.

## Modèle d'exécution

Norme projet (cf. mémoire `feedback_superpowers_plan_worktree_flow`) : worktree dédié `../llm-wiki-template-wt`, une branche `fix/70-tNN-<slug>` par tâche forkée depuis `fix/70-scan-raw-perf`, commit à chaque step, squash-merge dans la branche du plan (pathspec limité aux fichiers de la tâche pour exclure le `.gitignore` stagé de l'utilisateur), push de la branche du plan, suppression de la branche de tâche.

## Livré

| Tâche | Livrable | Fichier | Notes |
| --- | --- | --- | --- |
| 1 | Baseline de parité golden | `scripts/wiki-maint/scan_raw_fixture.py`, `scripts/wiki-maint/fixtures/scan-raw/default.golden`, `scripts/wiki-maint/test_scan_raw.py` | Fixture déterministe (chemins ASCII, tri stable) ; golden figé depuis le **bash actuel** avant toute réécriture ; `GoldenParityTest` branché sur le wrapper. Squash-merge `dc80977`. |

## Validation RÉELLE

Tests réellement exécutés (worktree, Python 3.14.4) :

- `GoldenParityTest.test_default_output_matches_frozen_golden` ✅ (le wrapper full-bash reproduit son propre golden — harnais prouvé correct, 1 test, ~2,3 s).
- `PythonResolutionTest` (suite hermétique existante) ✅ 5/5 — inchangée.

_(Validation perf réelle + run différentiel bash-vs-Python sur le vault BoilingBrain : Task 15.)_

## Gotchas de la passe

- **Seuil dir-implicite mal compris dans la fixture** : le cas « shallow » conçu comme profondeur 3 (non-matché) était en réalité à **4 slashes** dans son `idir` (`raw/shallow/a/b/` → `raw/ shallow/ a/ b/` = 4 ≥ 4), donc matché comme dossier implicite → le sibling ressortait `SKIP` au lieu du `NEW` attendu. Le bash compte les `/` de `${indexed_path%/*}/` et matche si ≥ 4. Corrigé en `raw/shallow/b/` (3 slashes < 4 → non-matché, sibling `NEW`). **Le golden généré depuis le vrai bash a révélé l'erreur avant toute réécriture** — exactement la raison de figer la baseline en premier. Le plan (test unitaire Task 3) a été corrigé en conséquence.

## Décisions / restes

- Mémoïsation / cache d'index : **différé** (pas écarté) — seuil de déclenchement = full scan réel > ~5 s malgré le moteur Python ; design de secours (cache de hashes fail-open) documenté dans la spec §hors-périmètre.
- Promotion `composite-mismatch` → verdict `MODIFIED` : différée post-convergence du vault.
- Reste à livrer : Tasks 2-16 (moteur, wrapper, flags, guard, docs, validation réelle).
