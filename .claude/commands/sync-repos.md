---
description: Synchronise la doc des repos GitHub déclarés dans tracked-repos.config.json vers raw/ en snapshots par SHA, puis enchaîne /ingest
argument-hint: [noms-de-sources — vide = multiSelect interactif]
---

Run the SYNC-REPOS workflow from CLAUDE.md on: $ARGUMENTS

Le manifest `tracked-repos.config.json` (à la racine du vault) liste les repos à suivre (champ `sources[]` : `name`, `repo`, `branch`, `dest`, `paths`, `exclude_paths`). Chaque source déclare son `dest` libre — typiquement `raw/tracked-repos/<slug>`, mais rien n'empêche un layout différent.

**Principe immutable.** Chaque sync crée un **nouveau snapshot** sous `<dest>/<shortsha>/` (shortsha = 7 premiers chars du SHA du HEAD de `branch`). Si le snapshot existe déjà → skip. Aucun fichier existant dans `raw/` n'est jamais modifié.

### 1. Pré-requis

1. `gh auth status` — si pas authentifié : stopper, demander à l'utilisateur de lancer `gh auth login`.
2. `tracked-repos.config.json` existe — sinon : stopper et signaler.
3. `jq` installé — sinon : suggérer `brew install jq`.

### 2. Résolution de la cible

Depuis le **main context**, déterminer les sources à sync en fonction de `$ARGUMENTS` :

- **Un ou plusieurs noms** → sync ces sources.
- **Vide** → lire `tracked-repos.config.json`, afficher pour chaque source : `name · repo · dernier shortsha snapshotté dans dest/` (ou `(jamais sync)`), puis `AskUserQuestion` en **multiSelect** avec :
  - une option par source (libellé : `<name>`)
  - `all` (tout)

Évite un « tout sync » involontaire (N repos = N clones).

### 3. Invocation du script

Appeler `scripts/sync-repos.sh` avec la liste finale de noms :
```bash
scripts/sync-repos.sh <name1> <name2>
```

Le script écrit sur stdout des lignes de trois formes :
- `CREATED <path-relatif-au-vault>` — un nouveau snapshot.
- `SKIPPED <name> (sha <shortsha> already snapshotted)` — pas de merge amont depuis le dernier sync.
- `ERROR <name> <message>` — échec (clone, paths manquants, repo inaccessible).

### 4. Chaînage sur /ingest

Pour chaque ligne `CREATED <path>` : enchaîner `/ingest <path>`. Le dispatch d'`/ingest` proposera l'agent expert adapté à la doc des repos suivis.

Si plusieurs snapshots créés dans le même run : les ingérer **séquentiellement** (un par un), pas en parallèle — l'agent expert doit pouvoir cross-référencer chaque snapshot avec les pages wiki déjà présentes (y compris celles créées dans le même run).

### 5. Rapport final

```
N snapshots créés · K sources inchangées · E erreurs

Créés :
- <dest>/<shortsha>  →  ingéré via <agent>-expert
- ...

Inchangés :
- <name> (sha <shortsha> déjà snapshotté)

Erreurs :
- <name> : échec clone
```

Ajouter une entrée dans `wiki/log.md` :
```
## [YYYY-MM-DD] sync-repos | N snapshots créés
<liste des snapshots créés et ingérés>
```

### Notes

- Aucune limite de taille : si un `paths[]` listé est volumineux, le snapshot sera volumineux. Ajuster `paths` dans le manifest au besoin.
- Pour un nouveau repo : éditer le manifest, relancer `/sync-repos <nouveau-name>`.
- Un repo privé nécessite que `gh` soit authentifié avec un compte ayant accès.
