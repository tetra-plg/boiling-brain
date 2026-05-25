# MCP tiered-loading layer

> Reference for the `boiling-brain-wiki` MCP server's 12 tools and the tiered-loading pattern they implement. Added in v1.1.0 (refactor #41).

## Why tiered loading

A flat `scan_domain("ia")` on a 388-page domain returns ~23k tokens — too much for context-constrained backends (e.g. a Realtime voice agent against a 40k TPM org limit, or smaller models with tight context budgets). The MCP server now exposes a **hierarchical descent**: orient first, then drill into the right type, then read the matching pages. Measured reduction on the same query path: **~96%** (23k → ~900 tokens for the orientation step).

## The 12 tools

```
┌─ Orientation ──────────────────────────────────────────────────────┐
│  scan_domain(domain)                                               │
│    → hub summary_l1 + counts per type + top 10 by centrality       │
│    → ~860 tokens, replaces the old "dump all pages" behaviour      │
└────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─ Drill-down per type (7 tools, uniform signature) ─────────────────┐
│  scan_concepts(domain, query="", top=20)                           │
│  scan_entities(domain, query="", top=20)                           │
│  scan_decisions(domain, query="", top=20)                          │
│  scan_syntheses(domain, query="", top=20)                          │
│  scan_cheatsheets(domain, query="", top=20)                        │
│  scan_diagrams(domain, query="", top=20)                           │
│  scan_sources(domain, query="", top=20)  [query REQUIRED]          │
│                                                                    │
│    Without query: top N pages of that type ranked by centrality    │
│    With query:    case + separator-insensitive token filter,       │
│                   ranked by centrality (tie-breaker)               │
│    Format:        "- <slug> — <summary_l0>" (type implicit)        │
└────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─ Page-level tiered loading (existing, unchanged) ──────────────────┐
│  preview_page(page_path)  → frontmatter + summary_l1 (L1)          │
│  read_page(page_path)     → full body (L2)                         │
└────────────────────────────────────────────────────────────────────┘

┌─ Cross-coupe ──────────────────────────────────────────────────────┐
│  search_wiki(query, limit=10)                                      │
│    Cross-type, cross-domain. Format enriched per result:           │
│    "<path> (<type>) — <summary_l0> — wikilinks: [<slugs>]"         │
│    Token-tokenised + ranked by centrality. Default limit=10,       │
│    wikilinks capped at 3 per result (gates ~671 tokens).           │
└────────────────────────────────────────────────────────────────────┘

┌─ Write side ───────────────────────────────────────────────────────┐
│  drop_to_raw(subfolder, filename, content)                         │
│    Sanctioned write into raw/ (bypasses protect-raw.sh PreToolUse  │
│    hook by writing server-side). Auto-updates cache/.pending-ingest│
└────────────────────────────────────────────────────────────────────┘
```

## Recommended usage pattern

For a natural-language query (typical voice or chat usage):

1. **Orient** with `scan_domain(domain)` — get the hub summary, see what types exist, pick the most relevant `scan_<type>` for the next step. ~860 tokens.
2. **Drill** with `scan_<type>(domain, query="<topic>")` — get the top 20 pages of that type matching the query, ranked by centrality. ~500-800 tokens.
3. **Preview** with `preview_page(<path>)` on the 1-3 most promising pages — read the L1 summary. ~300 tokens each.
4. **Read** with `read_page(<path>)` only when the L1 confirms relevance — full body. Variable, often 2-10k tokens.

Total typical session: **2-3k tokens**, sometimes 5k if the L2 read is mandatory. Compare to the pre-refactor ~23k just for the orientation step alone.

For a cross-domain or unscoped query, use `search_wiki(query)` instead of `scan_domain` — same tokenisation, returns up to 10 enriched results with outgoing wikilinks for the next hop.

## Centrality ranking (backlinks)

`scan_<type>` and `search_wiki` both rank results by **centrality** = number of incoming wikilinks (`[[slug]]` patterns) targeting the page across the whole wiki. Implementation:

