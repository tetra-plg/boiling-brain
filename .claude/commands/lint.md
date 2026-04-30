---
description: Lint the wiki for contradictions, orphans, and gaps
argument-hint: [domaine — vide = tout le wiki]
---

Run the LINT workflow from CLAUDE.md.

Si $ARGUMENTS est fourni : limiter l'analyse au domaine `$ARGUMENTS`
  (pages wiki/domains/$ARGUMENTS.md, wiki/entities/, wiki/concepts/, wiki/sources/ ayant `domains: [$ARGUMENTS]`).
Si vide : analyse complète du wiki (coûteux — réserver aux revues mensuelles).

Report on:
- Contradictions across pages
- Stale claims
- Orphan pages (no inbound links)
- Concepts mentioned without their own page
- Missing cross-references
- Data gaps worth researching

Suggest next sources to ingest.
