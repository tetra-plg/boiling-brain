---
description: Lint the wiki for contradictions, orphans, and gaps
argument-hint: [domain — empty = whole wiki]
---

Run the LINT workflow in **two explicit passes**: a deterministic **structural pass** (main/script) and a domain-judgment **semantic pass** (optionally delegated to domain experts).

If `$ARGUMENTS` is a domain: limit both passes to domain `$ARGUMENTS` (pages `wiki/domains/$ARGUMENTS.md`, and `wiki/entities/`, `wiki/concepts/`, `wiki/sources/` with `domains: [$ARGUMENTS]`).
If empty: full wiki sweep (expensive — reserve for monthly reviews).

## Pass 1 — Structural (deterministic, main/script — never delegated)

Mechanical, decidable without domain knowledge:

- **Orphan pages** — see criterion below.
- **Stale raw sources** — for every page, each path listed in `sources:` (and `covered_paths:`) must exist on disk under `raw/`. A missing source means the page references content that was deleted or moved — flag it. (This is the local counterpart of the CI, which cannot see `raw/`.)
- **Broken wikilinks** — a `[[target]]` with no matching page.
- **L3 readiness** (date-based):
  - ADRs (`wiki/decisions/*.md`) older than 90 days without `verdict` (status confirmation overdue).
  - Pages whose `revisit_after` date has passed (decisions and concepts).

Run `python3 scripts/wiki-maint/validate-wiki.py` for the checks it covers; complete with the orphan heuristic below.

## Pass 2 — Semantic (domain judgment — delegable to the domain expert)

Requires weighing meaning, history, and domain conventions — where a domain expert (system prompt + `agent-memory/<domain>/` + Domain orientation, #71) beats the main context:

- Contradictions across pages.
- Stale claims (superseded by a newer source).
- Concepts mentioned without their own page (threshold met?).
- Missing cross-references.
- Data gaps worth researching — suggest next sources to ingest.

### Delegation (selective, opt-in)

- `/lint <domain>` → run Pass 1 for the domain, then **delegate Pass 2 to `<domain>-expert`** (if the agent exists).
- `/lint` (full sweep) → run Pass 1 globally, then **partition Pass 2 by domain** and delegate each domain to its expert (fan-out — the monthly deep review). Domains without an expert agent: Pass 2 stays in the main context.

Spawn each expert in **semantic-lint mode**, with:

- The lint scope (its domain pages).
- A fresh snapshot: `bash scripts/mcp/wiki-cli.sh scan-domain <domain>` under `## Domain snapshot`.
- The content of `.claude/agent-output-contract.md`.
- Instruction: return a `## Semantic findings` block. **Read-only** — do not edit `wiki/`; the main context applies any fix (create a cross-ref, open a radar item).

Aggregate the `## Semantic findings` blocks, present grouped by finding type, then act (or log to `wiki/radar.md`) from the main context after validation.

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
