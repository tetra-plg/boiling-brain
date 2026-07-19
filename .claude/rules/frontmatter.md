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
source_path: "raw/<folder>/<file>.md" # mandatory, non-empty, real existing path
source_sha256: "<64-character hex hash>" # mandatory, non-empty
ingested: YYYY-MM-DD # date of ingestion by the agent
covered_paths: # optional: if the page synthesizes multiple raws
  - "raw/<folder>/<file1>.md"
  - "raw/<folder>/<file2>.md"
```

### Hard rule `source_path` round-trip

`source_path` **must round-trip byte-for-byte** to the on-disk filename. Do NOT normalise typographic characters (apostrophes `'` ↔ `’`, quotes, em/en dashes, etc.) when emitting `source_path`. `scripts/wiki-maint/scan-raw.sh` applies Unicode normalization symmetrically at match time (NFC + fold U+2019 → U+0027), but emitting a normalized `source_path` against a non-normalized filename creates ghost duplicate pages on every subsequent sweep.

### Hard rule `source_sha256`

`source_sha256` must **always** be computed via `shasum -a 256 <file>` on the actual file at ingestion time. Never a textual placeholder (`see-raw-file`, the slug, a fake hex, `TODO`...). This rule applies without exception to every expert agent.

Standard computation command:

```bash
shasum -a 256 raw/<folder>/<file>.md | awk '{print $1}'
```

If the file cannot be hashed (invalid path, access error), the ingestion fails — no silent fallback.

### Composite hash `source_sha256_composite` (multi-file pages)

A page that synthesizes several raws via `covered_paths` MAY carry a
`source_sha256_composite`. Its **canonical** value — the one
`scripts/wiki-maint/scan-raw.py` recomputes to detect drift — is the sha256 of
the concatenation, over every `covered_paths` entry sorted lexicographically,
of the exact line `shasum -a 256` prints for that file (`<hex>  <path>\n`, two
spaces, trailing newline):

```bash
for p in $(printf '%s\n' "${covered_paths[@]}" | sort); do
  shasum -a 256 "$p"
done | shasum -a 256 | awk '{print $1}'
```

The scan emits `WARN: composite-mismatch <slug>` when a stored composite
diverges from this recomputation (covered files all present). It does **not**
yet turn a mismatch into a `MODIFIED` verdict — legacy composites predate this
formula, so a mismatch does not by itself mean the content changed. Recompute
and rewrite the field on the next re-ingest of the page.

## Fields specific to `type: decision` pages

```yaml
status: pending | accepted # mandatory
verdict: null | validated | invalidated | partial # optional, null until reality validates
verdict_date: null | YYYY-MM-DD # optional, must accompany verdict
verdict_evidence: null | "short narrative" # optional, must accompany verdict
```

ADRs without `verdict` after **90 days** are flagged by `/lint` (forces L3 confrontation with reality).

## Optional `revisit_after` field

```yaml
revisit_after: YYYY-MM-DD # on type: decision and type: concept pages
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
