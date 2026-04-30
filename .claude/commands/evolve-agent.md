---
description: Consomme les suggestions accumulées d'un agent expert et propose une évolution de son prompt système
argument-hint: <domain>
---

Run EVOLVE-AGENT workflow on domain: $ARGUMENTS

Faire évoluer le prompt de l'agent expert `$ARGUMENTS-expert` à partir des suggestions qu'il a lui-même remontées lors de ses ingestions.

## Étapes

### 1. Lire les matériaux

- **Prompt actuel** : `.claude/agents/$ARGUMENTS-expert.md`.
- **Suggestions accumulées** : `.claude/agents/$ARGUMENTS-expert.suggestions.md` (append-only, horodaté par `/ingest`).
- **Archive précédente** (si existe) : `.claude/agents/$ARGUMENTS-expert.suggestions.archive.md` — pour voir ce qui a déjà été intégré dans le passé.

Si le fichier de suggestions n'existe pas ou est vide → informer le user, proposer qu'il déclenche d'abord une ou plusieurs ingestions du domaine.

### 2. Analyser

Pour chaque suggestion accumulée :
- Classer : **pattern récurrent** (≥2 occurrences) / **angle mort** / **proposition de prompt** / **proposition de livrable**.
- Dédupliquer les suggestions équivalentes.
- Filtrer : garder ce qui est **récurrent** ou **clairement structurant**. Écarter l'anecdotique isolé (mais ne pas l'archiver — il pourra redevenir récurrent).

### 3. Proposer un diff de révision

Présenter au user un **plan de révision concis** :
- Liste des suggestions retenues (et pourquoi).
- Liste des suggestions écartées pour cette itération (avec raison).
- **Diff proposé** sur `.claude/agents/$ARGUMENTS-expert.md` : sections ajoutées, modifiées, supprimées.
- Impact attendu sur les prochaines ingestions (en 2-3 lignes).

Demander validation via `AskUserQuestion` avec options :
- **Appliquer le diff** (option par défaut si pertinent).
- **Modifier** (user précise ce qui doit changer).
- **Reporter** (ne rien faire, les suggestions restent en attente).

### 4. Appliquer (si validé)

1. Éditer `.claude/agents/$ARGUMENTS-expert.md` selon le diff.
2. Déplacer les suggestions intégrées de `.suggestions.md` vers `.suggestions.archive.md`. Préfixer chaque bloc archivé par `### [YYYY-MM-DD] evolve → version <n>`. Ne pas perdre les suggestions écartées — elles restent dans `.suggestions.md`.
3. Appendre une entrée dans `wiki/log.md` :
   ```
   ## [YYYY-MM-DD] evolve | $ARGUMENTS-expert
   Révision du prompt système à partir de <N> suggestions. Retenues : <résumé>. Écartées : <résumé court>. Archive : `.claude/agents/$ARGUMENTS-expert.suggestions.archive.md`.
   ```
4. Indiquer au user que l'agent sera mis à jour au prochain démarrage de session (les subagents sont chargés au boot).

### 5. Rapport final

- Nombre de suggestions lues / retenues / reportées / archivées.
- Chemin du fichier agent mis à jour.
- Prochaine étape recommandée (ex. rejouer `/ingest` sur une source récente pour valider l'amélioration).

## Principes

- **Curation humaine, pas auto-modification silencieuse** — l'agent propose, le user valide.
- **Pas de régression** : le diff respecte la structure existante (frontmatter, sections, ton). On ajoute ou affine, on ne refond pas sans raison.
- **Traçabilité** : chaque évolution est loguée, chaque suggestion intégrée est archivée avec sa date et son origine.
