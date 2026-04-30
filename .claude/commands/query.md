---
description: Query the wiki to answer a question from indexed pages, with citations and optional synthesis archiving
argument-hint: <question>
---

Run the QUERY workflow from CLAUDE.md on: $ARGUMENTS

1. Lire `wiki/index.md` pour identifier les pages pertinentes à la question.
2. Lire ces pages, suivre les `[[wikilinks]]` nécessaires.
3. Synthétiser la réponse avec citations `[[page]]`.
4. Si la réponse est substantielle, proposer de l'archiver dans `wiki/syntheses/<slug>.md`.
5. Ajouter dans `wiki/log.md` : `## [YYYY-MM-DD] query | <question courte>`.
