---
description: Save the current session journal to raw/notes/sessions/ for later ingestion
argument-hint: <slug>
---

# /compress-bb

Save the current session journal into `raw/notes/sessions/YYYY-MM-DD-<slug>.md` for later ingestion via `/ingest`.

Use this workflow at the end of a substantive work session: analysis, decisions, explorations, learnings.

## When NOT to use

If the session already produced a substantive `raw/notes/<topic>.md`, don't duplicate the content into a session journal.

| Situation                       | Session journal              | `.pending-ingest`                                      |
| ------------------------------- | ---------------------------- | ------------------------------------------------------ |
| Existing note covers everything | skip                         | `grep -qFx <note> \|\| echo <note> >> .pending-ingest` |
| Note + valuable uncaptured meta | 3-5 line pointer to the note | append the pointer (normal flow)                       |
| No substantive note             | normal flow (steps below)    | normal flow                                            |

The session journal is reserved for meta that would be lost otherwise: scope pivots, tooling friction, verbal decision reasoning. `cache/.session-pending` is orthogonal (SESSION START signal, deleted right after the proposal).

## Steps

### 1. Determine the slug

If `$ARGUMENTS` is provided, use it as the slug (kebab-case, no date).
Otherwise, infer a short and descriptive slug from the themes of the session.

### 2. Build the content

The file must capture what happened during the session, **not the raw history**:

```markdown
---
type: session-journal
date: YYYY-MM-DD
slug: <slug>
themes: [list of themes covered]
---

# Session — <slug> (YYYY-MM-DD)

## Context

<What was ongoing before the session: project state, starting goal.>

## What was done

<List of concrete actions: files created/modified, decisions made, problems solved.>

## Learnings & insights

<What emerged from the session: new understandings, observed patterns, surprises.>

## Open questions

<What remains unclear or to resolve in the next session.>

## Next steps

<Concrete actions identified for follow-up.>
```

### 3. Persist the file (via MCP, fallback to manual paste)

The session journal lives under `raw/notes/sessions/`, which is protected by the `.claude/hooks/protect-raw.sh` `PreToolUse:Write|Edit` hook. Writes from the agent's `Write` or `Edit` tool would be denied. The sanctioned write path is the MCP `drop_to_raw` tool exposed by the `boiling-brain-wiki` server: it writes server-side (bypassing the hook by design) AND appends the relative path to `cache/.pending-ingest` automatically.

**Preferred path — MCP `drop_to_raw`:**

Invoke the tool:

```
drop_to_raw(
  subfolder="notes/sessions",
  filename="YYYY-MM-DD-<slug>.md",
  content=<the full markdown content built in step 2>
)
```

Substitute `YYYY-MM-DD` with today's date and `<slug>` with the slug from step 1. The tool creates `raw/notes/sessions/YYYY-MM-DD-<slug>.md`, appends the relative path to `cache/.pending-ingest`, and returns a confirmation. No separate signal-update step is needed.

**Fallback — manual paste** (only when the `boiling-brain-wiki` MCP server is not connected in the current session, e.g. brand-new vault or temporarily unregistered):

Emit a copy-pastable code block containing the full markdown content (the same body built in step 2), prefixed with this instruction to the user:

```
The boiling-brain-wiki MCP server is not connected in this session.
To persist the journal, copy the block below and write it manually to:
    raw/notes/sessions/YYYY-MM-DD-<slug>.md
Then append the path to cache/.pending-ingest:
    echo "raw/notes/sessions/YYYY-MM-DD-<slug>.md" >> cache/.pending-ingest
```

Followed by a fenced code block containing the journal content (the YAML-frontmatter + body from step 2).

### 4. Confirm to the user

After successful persistence (either path), display:

- The path created: `raw/notes/sessions/YYYY-MM-DD-<slug>.md`.
- A reminder: the file will be proposed for ingestion at the next session start (via the SessionStart hook).
- The manual-ingest shortcut: `/ingest raw/notes/sessions/YYYY-MM-DD-<slug>.md`.

> Note: `/compress-bb` writes only into `raw/notes/sessions/`, which is gitignored
> and never linted by CI. No formatting step is needed here — the session note is
> normalised later, when `/ingest` turns it into `wiki/` pages (which `/ingest`
> formats via `scripts/wiki-maint/format-md.py`).
