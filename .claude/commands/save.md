---
description: Archive the current conversation synthesis into wiki/syntheses/
argument-hint: <slug>
---

Run the SAVE workflow from CLAUDE.md with slug: $ARGUMENTS

Steps:
1. Identifier la dernière synthèse/réponse substantielle de la conversation.
2. Créer `wiki/syntheses/$ARGUMENTS.md` avec frontmatter (`type: synthesis`, `created`, `domains`, `sources`).
3. Inclure les liens `[[page]]` vers les pages citées.
4. Mettre à jour `wiki/index.md` section Synthèses.
5. Ajouter entrée dans `wiki/log.md` : `## [YYYY-MM-DD] save | $ARGUMENTS`.
