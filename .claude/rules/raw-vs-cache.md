---
description: Principe d'immutabilité de raw/ et rôle transitoire de cache/
paths:
  - "raw/**"
  - "cache/**"
---

# raw/ vs cache/ — principe d'immutabilité

## raw/ — strictement immutable

`raw/` contient les **sources brutes** que le wiki référence. Toute page `wiki/sources/<slug>.md` pointe vers un fichier de `raw/` via son frontmatter `source_path`.

Règles dures :

- **Ne jamais modifier un fichier existant dans `raw/`.** Si une source évolue (ex: doc mise à jour), créer un **nouveau fichier** avec un nouveau SHA, jamais réécrire l'ancien.
- **Ne jamais déplacer un fichier de `raw/`** une fois qu'il est référencé par une page wiki : tu casserais le `source_path` et `source_sha256`.
- **Snapshots par SHA** pour les sources évolutives (cf. `wiki/decisions/tracked-repos-immutable-snapshots.md`) : chaque version → un nouveau dossier dédié, jamais d'écrasement.
- **Pas d'agent expert n'écrit dans `raw/`.** Les agents lisent `raw/` et écrivent dans `wiki/`. La seule exception est la promotion de frames (`cache/frames/` → `raw/frames/`) gérée par `/ingest-video`.

## cache/ — transitoire

`cache/` contient les artefacts de traitement **jamais référencés par le wiki**. Purgeable à tout moment sans perte d'information.

Règles dures :

- **Ne jamais référencer `cache/` depuis une page du wiki.** Le contenu peut disparaître. Si un artefact de `cache/` doit persister, il est **promu** vers `raw/` (ex: une frame retenue pour illustration).
- **Vidéos et audios** transitent par `cache/videos/`, `cache/audio/` le temps de la transcription, puis sont supprimés ou archivés hors-vault.
- **Frames candidates** vivent dans `cache/frames/`. Seules les frames **réellement utilisées** par une page wiki sont promues vers `raw/frames/<source-slug>-<descriptif>.png`.

## Conséquences pratiques

- Un agent qui veut citer un visuel → s'assurer qu'il est dans `raw/frames/`, sinon demander la promotion.
- Une vérification de cohérence du wiki (`/lint`) doit signaler toute page qui référence un chemin `cache/` comme erreur.
- `raw/` est **versionnable git** sans crainte (immutable par construction). `cache/` peut être `.gitignored` si trop volumineux.

## Cross-refs

- `wiki/decisions/tracked-repos-immutable-snapshots.md` — pattern de snapshots par SHA pour les sources externes évolutives.
- `wiki/decisions/extraction-frames-induction-runbook.md` — workflow de promotion `cache/frames/` → `raw/frames/`.
