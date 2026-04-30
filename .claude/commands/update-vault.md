# /update-vault

Met à jour ce vault depuis le template `tetra-plg/boiling-brain` en amont.

Utilise ce workflow pour récupérer les nouveaux scripts, slash-commands, décisions d'architecture, ou améliorations publiées dans le template après ton bootstrap.

## Étapes

### 1. Configure le remote template-upstream (une seule fois)

```bash
git remote add template-upstream https://github.com/tetra-plg/boiling-brain.git 2>/dev/null \
  && echo "remote template-upstream ajouté" \
  || echo "remote template-upstream déjà configuré"
git fetch template-upstream
```

### 2. Affiche les commits disponibles

```bash
git log HEAD..template-upstream/main --oneline
```

Présente la liste à l'utilisateur. Si vide : « Ton vault est à jour. »

### 3. Demande l'action via AskUserQuestion

```json
{
  "questions": [{
    "question": "Que veux-tu faire avec ces mises à jour ?",
    "header": "Action",
    "multiSelect": false,
    "options": [
      {"label": "Cherry-pick sélectif", "description": "Applique commit par commit. Recommandé : tu choisis ce que tu intègres."},
      {"label": "Voir les diffs sans modifier", "description": "Affiche les changements pour décider ensuite."},
      {"label": "Annuler", "description": "Ne modifie rien."}
    ]
  }]
}
```

### 4. Cherry-pick sélectif

Pour chaque commit sélectionné :

```bash
git cherry-pick <sha>
```

En cas de conflit :
- Affiche le diff (`git diff --stat HEAD`)
- Demande à l'utilisateur de résoudre manuellement puis `git cherry-pick --continue`

### 5. Voir les diffs

```bash
git diff HEAD template-upstream/main -- <fichier>
```

Présente fichier par fichier les changements pertinents (scripts, commandes, décisions).

## Notes

- **Tes personnalisations sont préservées** : les fichiers générés par le bootstrap (agents, hubs, CLAUDE.md, overview.md) ont des noms distincts de ceux du template. Le cherry-pick ne les touche pas.
- **Fichiers les plus susceptibles d'être mis à jour** : `scripts/`, `.claude/commands/`, `wiki/decisions/` (décisions architecturales génériques).
- **Fichiers qui ne te concernent pas** : `BOOTSTRAP.md`, `PLACEHOLDERS.md`, `*.tpl` — ils ont été consommés lors de ton bootstrap et tu n'en as plus besoin.
- **Si un nouveau script ou command est ajouté** sans commit clair, tu peux le copier manuellement :
  ```bash
  git show template-upstream/main:.claude/commands/nouveau-script.md > .claude/commands/nouveau-script.md
  ```
