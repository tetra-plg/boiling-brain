---
description: Query the wiki to answer a question from indexed pages, with citations and optional synthesis archiving
argument-hint: <question>
---

Run the QUERY workflow from CLAUDE.md on: $ARGUMENTS

## Tiered loading — stratégie de lecture

Lire le moins possible pour répondre avec précision. Descendre les niveaux dans l'ordre :

**L0 — scan** : `summary_l0` de chaque page candidate (champ frontmatter, ≤140 chars).
**L1 — preview** : `summary_l1` (frontmatter, 2-5 phrases) si L0 ne suffit pas à discriminer.
**L2 — full body** : corps complet uniquement pour les pages confirmées pertinentes par L1.

## Étapes

1. Identifier le ou les domaines de la question (poker, ia, factory, metier, tech, astro, ou transversal).
2. Lire `wiki/index.md` → extraire la liste des pages candidates.
3. **L0** : lire les `summary_l0` des candidates (en-têtes frontmatter uniquement si les pages sont longues).
   - Si la réponse est claire depuis L0 → répondre directement avec citations.
   - Sinon : sélectionner les pages nécessitant un approfondissement.
4. **L1** : lire le `summary_l1` des pages sélectionnées. Si suffisant → répondre. Sinon → L2.
5. **L2** : lire le corps complet des pages retenues. Suivre les `[[wikilinks]]` uniquement si indispensable.
6. Synthétiser la réponse avec citations `[[page]]`. Mentionner explicitement si la réponse est partielle faute de sources.
7. Si la réponse est substantielle (>200 mots, exploitable en dehors de cette session), proposer de l'archiver via `/save <slug>`.
8. Ajouter dans `wiki/log.md` : `## [YYYY-MM-DD] query | <question courte>`.
