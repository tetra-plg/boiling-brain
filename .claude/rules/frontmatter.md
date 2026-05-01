---
description: Règles de frontmatter pour les pages du wiki (sources, concepts, syntheses, decisions)
paths:
  - "wiki/sources/**"
  - "wiki/concepts/**"
  - "wiki/syntheses/**"
  - "wiki/decisions/**"
  - "wiki/entities/**"
  - "wiki/cheatsheets/**"
  - "wiki/diagrams/**"
  - "wiki/domains/**"
---

# Frontmatter — règles dures

Toute page du wiki commence par un frontmatter YAML. Ces règles sont **non-négociables** : un agent expert qui les viole produit une page invalide.

## Champs obligatoires

```yaml
---
type: source | entity | concept | synthesis | decision | domain | cheatsheet | diagram | overview
domains: [<domain1>, <domain2>, ...]
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

- `type` : exactement une des valeurs ci-dessus, en minuscules.
- `domains` : tableau YAML, slugs de domaines déclarés dans `wiki/index.md`. Au moins un.
- `created` / `updated` : format ISO `YYYY-MM-DD`. `updated` reflète la dernière modification matérielle de la page.

## Champs spécifiques aux pages `type: source`

```yaml
source_path: "raw/<dossier>/<fichier>.md"   # obligatoire, non-vide, chemin réel existant
source_sha256: "<hash hex 64 caractères>"   # obligatoire, non-vide
ingested: YYYY-MM-DD                        # date d'ingestion par l'agent
covered_paths:                              # optionnel : si la page synthétise plusieurs raw
  - "raw/<dossier>/<fichier1>.md"
  - "raw/<dossier>/<fichier2>.md"
```

### Règle dure `source_sha256`

`source_sha256` doit **toujours** être calculé via `shasum -a 256 <file>` sur le fichier réel au moment de l'ingestion. Jamais un placeholder textuel (`see-raw-file`, le slug, un faux hex, `TODO`...). Cette règle s'applique sans exception à tous les agents experts.

Commande de calcul standard :

```bash
shasum -a 256 raw/<dossier>/<fichier>.md | awk '{print $1}'
```

Si le fichier ne peut pas être calculé (chemin invalide, erreur d'accès), l'ingestion échoue — pas de fallback silencieux.

## Champs `summary_l0` et `summary_l1` (tiered loading)

Obligatoires pour `domains/`, `cheatsheets/`, `concepts/`, `syntheses/`. Recommandés pour `sources/`, `entities/`.

```yaml
summary_l0: "≤140 chars, télégraphique, scannable"
summary_l1: |
  2-5 phrases, ~50-150 mots, description structurée.
  Couvre les claims principaux et l'angle.
```

Ces champs alimentent le **tiered loading** des oracles : un agent peut scanner un domaine entier via les `summary_l0` (TOC L0), puis descendre en `summary_l1` (preview L1) ou body complet (L2) seulement si pertinent.

## Champ `sources` (cross-référence)

Pour les pages non-`source` qui s'appuient sur des sources :

```yaml
sources:
  - "[[sources/2026-XX-XX-slug]]"
  - "[[sources/2026-YY-YY-autre-slug]]"
```

Wikilinks Obsidian, pas de chemin nu.
