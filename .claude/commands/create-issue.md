---
description: Crée une issue sanitizée sur le repo template upstream à partir du contexte de la session courante (sanitization automatique des données vault-specific)
argument-hint: [bug|enhancement|docs|question] [<courte description optionnelle>]
---

Run the CREATE-ISSUE workflow on: $ARGUMENTS

Cette commande remonte un bug, une amélioration, une question doc ou une question générale vers le repo **template upstream** (`tetra-plg/boiling-brain` par défaut). Elle génère un draft depuis le contexte de la conversation, **sanitize** les données vault-specific via les règles de `.claude/rules/sanitization-issues.md`, propose la prévisualisation, puis crée l'issue via `gh issue create`.

Aucune création silencieuse : la dernière étape est toujours une validation utilisateur via `AskUserQuestion`.

## 1. Pré-requis

Vérifier dans cet ordre, stopper au premier échec avec un message clair :

```bash
# 1.1 — gh CLI authentifié
gh auth status 2>&1 | head -5
# Si échec : "Lance `gh auth login` puis relance /create-issue."

# 1.2 — Remote template-upstream configuré (si absent, le proposer)
TEMPLATE_REMOTE_URL=$(git remote get-url template-upstream 2>/dev/null)
if [ -z "$TEMPLATE_REMOTE_URL" ]; then
  echo "Le remote template-upstream n'est pas configuré."
  echo "Configure-le via :"
  echo "  git remote add template-upstream https://github.com/tetra-plg/boiling-brain.git"
fi
```

Extraire `<owner/repo>` depuis l'URL du remote (parser `https://github.com/<owner>/<repo>.git` ou `git@github.com:<owner>/<repo>.git`). Stocker dans `TEMPLATE_REPO`.

## 2. Détermination du type d'issue

Parser `$ARGUMENTS` :
- Premier token = type, parmi `bug`, `enhancement` (alias `feature`), `docs`, `question`.
- Reste = description courte optionnelle pour pré-remplir le titre.

Si type absent ou invalide → `AskUserQuestion` :

```json
{
  "questions": [{
    "question": "Quel type d'issue veux-tu créer ?",
    "header": "Type",
    "multiSelect": false,
    "options": [
      {"label": "bug", "description": "Quelque chose ne marche pas comme attendu (sections : Contexte, Reproduction, Fix proposé, Test plan, Impact)"},
      {"label": "enhancement", "description": "Proposition d'amélioration ou nouvelle feature (sections : Problème, Proposition, Alternatives, Out-of-scope, Critères de done)"},
      {"label": "docs", "description": "Manque ou imprécision dans la doc du template (sections : Section concernée, Manque constaté, Suggestion)"},
      {"label": "question", "description": "Question d'usage ou de design (sections : Contexte, Question, Ce qui a déjà été essayé)"}
    ]
  }]
}
```

Mapping label GitHub : `bug` → `bug`, `enhancement` / `feature` → `enhancement`, `docs` → `documentation`, `question` → `question`. Vérifier que le label existe sur le repo cible :

```bash
gh label list --repo "$TEMPLATE_REPO" --json name --jq '.[].name'
```

