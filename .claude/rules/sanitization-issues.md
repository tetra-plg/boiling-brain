---
description: Règles dures de sanitization avant publication d'une issue sur le repo template upstream (évite la fuite de données du vault)
paths:
  - ".claude/commands/create-issue.md"
  - "scripts/migrations/*-create-issue*.md"
---

# Sanitization avant `gh issue create` vers le template

Quand l'utilisateur invoque `/create-issue` pour remonter un bug ou une amélioration vers le template upstream, le draft est généré depuis le contexte de la session Claude Code en cours. Ce contexte est susceptible de contenir des données spécifiques au vault de l'utilisateur (slugs de domaines, noms propres, chemins de contenu privé, références internes). Ces règles définissent ce qui doit être stripé, transformé ou flaggé pour review humaine **avant** la création de l'issue.

## Règles strip (transformation silencieuse)

Les patterns suivants sont **transformés systématiquement** dans le titre et le body du draft :

### 1. Wikilinks Obsidian

- Pattern : `\[\[.+?\]\]` (avec ou sans alias `|`).
- Action : strip complet, **ou** remplacement par un terme générique si le contexte est explicite (ex: `[[concepts/llm-wiki]]` → `the LLM wiki concept`).
- Justification : les wikilinks sont des références internes au vault, sans valeur en dehors.

### 2. Chemins de contenu privé

- Pattern : `raw/notes/YYYY-MM-DD-<anything>.md`, `raw/transcripts/YYYY-MM-DD-<anything>.md`, `raw/clippings/<anything>.md`.
- Action : remplacer par un placeholder générique (`raw/notes/<example>.md`, `raw/transcripts/<example>.md`).
- Justification : les noms de fichiers révèlent souvent le sujet de la note privée.

### 3. Slugs de domaines vault-specific

- Lire la liste des domaines depuis `wiki/index.md` (section `## Domaines`) ou les noms de fichiers `wiki/domains/*.md`.
- Pour chaque slug détecté dans le draft (mention textuelle ou path `wiki/domains/<slug>.md`), remplacer par `domain X`, `domain Y`, etc., **sauf si** le slug correspond à un terme générique attendu dans le template (`metier`, `tech`, `ia` peuvent rester si le contexte l'exige — mais c'est rare).
- Justification : les domaines sont une projection personnelle du vault.

### 4. Chemins `wiki/sources/<date>-<slug>.md`

- Pattern : `wiki/sources/[0-9]{4}-[0-9]{2}-[0-9]{2}-<slug>.md`.
- Action : remplacer par `wiki/sources/<example>.md` ou par une description fonctionnelle (`a source page about X`).
- Justification : révèle ce que l'utilisateur a ingéré récemment.

## Règles flag (review humaine obligatoire)

Les patterns suivants ne sont **pas stripés silencieusement** mais signalés à l'utilisateur dans la prévisualisation, qui doit les valider ou les éditer :

### 5. Noms propres de personnes

- Heuristique : tout token capitalisé en **milieu de phrase** (hors début), sauf liste blanche connue (`Claude`, `Anthropic`, `GitHub`, `Linux`, noms de produits OSS standards).
- Action : surligner dans la prévisualisation avec un avertissement « Nom propre détecté : `<token>` — confirmer ou éditer ».
- Justification : un nom propre peut être une vraie personne du vault (collègue, formateur, sujet d'étude). La détection automatique aurait trop de faux positifs pour strip silencieusement.

### 6. Noms d'entités externes spécifiques au vault

- Pattern : noms d'entreprises, produits internes, projets non-publics référencés dans `wiki/entities/`.
- Action : lire les noms d'entités depuis `wiki/entities/*.md` et flagger toute occurrence dans le draft.
- Justification : un produit interne ou un client du vault ne doit jamais sortir publiquement.

### 7. Identifiants utilisateur (emails, handles)

- Pattern : `[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+`, `@[a-zA-Z0-9_]+` (handles potentiels).
- Action : strip silencieux pour les emails. Flag pour les handles (peuvent être des références publiques légitimes comme `@anthropics`).

## Règles de structure

### 8. Anonymisation des cas concrets

Si le draft cite un cas concret (« 18 pages BB ont eu... »), proposer une formulation neutre : « Some vault pages had... » ou « N pages affected (figure measured on the BoilingBrain reference vault) ». Le mainteneur du template peut choisir de préciser dans le contexte de l'issue, mais la formulation par défaut est anonyme.

### 9. Templates par type d'issue

- **bug** : sections `## Contexte`, `## Reproduction`, `## Fix proposé`, `## Test plan`, `## Impact`.
- **enhancement** (alias `feature`) : sections `## Problème`, `## Proposition`, `## Alternatives considérées`, `## Out-of-scope`, `## Critères de done`.
- **docs** : sections `## Section concernée`, `## Manque constaté`, `## Suggestion`.
- **question** : sections `## Contexte`, `## Question`, `## Ce qui a déjà été essayé`.

Le draft suit l'un de ces templates selon le type. Pas de section narrative libre.

## Verdict final

La création de l'issue est **toujours validée par l'utilisateur** via `AskUserQuestion` avec 3 options : créer, éditer manuellement, annuler. Aucune création silencieuse, même si toutes les règles strip/flag passent. Le filet de sécurité humain reste obligatoire.

Si l'utilisateur choisit « éditer manuellement », l'issue n'est pas créée — un draft copy-pastable est affiché pour qu'il l'utilise dans l'UI GitHub.
