# Agent output contract

Every expert agent invoked by `/ingest` returns **three parsable markdown blocks** at the end of its turn. The main context reads these blocks and writes the downstream files. **The agent never writes to `wiki/log.md`, `wiki/radar.md`, or `.claude/agents/*.suggestions.md` directly.**

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
