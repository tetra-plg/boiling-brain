---
description: Lint the wiki for contradictions, orphans, and gaps
argument-hint: [domain — empty = whole wiki]
---

Run the LINT workflow from CLAUDE.md.

If $ARGUMENTS is provided: limit the analysis to domain `$ARGUMENTS`
  (pages wiki/domains/$ARGUMENTS.md, wiki/entities/, wiki/concepts/, wiki/sources/ with `domains: [$ARGUMENTS]`).
If empty: full wiki sweep (expensive — reserve for monthly reviews).

Report on:
- Contradictions across pages
- Stale claims
- Orphan pages — see criterion below
- Concepts mentioned without their own page
- Missing cross-references
- Data gaps worth researching

Suggest next sources to ingest.

## Orphan pages — criterion

**Orphan = page with 0 inbound link from a page other than its parent ingestion source.**

A page created from a single source will always have ≥1 inbound from that source; this trivial link does not suffice to connect it to the cross-ref network (domain hubs, cheatsheets, other concepts, syntheses). The naive "0 inbound" criterion misses those cases.

Practical heuristic:

1. For every non-source page, read its `sources:` frontmatter.
2. List the inbound wikilinks pointing to the page (grep).
3. Subtract the inbounds coming from the sources listed in its `sources:` (and their `covered_paths`).
4. If the remainder is 0 → effective orphan.

Example: a framework concept created during the ingestion of a single doc, never cross-referenced from its domain hub nor from a neighboring concept, is an orphan — even though it has 1 inbound from its parent source.
