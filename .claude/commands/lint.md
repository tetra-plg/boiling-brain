---
description: Lint the wiki for contradictions, orphans, and gaps
argument-hint: [domain — empty = whole wiki]
---

Run the LINT workflow from CLAUDE.md.

If $ARGUMENTS is provided: limit the analysis to domain `$ARGUMENTS`  (pages wiki/domains/$ARGUMENTS.md, wiki/entities/, wiki/concepts/, wiki/sources/ with`domains: [$ARGUMENTS]`).
If empty: full wiki sweep (expensive — reserve for monthly reviews).

Report on:

- Contradictions across pages
- Stale claims
- Orphan pages — see criterion below
- Concepts mentioned without their own page
- Missing cross-references
- **Stale raw sources** — for every page, each path listed in `sources:` (and
  `covered_paths:`) must exist on disk under `raw/`. A missing source means the
  page references content that was deleted or moved — flag it. (This is the
  local counterpart of the CI, which cannot see `raw/`.)
- Data gaps worth researching
- **L3 readiness**:
  - ADRs (`wiki/decisions/*.md`) older than 90 days without `verdict` (status confirmation overdue).
  - Pages whose `revisit_after` date has passed (decisions and concepts).

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

## Final step — archive handled radar entries

After reporting, keep the active radar lean by archiving its resolved entries.

Run `python3 scripts/wiki-maint/archive-radar.py`. It moves every `- [x]` entry
from `wiki/radar.md` into `wiki/radar-archive.md` — under the entry's original
`## ` section (created in the archive if absent; generic `## Handled` fallback for
entries under no section), preserving each entry's resolution text verbatim. It
creates `wiki/radar-archive.md` on first use with a valid frontmatter and bumps
the `updated:` date on both files. It is idempotent: with no `[x]` entry it writes
nothing.

Parse its stdout:

- `archived=<N>` — if `N > 0`, add to the lint report: **"Archived N handled radar
  entries to `wiki/radar-archive.md`."** If `N == 0`, say nothing about archiving.
- `active=<M>` and `total_archived=<K>` — if `wiki/radar.md` / `wiki/radar-archive.md`
  carry an entry count in their `summary_l0`, reconcile it with these numbers
  (`M` active entries, `K` archived).

This runs on every `/lint`, whole-radar, regardless of the `$ARGUMENTS` domain scope.