- Helper `_compute_centrality(page_path)` lazy-builds a single backlink index per process (one full wiki scan), cached in module-level state.
- Counts both full-slug references (`[[concepts/foo]]`) and bare-slug references (`[[foo]]`) when the slug is unique.
- No external dependency — pure regex scan of all markdown files.

Why centrality? On a well-linked wiki, the most-referenced pages are the most-central concepts. Empirically, on BoilingBrain: `concepts/model-context-protocol` (114 backlinks) ranks above `concepts/some-obscure-detail` (2 backlinks) for a query on "MCP", which matches user intent.

## Matching (tokenised + normalised)

`scan_<type>(query)` and `search_wiki(query)` both use:

- **`_normalize_query(q)`**: lowercase + NFC + split on whitespace and hyphens, drop empties.
- **`_normalize_haystack(text)`**: same lowercase + NFC + collapse hyphens and whitespace into single spaces.
- **`_all_tokens_present(tokens, haystack)`**: AND-match (every token must be a substring).

Result: `"two words"`, `"two-words"`, and `"twowords"` all match the same content. Case-insensitive throughout.

Haystack composition for each page: `summary_l0 + summary_l1 + filename + body`.

## Special case: `scan_sources`

Source pages are typically too numerous (~133 sources on BoilingBrain `ia`) to enumerate usefully without a target. `scan_sources(domain)` without a query returns a refusal message with the count and a pointer to `scan_domain` or `scan_concepts` for orientation. The tool description signals this explicitly to Claude Code, so the agent learns to provide a query.

## Smoke test

`scripts/mcp/smoke_test.py` is a standalone harness that invokes every MCP tool against a real vault and asserts per-tool token budgets. Used as the v1.1.0 gate before tagging.

```bash
WIKI_PATH=/path/to/vault python3 scripts/mcp/smoke_test.py [domain]
# Default domain: ia
```

Output format (machine-parseable):

```
[OK]   scan_domain: 3453 chars (~863 tokens, cap 1500)
[OK]   scan_concepts (query): 296 chars (~74 tokens, cap 800)
[FAIL] search_wiki: 825 chars (~206 tokens, cap 800)
...
All gates passed.   ← or "N gate(s) failed:" + exit 1
```

Re-run after any non-trivial change to `mcp-wiki.py` to catch token-budget regressions.

## Per-vault customisation

The 7 `scan_<type>` tools assume the standard frontmatter `type:` values: `concept`, `entity`, `decision`, `synthesis`, `cheatsheet`, `source`, `diagram`. If your vault uses additional or different types, edit `_TYPE_TOOL_TO_FRONTMATTER` in `scripts/mcp/mcp-wiki.py` and add the corresponding `@mcp.tool` wrapper.

The hub page lookup uses `wiki/domains/<domain>.md` and reads its `summary_l1`. Vaults without a `wiki/domains/` directory will get a `scan_domain` output with empty hub but still functional counts + top-N sections.

## Backward compatibility

- **scan_domain** : format changed (was a flat list of all pages, now hierarchical). Consumers parsing the old `[path] (type, date) — l0` format must migrate. Token reduction: ~96%.
- **search_wiki** : format changed (was `path:line: extract`, now `path (type) — l0 — wikilinks: [...]`). Consumers parsing the old format must migrate.
- **preview_page, read_page, drop_to_raw** : unchanged.
- **7 new `scan_<type>` tools** : auto-discovered by Claude Code at session start via the MCP `tools/list` request. The LLM instructions block in `~/.claude/CLAUDE.md` (written by `setup-mcp.sh`) documents the usage pattern.

## Related artefacts

- `scripts/mcp/mcp-wiki.py` — server implementation (FastMCP stdio).
- `scripts/mcp/setup-mcp.sh` — installer + self-healing maintainer of `~/.claude/CLAUDE.md` block.
- `scripts/mcp/smoke_test.py` — token-budget harness.
- `scripts/migrations/v1.1.0.md` — migration that installs/refreshes the stack. Marked `force-rerun: true` to re-evaluate at every `/update-vault`.
