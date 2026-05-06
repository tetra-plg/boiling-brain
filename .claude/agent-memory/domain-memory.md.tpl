# Memory — {{domain_label}}-expert

> This memory is read by `{{domain_slug}}-expert` at the start of every ingest, and updated at the end. It represents the **domain state** in the wiki — not behavioral rules (those live in the system prompt and evolve via `/evolve-agent`).
>
> Format: named sections with dated entries `[last-seen: YYYY-MM-DD]`. An entry disappears as soon as it's confirmed (concept created, pattern codified) or archived if it lingers > 90 days without follow-up.

## Pending patterns

> Patterns observed in a single source — I'm waiting for a 2nd occurrence before creating the matching concept page (cf. wiki rule "≥2 sources"). If a new source confirms one of these, I create the page right away and drop the entry.

_(empty at boot)_

## Recent concepts

> List of the last 10 concepts I created or significantly enriched, descending by date. Used to avoid duplicates and to surface natural cross-refs in upcoming ingests.

_(empty at boot)_

## Pivot sources

> Particularly structural sources for the domain — they anchor an entire sub-theme. Worth keeping in mind for cross-refs.

_(empty at boot)_

## Expired patterns

> Archive of entries that stayed too long pending (> 90 days) or were discarded. Not deleted — they may become relevant again.

_(empty at boot)_
