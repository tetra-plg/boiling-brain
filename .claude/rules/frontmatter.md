---
description: Frontmatter rules for wiki pages (sources, concepts, syntheses, decisions)
paths:
  - "wiki/sources/**"
  - "wiki/concepts/**"
  - "wiki/syntheses/**"
  - "wiki/decisions/**"
  - "wiki/entities/**"
  - "wiki/cheatsheets/**"
  - "wiki/diagrams/**"
  - "wiki/domains/**"
---

# Frontmatter — hard rules

Every wiki page starts with a YAML frontmatter. These rules are **non-negotiable**: an expert agent that violates them produces an invalid page.

## Mandatory fields

```yaml
---
type: source | entity | concept | synthesis | decision | domain | cheatsheet | diagram | overview
domains: [<domain1>, <domain2>, ...]
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

- `type`: exactly one of the values above, lowercase.
- `domains`: YAML array, slugs of domains declared in `wiki/index.md`. At least one.
- `created` / `updated`: ISO format `YYYY-MM-DD`. `updated` reflects the last material modification of the page.

## Fields specific to `type: source` pages

```yaml
source_path: "raw/<folder>/<file>.md"        # mandatory, non-empty, real existing path
source_sha256: "<64-character hex hash>"     # mandatory, non-empty
ingested: YYYY-MM-DD                         # date of ingestion by the agent
covered_paths:                               # optional: if the page synthesizes multiple raws
  - "raw/<folder>/<file1>.md"
  - "raw/<folder>/<file2>.md"
```

### Hard rule `source_sha256`

`source_sha256` must **always** be computed via `shasum -a 256 <file>` on the actual file at ingestion time. Never a textual placeholder (`see-raw-file`, the slug, a fake hex, `TODO`...). This rule applies without exception to every expert agent.

Standard computation command:

```bash
shasum -a 256 raw/<folder>/<file>.md | awk '{print $1}'
```

If the file cannot be hashed (invalid path, access error), the ingestion fails — no silent fallback.

## Fields specific to `type: decision` pages

```yaml
status: pending | accepted                            # mandatory
verdict: null | validated | invalidated | partial     # optional, null until reality validates
verdict_date: null | YYYY-MM-DD                       # optional, must accompany verdict
verdict_evidence: null | "short narrative"            # optional, must accompany verdict
```

ADRs without `verdict` after **90 days** are flagged by `/lint` (forces L3 confrontation — see [[decisions/template-l3-optims-v1.1x]]).

## Optional `revisit_after` field

```yaml
revisit_after: YYYY-MM-DD     # on type: decision and type: concept pages
```

`/lint` flags pages whose `revisit_after` date has passed. Use this to schedule a re-read of a concept or decision (e.g. after a related project ships, after a major external change).

## `summary_l0` and `summary_l1` fields (tiered loading)

Mandatory for `domains/`, `cheatsheets/`, `concepts/`, `syntheses/`. Recommended for `sources/`, `entities/`.

```yaml
summary_l0: "≤140 chars, telegraphic, scannable"
summary_l1: |
  2-5 sentences, ~50-150 words, structured description.
  Covers the main claims and the angle.
```

These fields feed the **tiered loading** of oracles: an agent can scan an entire domain via the `summary_l0` (TOC L0), then descend to `summary_l1` (preview L1) or full body (L2) only when relevant.

## `sources` field (cross-reference)

For non-`source` pages that lean on sources:

```yaml
sources:
  - "[[sources/2026-XX-XX-slug]]"
  - "[[sources/2026-YY-YY-other-slug]]"
```

Obsidian wikilinks, no bare paths.
