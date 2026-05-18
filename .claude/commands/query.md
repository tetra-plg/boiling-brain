---
description: Query the wiki to answer a question from indexed pages, with citations and optional synthesis archiving
argument-hint: <question>
---

Run the QUERY workflow from CLAUDE.md on: $ARGUMENTS

## Tiered loading — reading strategy

Read as little as possible to answer accurately. Descend levels in order:

**L0 — scan**: `summary_l0` of each candidate page (frontmatter field, ≤140 chars).
**L1 — preview**: `summary_l1` (frontmatter, 2-5 sentences) if L0 isn't enough to discriminate.
**L2 — full body**: full content only for pages confirmed relevant by L1.

## Steps

1. Identify the domain(s) of the question (one or more of the domains declared in `wiki/index.md`, or cross-domain).
2. Build the candidate-page list:
   - Per identified domain: `grep -rl "domains:.*<domain>" wiki/`
   - If several domains: run one grep per domain and deduplicate (`sort -u`).
   - Don't rely on `wiki/index.md`: it may be incomplete.
3. **L0**: read the `summary_l0` of the candidates (frontmatter only).
   - If the answer is clear from L0 → answer directly with citations.
   - Otherwise: pick the pages needing deeper inspection.
4. **L1**: read the `summary_l1` of the selected pages. If sufficient → answer. Otherwise → L2.
5. **L2**: read the full body of the retained pages. Follow `[[wikilinks]]` only if essential.
6. Synthesize the answer with `[[page]]` citations. Explicitly mention if the answer is partial due to missing sources.
7. If the answer is substantial (>200 words, usable outside this session), suggest archiving it via `/save <slug>`.
8. Append to `wiki/log.md`: `## [YYYY-MM-DD] query | <short question>`.
