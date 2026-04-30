---
type: decision
domains: [meta]
created: 2026-04-19
updated: 2026-04-30
sources: []
summary_l0: "Snapshots immuables par SHA pour doc évolutive de repos GitHub — fidèle au principe Karpathy"
summary_l1: |
  Le problème : on veut faire entrer dans le wiki la doc de repos GitHub qui change à chaque merge, mais `raw/` doit rester immutable. Solution : `/sync-factory-docs` crée des snapshots immuables nommés par SHA court du HEAD de chaque repo, via un manifest `factory-docs.config.json`. Chaque merge génère un nouveau snapshot sans écraser les précédents ; l'idempotence par hash et l'historique des versions restent exploitables. Pattern réutilisable pour tout repo dont la doc évolue (frameworks, specs vivantes, projets en cours).
---
# Faire entrer de la doc évolutive dans un `raw/` immutable

## Le problème

Le LLM Wiki repose sur un principe Karpathy fort : **`raw/` est immutable**. Une source = un snapshot hashé, jamais modifié, référencé par `wiki/sources/` via `source_path` + `source_sha256`. L'idempotence d'`/ingest` en dépend, et la couche wiki est toujours dérivable depuis `raw/`.

Or on veut souvent rendre interrogeables des contenus **vivants** :
- Doc technique de composants ou frameworks qu'on suit (release notes, README, docs/).
- Specs de standards qui évoluent (MCP, Agent Skills, etc.).
- Doc projet de repos en cours de développement.

Chaque merge sur `main` côté GitHub = nouvelle version de la doc. Reproduire cela dans `raw/` en écrasant casserait le principe fondateur.

## Les options écartées

**Option A — `raw/` live, écrasé à chaque sync.**
Simple, mais perd l'historique et viole l'immutabilité. Les contradictions entre versions ne deviennent pas exploitables — elles disparaissent.

**Option B — Doc live hors-`raw/` (ex: `docs-live/`), seul les releases snapshotées dans `raw/`.**
Deux régimes coexistent, complexité accrue pour `/ingest` et `/lint`. Et surtout : ça ouvre une brèche dans la règle « rien de mutable dans le vault ».

**Option C — Snapshot à chaque sync sur date.**
`raw/factory-docs/<composant>/2026-04-19/`. Crée un snapshot même si le contenu est identique → pollution. L'unité naturelle n'est pas la date mais l'**événement** (merge sur main).

## La décision retenue

**Snapshot par SHA court pour tout**, via un unique slash command `/sync-factory-docs` piloté par un manifest.

### Mécanique

1. Manifest [`factory-docs.config.json`](../../factory-docs.config.json) à la racine du vault — liste des repos suivis, leur `branch`, `kind` (core|project), `paths` (fichiers/dossiers de doc à extraire), `dest` (chemin cible dans `raw/`).
2. `scripts/sync-factory-docs.sh` : pour chaque source, `gh api repos/<repo>/commits/<branch>` → SHA du HEAD. Si `raw/<dest>/<shortsha>/` existe → **skip** (la source est identique à un snapshot connu). Sinon `gh repo clone --depth=1`, copie des `paths`, écriture de `.sync-meta.json`, purge du clone dans `cache/factory-repos/`.
3. `.claude/commands/sync-factory-docs.md` : résout `$ARGUMENTS` (noms explicites, `--kind=…`, ou multiSelect interactif si vide), invoque le script, puis enchaîne `/ingest <snapshot>` sur chaque `CREATED`.

### Pourquoi ce dispositif est fidèle à Karpathy

- **Immutabilité préservée, zéro exception.** Chaque snapshot est un nouveau dossier. Les anciens ne sont jamais modifiés ni supprimés.
- **L'événement, pas la date.** Le shortsha est l'unité naturelle : un merge = un snapshot, pas de pollution si rien n'a bougé.
- **L'historique devient du signal.** Les contradictions entre versions successives (v1 disait X, v2 dit Y) sont capturables par `/lint` — exactement ce que Karpathy appelle *knowledge compilation*.
- **L'idempotence par hash continue de fonctionner.** `/ingest` détecte via `source_sha256` que la doc d'un snapshot est identique à celle d'un snapshot précédent et skip.

### Interface utilisateur

| Invocation | Effet |
|---|---|
| `/sync-factory-docs` | multiSelect interactif (évite le gros run involontaire sur N repos) |
| `/sync-factory-docs <name1> <name2>` | ces sources seulement |
| `/sync-factory-docs --kind=core` | tous les composants core |
| `/sync-factory-docs --kind=project` | tous les projets |

## Ce que ça débloque

- **Travailler avec l'état courant des composants.** Quand un repo évolue, on peut ré-sync, le wiki reflète la nouvelle version, les anciennes restent consultables.
- **Requêter l'évolution.** `/query comment a évolué la doc du composant X entre les deux dernières versions ?` devient possible naturellement (deux snapshots, deux pages sources, cross-réf).
- **Cadre générique.** Le même pattern s'applique à tout repo externe (doc d'un framework qu'on veut suivre, spec d'un standard évolutif).

## Questions ouvertes

- **Volume long-terme.** Si N repos mergent chacun M fois par an, c'est N×M snapshots/an. À surveiller — un `/lint` futur pourrait suggérer de consolider les snapshots anciens d'un même composant s'ils ne sont plus référencés par aucune page vivante du wiki.
- **Granularité des `paths`.** Pour l'instant défaut `["README.md", "docs/", "CHANGELOG.md"]`. Si un repo a sa doc ailleurs (ex: `docs-site/content/`), ajuster per-source dans le manifest.

## Fichiers livrés

- [`factory-docs.config.json`](../../factory-docs.config.json) — manifest (vide par défaut au bootstrap, à peupler au fur et à mesure).
- [`scripts/sync-factory-docs.sh`](../../scripts/sync-factory-docs.sh) — orchestration bash (gh + jq).
- [`.claude/commands/sync-factory-docs.md`](../../.claude/commands/sync-factory-docs.md) — slash command.
- [`CLAUDE.md`](../../CLAUDE.md) — documentation du workflow (section SYNC-FACTORY-DOCS).
