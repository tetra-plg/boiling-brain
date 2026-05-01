---
description: Cherry-pick improvements from the upstream template into this vault
---

# /update-vault

Met à jour ce vault depuis le template `tetra-plg/boiling-brain` en amont.

Utilise ce workflow pour récupérer les nouveaux scripts, slash-commands, ou décisions d'architecture publiés dans le template après ton bootstrap.

## Étapes

### 1. Configure le remote template-upstream (une seule fois)

```bash
git remote add template-upstream https://github.com/tetra-plg/boiling-brain.git 2>/dev/null \
  && echo "remote template-upstream ajouté" \
  || echo "remote template-upstream déjà configuré"
git fetch template-upstream --tags
```

### 2. Résoudre le baseline

```bash
BOOTSTRAP_SHA=$(cat .template-bootstrap-sha 2>/dev/null || echo "")

if [ -z "$BOOTSTRAP_SHA" ]; then
  # Rétrocompat v1.0.0 : utiliser le tag v1.0.0 comme baseline
  BOOTSTRAP_SHA=$(git rev-list -n 1 v1.0.0 2>/dev/null || echo "")
fi

if [ -z "$BOOTSTRAP_SHA" ]; then
  echo "BASELINE_MISSING"
else
  echo "BASELINE $BOOTSTRAP_SHA"
  git log ${BOOTSTRAP_SHA}..template-upstream/main --oneline
fi
```

- Si `BASELINE_MISSING` : informer l'utilisateur qu'aucun baseline n'a pu être trouvé et proposer de créer `.template-bootstrap-sha` manuellement (voir Notes).
- Si la liste est vide : « Ton vault est à jour. »
- Sinon : présenter la liste des commits disponibles.

### 3. Identifier les fichiers modifiés

Pour chaque commit listé, identifier les fichiers changés **qui existent dans le vault** :

```bash
git diff --name-only ${BOOTSTRAP_SHA} template-upstream/main \
  | grep -v '\.tpl$' \
  | grep -v '^BOOTSTRAP\.md$' \
  | grep -v '^PLACEHOLDERS\.md$' \
  | grep -v '^CONTRIBUTING\.md$' \
  | while read f; do [ -e "$f" ] && echo "$f"; done
```

Présenter cette liste à l'utilisateur via `AskUserQuestion` (multiSelect) : quels fichiers veut-il mettre à jour ?

### 4. Appliquer fichier par fichier

Pour chaque fichier sélectionné :

```bash
git show template-upstream/main:<fichier> > <fichier>
```

> **Pourquoi `git show` plutôt que `cherry-pick` ?**
> Le bootstrap réinitialise l'historique git (`rm -rf .git/ && git init`). Le vault n'a donc aucun ancêtre commun avec le template — `cherry-pick` tenterait de rejouer des diffs sur un ancêtre inexistant et échouerait systématiquement. `git show` copie directement le contenu cible, sans dépendance à l'historique.

Après application de chaque fichier, afficher un diff rapide :

```bash
git diff <fichier>
```

### 5. Commit

```bash
git add <fichiers mis à jour>
git commit -m "chore: update-vault depuis template-upstream ($(date +%Y-%m-%d))"
```

## Notes

**Fichiers jamais mis à jour (consommés au bootstrap) :**
`*.tpl`, `BOOTSTRAP.md`, `PLACEHOLDERS.md`, `CONTRIBUTING.md`.
Ces fichiers ont été utilisés pour générer ton vault et n'existent plus (ou ont été déplacés). Ils sont exclus automatiquement.

**Fichiers propres à ton instance (jamais dans le template) :**
Tes agents (`.claude/agents/<domain>-expert.md`), tes hubs (`wiki/domains/*.md`), ton `CLAUDE.md`, `wiki/overview.md`, etc. ont des noms distincts des fichiers template — ils ne seront jamais écrasés.

**Baseline manquant (vault pré-v1.0.1) :**
Si ni `.template-bootstrap-sha` ni le tag `v1.0.0` ne sont trouvés, crée le fichier manuellement :
```bash
git fetch template-upstream --tags
git rev-list -n 1 v1.0.0 > .template-bootstrap-sha
git add .template-bootstrap-sha
git commit -m "fix: add template bootstrap sha (retrocompat)"
```
