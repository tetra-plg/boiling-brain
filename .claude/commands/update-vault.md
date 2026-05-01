---
description: Cherry-pick improvements from the upstream template into this vault, with versioned migrations
---

# /update-vault

Met à jour ce vault depuis le template `tetra-plg/boiling-brain` en amont. Depuis la v1.0.2, `/update-vault` est une **machine de migration versionnée** : il détecte la version du vault (via `.claude/template-version`), la compare à la version cible, propage les nouveaux fichiers, et exécute les migrations breaking entre les deux versions si nécessaire.

Utilise ce workflow pour récupérer les nouveaux scripts, slash-commands, rules ou décisions d'architecture publiés dans le template après ton bootstrap.

## Étapes

### 1. Configure le remote `template-upstream` (une seule fois)

```bash
git remote add template-upstream https://github.com/tetra-plg/boiling-brain.git 2>/dev/null \
  && echo "remote template-upstream ajouté" \
  || echo "remote template-upstream déjà configuré"
git fetch template-upstream --tags
```

### 2. Détecter la version locale (avec rétrocompat v1.0.0 et v1.0.1)

```bash
LOCAL_VERSION=""
LOCAL_SHA=""

if [ -f .claude/template-version ]; then
  # Cas standard : v1.0.2+
  LOCAL_VERSION=$(grep '^template-version:' .claude/template-version | awk '{print $2}')
  LOCAL_SHA=$(grep '^template-sha:' .claude/template-version | awk '{print $2}')
elif [ -f .template-bootstrap-sha ]; then
  # Rétrocompat v1.0.1 : a .template-bootstrap-sha mais pas .claude/template-version
  LOCAL_VERSION="1.0.1"
  LOCAL_SHA=$(cat .template-bootstrap-sha)
  echo "Vault détecté en v1.0.1 (legacy). .claude/template-version sera créé pendant cette mise à jour."
else
  # Rétrocompat v1.0.0 : ni l'un ni l'autre. Utiliser le tag v1.0.0 comme baseline.
  LOCAL_SHA=$(git -C . show template-upstream/main 2>/dev/null && git rev-list -n 1 v1.0.0 2>/dev/null || echo "")
  if [ -n "$LOCAL_SHA" ]; then
    LOCAL_VERSION="1.0.0"
    echo "Vault détecté en v1.0.0 (legacy, pas de .template-bootstrap-sha). Baseline = tag v1.0.0."
  else
    echo "BASELINE_MISSING"
    echo "Aucun baseline trouvé (.claude/template-version, .template-bootstrap-sha, et tag v1.0.0 absents)."
    echo "Crée le fichier manuellement (voir Notes en bas) puis relance /update-vault."
    exit 1
  fi
fi

echo "Version locale : $LOCAL_VERSION (SHA $LOCAL_SHA)"
```

### 3. Détecter la version cible (depuis le remote)

```bash
TARGET_VERSION=$(git show template-upstream/main:.claude/template-version 2>/dev/null \
  | grep '^template-version:' | awk '{print $2}')
TARGET_SHA=$(git rev-parse template-upstream/main)

if [ -z "$TARGET_VERSION" ]; then
  echo "Le template upstream n'a pas de .claude/template-version (probablement < v1.0.2). Fallback sur le SHA."
  TARGET_VERSION="$TARGET_SHA"
fi

echo "Version cible : $TARGET_VERSION (SHA $TARGET_SHA)"
```

### 4. Calculer la chaîne de migrations à appliquer

Lister toutes les migrations dans `template-upstream/main:scripts/migrations/v<X>-*.md` dont la version `X` est strictement supérieure à `LOCAL_VERSION` et inférieure ou égale à `TARGET_VERSION`. Ordonner par version croissante.

```bash
git ls-tree -r template-upstream/main --name-only \
  | grep '^scripts/migrations/v[0-9]' \
  | sort
```

Pour chaque migration trouvée, extraire la version depuis le nom de fichier (ex: `scripts/migrations/v1.0.2-claude-md-slim.md` → `1.0.2`). Conserver uniquement celles avec `LOCAL_VERSION < migration_version <= TARGET_VERSION` (comparaison sémantique simple : `sort -V`).

Si aucune migration applicable et version locale == cible : « Ton vault est à jour. ».

Si aucune migration applicable mais version locale < cible : on propage seulement les fichiers (étape 5).

### 5. Identifier et propager les fichiers modifiés

Lister les fichiers changés entre `LOCAL_SHA` et `TARGET_SHA`, en excluant les fichiers consommés au bootstrap :

```bash
git diff --name-only ${LOCAL_SHA} template-upstream/main \
  | grep -v '\.tpl$' \
  | grep -v '^BOOTSTRAP\.md$' \
  | grep -v '^PLACEHOLDERS\.md$' \
  | grep -v '^CONTRIBUTING\.md$' \
  | grep -v '^CLAUDE\.md$'
```

Notes :

- **`.claude/rules/**`** est inclus naturellement (pas dans les exclusions).
- **`scripts/migrations/**`** est inclus aussi : les migrations sont propagées dans le vault pour pouvoir être consommées au prochain `/update-vault`.
- **`CLAUDE.md`** est exclu : c'est user-owned. Sa migration est gérée par les slash-commands `scripts/migrations/v<X>-*.md` interactifs, jamais par écrasement.

