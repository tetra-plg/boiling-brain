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
- Orphan pages — voir critère ci-dessous
- Concepts mentioned without their own page
- Missing cross-references
- Data gaps worth researching

Suggest next sources to ingest.

## Orphan pages — critère

**Orphan = page avec 0 inbound link depuis une page autre que sa source parente d'ingestion.**

Une page créée à partir d'une seule source aura toujours ≥1 inbound depuis cette source ; ce lien trivial ne suffit pas à la connecter au réseau de cross-refs (hubs de domaine, cheatsheets, autres concepts, syntheses). Le critère naïf "0 inbound" rate ces cas.

Heuristique pratique :

1. Pour chaque page non-source, lire son frontmatter `sources:`.
2. Lister les wikilinks entrants vers la page (grep).
3. Soustraire les inbounds qui viennent des sources listées dans son `sources:` (et leurs `covered_paths`).
4. Si reste 0 → orphan effective.

Exemple : un concept framework créé lors de l'ingestion d'une doc unique, jamais cross-référencé depuis le hub de son domaine ni depuis un concept voisin, est orphan — même s'il a 1 inbound depuis sa source parente.