Si le label n'existe pas, créer l'issue sans label (signaler à l'utilisateur dans la prévisualisation).

## 3. Collecte du contexte

Lire la conversation courante pour identifier le sujet de l'issue :
- Quel fichier / quel comportement / quel scénario est en jeu ?
- Quelle erreur observée vs attendue (pour bug) / quel manque (pour enhancement / docs) / quel point de confusion (pour question) ?
- Y a-t-il des extraits de code, traces d'erreur, ou commandes pertinentes ?

Si la description du `$ARGUMENTS` est fournie, l'utiliser comme **titre candidat** mais la reformuler si elle contient des références internes (slugs, wikilinks).

## 4. Rédaction du draft selon template

### Structure par type

**bug** :
```markdown
## Contexte

<2-3 phrases : où, dans quel scénario, depuis quand>

## Reproduction

<Étapes minimales reproductibles. Snippet de commande / fichier si pertinent.>

## Fix proposé

<Hypothèse de correction. Liste de fichiers / lignes / approche.>

## Test plan

- [ ] <cas test 1>
- [ ] <cas test 2>

## Impact

<Bloquant ? Cosmétique ? Combien de vaults touchés ?>
```

**enhancement** :
```markdown
## Problème

<Pourquoi le statu quo est insuffisant>

## Proposition

<Description de la solution proposée>

## Alternatives considérées

<Autres approches, pourquoi écartées>

## Out-of-scope (v1)

<Ce qu'on ne fait PAS dans cette première version>

## Critères de done

- [ ] <critère 1>
- [ ] <critère 2>
```

**docs** :
```markdown
## Section concernée

<Fichier + section précise (ex: README.md "Workflow loop")>

## Manque constaté

<Ce qui n'est pas clair, manquant, ou faux>

## Suggestion

<Ce qu'on pourrait ajouter ou reformuler>
```

**question** :
```markdown
## Contexte

<Configuration / scénario>

## Question

<La question, formulée précisément>

## Ce qui a déjà été essayé

<Ressources lues, tests effectués>
```

## 5. Sanitization

Appliquer les règles de `.claude/rules/sanitization-issues.md` au titre **et** au body du draft :

- **Strip silencieux** : wikilinks `[[...]]`, chemins `raw/notes/YYYY-MM-DD-*`, slugs de domaines listés dans `wiki/index.md`, chemins `wiki/sources/<date>-<slug>.md`, emails.
- **Flag pour review** : noms propres en milieu de phrase (hors liste blanche `Claude`, `Anthropic`, `GitHub`, etc.), noms d'entités lues depuis `wiki/entities/*.md`, handles `@xxx`.
- **Anonymisation des cas concrets** : reformuler « 18 pages BB ont eu X » en « N pages affected (figure measured on the BoilingBrain reference vault) » ou « Some vault pages had X ».

Construire un **rapport de sanitization** avec :
- Liste des transformations silencieuses appliquées (qui peut être copiée pour audit).
- Liste des éléments flaggés à confirmer par l'utilisateur.

## 6. Prévisualisation et validation

Afficher au format :

```
=== Issue draft (sanitized) ===

Repo cible : tetra-plg/boiling-brain
Label : bug

Titre :
<titre sanitizé>

Body :
<body sanitizé>

=== Sanitization ===
Transformations silencieuses :
- <wikilink> → <terme générique>
- <slug> → domain X
- ...

À confirmer (flaggé) :
- Nom propre détecté : "<token>" — confirmer ou éditer
- ...
```

Puis `AskUserQuestion` :

```json
{
  "questions": [{
    "question": "Que faire avec ce draft ?",
    "header": "Issue",
    "multiSelect": false,
    "options": [
      {"label": "✅ Créer l'issue", "description": "Crée l'issue via gh issue create. Affichera l'URL en retour."},
      {"label": "✏️ Éditer manuellement", "description": "N'crée rien. Affiche le draft prêt à copier-coller dans l'UI GitHub."},
      {"label": "❌ Annuler", "description": "Abandonne sans rien créer."}
    ]
  }]
}
```

## 7. Création (si validé)

```bash
gh issue create \
  --repo "$TEMPLATE_REPO" \
  --title "$SANITIZED_TITLE" \
  --body "$SANITIZED_BODY" \
  --label "$LABEL"
```

Capturer l'URL retournée (stdout). En cas d'échec (réseau, label inconnu, droits insuffisants) : afficher l'erreur + le draft copy-pastable comme fallback.

## 8. Suite (radar)

Après création réussie, proposer via `AskUserQuestion` :

```json
{
  "questions": [{
    "question": "Ajouter un suivi dans wiki/radar.md ?",
    "header": "Radar",
    "multiSelect": false,
    "options": [
      {"label": "✅ Oui, suivi dans le radar", "description": "Ajoute une entrée `- [ ] **[Template · YYYY-MM-DD]** <description courte>. → <URL>` dans wiki/radar.md catégorie « À surveiller »"},
      {"label": "❌ Non, pas de suivi local", "description": "L'issue vit sa vie sur GitHub uniquement"}
    ]
  }]
}
```

Si oui : ajouter l'entrée à `wiki/radar.md`, commit dédié `chore(radar): track upstream issue <#N>`.

Logger dans `wiki/log.md` : `## [YYYY-MM-DD] create-issue | <type> #<numéro> <titre court>`.

## Cas d'usage proactif depuis le radar

`/create-issue` peut aussi être déclenchée **proactivement** par le main context lors de l'affichage du radar (« montre le radar » / « qu'est-ce qu'il y a à faire aujourd'hui »). Quand une entrée du radar concerne **l'environnement template** (typiquement un bug ou manque touchant `scripts/scan-raw.sh`, `.claude/commands/*.md`, `BOOTSTRAP.md`, ou tout fichier propagé par `/update-vault`), le main context propose à l'utilisateur :

> Cette entrée du radar concerne le template upstream. Veux-tu la remonter via `/create-issue <type>` ?

Le main context **ne crée pas l'issue tout seul** — il propose juste la commande, l'utilisateur valide, le workflow standard ci-dessus prend le relais.

## Fallback `gh auth login` manquant

Si à l'étape 1.1 `gh auth status` échoue, ne pas continuer. Afficher le draft sanitizé prêt à copier-coller (sans même faire la sanitization complète — juste un draft brut). L'utilisateur peut alors `gh auth login` puis relancer, ou copier-coller dans l'UI GitHub.
