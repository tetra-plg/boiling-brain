---
description: Consume the accumulated suggestions of an expert agent and propose an evolution of its system prompt
argument-hint: <domain>
---

Run EVOLVE-AGENT workflow on domain: $ARGUMENTS

Evolve the prompt of the expert agent `$ARGUMENTS-expert` from the suggestions it itself surfaced during its ingests.

## Steps

### 1. Read the materials

- **Current prompt**: `.claude/agents/$ARGUMENTS-expert.md`.
- **Accumulated suggestions**: `.claude/agents/$ARGUMENTS-expert.suggestions.md` (append-only, timestamped by `/ingest`).
- **Previous archive** (if it exists): `.claude/agents/$ARGUMENTS-expert.suggestions.archive.md` — to see what's already been integrated in the past.
- **Operational memory** (read-only, for context): `.claude/agent-memory/$ARGUMENTS/MEMORY.md` and `.claude/agent-memory/$ARGUMENTS/patterns_pending.md` if they exist. These document the project state — use them to disambiguate suggestions but **do not modify** them.

If the suggestions file doesn't exist or is empty → tell the user, suggest they trigger one or more domain ingests first.

### 2. Analyze

For each accumulated suggestion:

- Classify: **recurring pattern** (≥2 occurrences) / **blind spot** / **prompt proposal** / **deliverable proposal**.
- Deduplicate equivalent suggestions.
- Filter: keep what's **recurring** or **clearly structural**. Discard isolated anecdotal items (but don't archive them — they may become recurring later).

### 3. Propose a revision diff

Present a **concise revision plan** to the user:

- List of suggestions kept (and why).
- List of suggestions discarded for this iteration (with reason).
- **Proposed diff** on `.claude/agents/$ARGUMENTS-expert.md`: sections added, modified, removed.
- Expected impact on next ingests (in 2-3 lines).

Ask for validation via `AskUserQuestion` with options:

- **Apply the diff** (default option if relevant).
- **Modify** (user specifies what should change).
- **Defer** (do nothing, suggestions stay pending).

### 4. Apply (if validated)

1. Edit `.claude/agents/$ARGUMENTS-expert.md` per the diff.
2. Move integrated suggestions from `.suggestions.md` to `.suggestions.archive.md`. Prefix each archived block with `### [YYYY-MM-DD] evolve → version <n>`. Don't lose discarded suggestions — they stay in `.suggestions.md`.
3. Append an entry to `wiki/log.md`:
   ```
   ## [YYYY-MM-DD] evolve | $ARGUMENTS-expert
   System prompt revision from <N> suggestions. Kept: <summary>. Discarded: <short summary>. Archive: `.claude/agents/$ARGUMENTS-expert.suggestions.archive.md`.
   ```
4. Tell the user the agent will be updated at the next session start (subagents are loaded at boot).

### 5. Final report

- Number of suggestions read / kept / deferred / archived.
- Path of the updated agent file.
- Recommended next step (e.g. re-run `/ingest` on a recent source to validate the improvement).

## Principles

- **Human curation, not silent self-modification** — the agent proposes, the user validates.
- **No regression**: the diff respects the existing structure (frontmatter, sections, tone). We add or refine, we don't refactor without reason.
- **Traceability**: every evolution is logged, every integrated suggestion is archived with its date and origin.

## Final step — normalise markdown

After all pages are written/updated, format the produced markdown so it stays
consistent and the CI `format-check` job passes:

```bash
npx -y prettier --write ".claude/agents/**/*.md" "wiki/**/*.md"
```
