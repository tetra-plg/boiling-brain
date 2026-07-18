# Agent output contract

Every expert agent invoked by `/ingest` returns **three parsable markdown blocks** at the end of its turn (a read-side delegation returns a single block instead — see **Read-side delegation contract** below). The main context reads these blocks and writes the downstream files. **The agent never writes to `wiki/log.md`, `wiki/radar.md`, or `.claude/agents/*.suggestions.md` directly.**

## Three blocks

```markdown
## Ingest summary

- Pages created: [[wiki/sources/...]], [[wiki/concepts/...]], …
- Pages updated: …
- Deliverables produced: …
- Contradictions detected: …
- Cross-domain: […]

## Radar items

- Specific observations attached to a named source / timestamp / project.
- Missing facts ("what is the exact value of X?").
- "If 2nd occurrence of X, create concept Y" (threshold not met).
- Content gaps to fill via a future ingest.

## Evolution suggestions

- Concept broadened to the domain (derived from a specific observation).
- Behavioral rule applicable to any future ingest **independent of the content**.
- Structural blind spot of the prompt.
- "N/A" if nothing notable — default encouraged.
```

## Conceptual derivation rule (core)

For every specific observation, apply the **double jump**:

1. **Broadened concept?** → `## Evolution suggestions` (transverse rule)
2. **Specific detail not covered by this ingest?** → `## Radar items` (to investigate)

**Decisive test** for `Evolution suggestions`: _"Would this rule still hold if the source was about another actor in the domain?"_ If no → not transverse → `Radar items`.

## Examples

**Valid Evolution suggestion** (transverse): "Future ingests of LLM provider docs should systematically capture context window, pricing tier, and reasoning configurability."

**Invalid** (specific): "Anthropic Opus 4.7 has a 1M context window." → goes to `## Radar items` (mention of a specific actor).

## Read-side delegation contract

Beyond ingest, an expert can be delegated a **read-side** task by a workflow command (`/radar`, `/lint`, `/query`) — but only when it needs **domain judgment**, not a plain fact lookup. The same discipline as ingest applies: **the agent reads `wiki/` but never writes to it** (no edit to radar / log / index / pages). It **returns one parsable block**; the main context applies the outcome.

The delegating command states the **mode** and supplies the input (a radar slice, a lint scope, or a question). The agent grounds its judgment in its **Domain orientation** (tiered-loading CLI, cf. #71) and its **`.claude/agent-memory/<domain>/MEMORY.md`**, and cites `[[page]]` for every claim.

### Radar-triage → `## Triage recommendations`

One line per radar entry handed to the agent, prefixed with a verb:

```markdown
## Triage recommendations
- [close] **[Domain · YYYY-MM-DD]** <entry> — <why resolved>. → [[page]]
- [merge] **[Domain · YYYY-MM-DD]** <entry> — duplicate of <other>. → [[other]]
- [defer] **[Domain · YYYY-MM-DD]** <entry> — still open, revisit after <trigger>.
- [keep]  **[Domain · YYYY-MM-DD]** <entry> — valid, no action.
```

Verb set: `close` (resolved), `merge` (fold into another entry/page), `defer` (keep + note the trigger), `keep` (valid, unchanged). The agent never edits `wiki/radar.md`.

### Semantic lint → `## Semantic findings`

```markdown
## Semantic findings
- [contradiction] [[page-a]] vs [[page-b]] — <what conflicts>.
- [stale-claim] [[page]] — <claim> looks outdated vs <source/date>.
- [missing-concept] "<concept>" mentioned in [[page]] with no page (threshold met? note it).
- [missing-xref] [[page-a]] should link [[page-b]] — <why>.
- [data-gap] <topic> under-documented — candidate source: <pointer>.
```

Structural checks (orphans, missing raw sources, broken wikilinks, `revisit_after`) are **not** the agent's job — they stay deterministic in the main/script pass.

### Delegated query → `## Query answer`

```markdown
## Query answer
<answer grounded in the domain, with [[page]] citations. State explicitly if partial due to missing sources.>
```

The main context relays the answer and offers `/save` if substantial.