Pour les fichiers nouveaux dans le template (qui n'existent pas encore dans le vault — ex: `.claude/template-version`, `.claude/rules/*`, `scripts/migrations/*`), ne pas filtrer par `[ -e "$f" ]` : ils doivent être créés.

Présenter la liste à l'utilisateur via `AskUserQuestion` (multiSelect) : quels fichiers veut-il mettre à jour ? Pré-cocher tous les fichiers nouveaux et tous les fichiers `.claude/rules/`.

Pour chaque fichier sélectionné :

```bash
mkdir -p "$(dirname "$f")"
git show template-upstream/main:"$f" > "$f"
```

> **Pourquoi `git show` plutôt que `cherry-pick` ?**
> Le bootstrap réinitialise l'historique git. Le vault n'a aucun ancêtre commun avec le template — `cherry-pick` échouerait. `git show` copie le contenu cible, sans dépendance à l'historique.

Commit dédié :

```bash
git add <fichiers mis à jour>
git commit -m "chore: propagate template files (${LOCAL_VERSION} → ${TARGET_VERSION})"
```

### 6. Exécuter la chaîne de migrations

Pour chaque migration identifiée à l'étape 4, dans l'ordre de version croissante, **invoquer le slash-command** correspondant. Ex pour la v1.0.2 :

```
/v1.0.2-claude-md-slim
```

Note : les fichiers de migration vivent dans `scripts/migrations/` (pas dans `.claude/commands/`), donc ils ne sont pas exposés comme slash-commands de premier niveau. `/update-vault` les invoque comme **sous-workflow** : tu lis le fichier `scripts/migrations/v<X>-*.md` et tu exécutes son workflow pas-à-pas, en suivant les instructions qu'il contient (lecture, détection, AskUserQuestion, écriture).

Chaque migration peut décider de son propre verdict :

- **Appliquée** : le fichier est mis à jour, commit dédié par la migration elle-même.
- **Édition manuelle demandée par l'utilisateur** : la migration ne touche rien, l'utilisateur prendra le relais. Dans ce cas, **ne pas bumper `.claude/template-version`** à l'étape 7 — la migration sera reproposée au prochain `/update-vault`.
- **Skippée** : idem, ne pas bumper.

Tracker l'état de chaque migration appliquée dans une variable mémoire pour décider du bump final.

### 7. Bump `.claude/template-version`

**Seulement si toutes les migrations applicables ont été acceptées (pas d'édition manuelle ni de skip).**

```bash
TODAY=$(date +%Y-%m-%d)
cat > .claude/template-version <<EOF
template-version: ${TARGET_VERSION}
template-sha: ${TARGET_SHA}
last-updated: ${TODAY}
EOF

git add .claude/template-version
git commit -m "chore: bump template-version to ${TARGET_VERSION}"
```

Si une migration a été skippée ou édition manuelle : afficher un message clair :

> ⚠️ Certaines migrations n'ont pas été appliquées automatiquement. `.claude/template-version` reste sur `${LOCAL_VERSION}`. Relance `/update-vault` quand tu auras finalisé les migrations manuelles.

### 8. Cas particulier : vault legacy v1.0.0 ou v1.0.1 (pas de `.claude/template-version`)

Si `.claude/template-version` n'existait pas en début de session (rétrocompat détectée à l'étape 2), il faut le **créer** à la fin de cette première mise à jour, même si toutes les migrations n'ont pas été acceptées. La création initiale fixe la baseline.

Cas A — toutes les migrations acceptées : `.claude/template-version` est créé à l'étape 7 avec `template-version: ${TARGET_VERSION}` (cas standard).

Cas B — au moins une migration skippée ou en édition manuelle : créer `.claude/template-version` avec **la version d'avant les migrations skippées** :

```bash
# Trouver la dernière migration appliquée avec succès, sinon utiliser LOCAL_VERSION
LAST_APPLIED_VERSION="$LOCAL_VERSION"  # à mettre à jour si migrations partielles appliquées
TODAY=$(date +%Y-%m-%d)
cat > .claude/template-version <<EOF
template-version: ${LAST_APPLIED_VERSION}
template-sha: ${LOCAL_SHA}
last-updated: ${TODAY}
EOF
git add .claude/template-version
git commit -m "chore: initialize .claude/template-version (${LAST_APPLIED_VERSION})"
```

Ainsi le vault legacy bénéficie du nouveau mécanisme de versionning même si la migration n'est pas terminée.

## Notes

**Fichiers jamais mis à jour automatiquement :**

- `*.tpl`, `BOOTSTRAP.md`, `PLACEHOLDERS.md`, `CONTRIBUTING.md` — consommés au bootstrap.
- `CLAUDE.md` — user-owned, migré seulement via `scripts/migrations/v<X>-*.md` interactifs.

**Fichiers propres à ton instance (jamais dans le template) :**

Tes agents (`.claude/agents/<domain>-expert.md`), tes hubs (`wiki/domains/*.md`), `wiki/overview.md`, `wiki/log.md`, `wiki/radar.md`, `wiki/index.md`, etc. ont des noms distincts des fichiers template — ils ne seront jamais écrasés.

**`.claude/rules/`** est upstream-tracké : tout ajout ou modification d'une rule dans le template sera propagé dans le vault à chaque `/update-vault`.

**Baseline manquant (vault pré-v1.0.0 hypothétique) :**

Si ni `.claude/template-version`, ni `.template-bootstrap-sha`, ni le tag `v1.0.0` ne sont trouvés, crée le fichier manuellement :

```bash
git fetch template-upstream --tags
git rev-list -n 1 v1.0.0 > .template-bootstrap-sha
git add .template-bootstrap-sha
git commit -m "fix: add template bootstrap sha (retrocompat)"
```

Puis relance `/update-vault` — la rétrocompat v1.0.0 prendra le relais.
