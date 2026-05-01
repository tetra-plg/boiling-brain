---
description: Save the current session journal to raw/notes/sessions/ for later ingestion
argument-hint: <slug>
---

# /compress-bb

Sauvegarde le journal de la session courante dans `raw/notes/sessions/YYYY-MM-DD-<slug>.md` pour ingestion ultérieure via `/ingest`.

Utilise ce workflow à la fin d'une session de travail substantielle : analyse, décisions, explorations, apprentissages.

## Étapes

### 1. Déterminer le slug

Si `$ARGUMENTS` est fourni, l'utiliser comme slug (kebab-case, sans date).
Sinon, inférer un slug court et descriptif depuis les thèmes de la session.

### 2. Construire le contenu

Le fichier doit capturer ce qui s'est passé dans la session, **pas l'historique brut** :

```markdown
---
type: session-journal
date: YYYY-MM-DD
slug: <slug>
themes: [liste des thèmes abordés]
---

# Session — <slug> (YYYY-MM-DD)

## Contexte
<Ce qui était en cours avant la session : état du projet, objectif de départ.>

## Ce qui a été fait
<Liste des actions concrètes : fichiers créés/modifiés, décisions prises, problèmes résolus.>

## Apprentissages & insights
<Ce qui a émergé de la session : nouvelles compréhensions, patterns observés, surprises.>

## Questions ouvertes
<Ce qui reste flou ou à résoudre lors de la prochaine session.>

## Prochaines étapes
<Actions concrètes identifiées pour la suite.>
```

### 3. Écrire le fichier

```
raw/notes/sessions/YYYY-MM-DD-<slug>.md
```

### 4. Mettre à jour le signal pending-ingest

Ajouter le chemin dans `cache/.pending-ingest` (créer le fichier si absent) :

```
raw/notes/sessions/YYYY-MM-DD-<slug>.md
```

### 5. Confirmer à l'utilisateur

Afficher le chemin créé et rappeler :
- Le fichier sera proposé à l'ingestion au prochain démarrage de session (via hook SessionStart).
- L'ingestion manuelle est possible immédiatement : `/ingest raw/notes/sessions/YYYY-MM-DD-<slug>.md`.
