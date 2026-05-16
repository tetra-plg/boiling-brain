---
description: Save the current session journal to raw/notes/sessions/ for later ingestion
argument-hint: <slug>
---

# /compress-bb

Save the current session journal into `raw/notes/sessions/YYYY-MM-DD-<slug>.md` for later ingestion via `/ingest`.

Use this workflow at the end of a substantive work session: analysis, decisions, explorations, learnings.

## When NOT to use

If the session already produced a substantive `raw/notes/<topic>.md`, don't duplicate the content into a session journal.

| Situation | Session journal | `.pending-ingest` |
|-----------|-----------------|-------------------|
| Existing note covers everything | skip | `grep -qFx <note> \|\| echo <note> >> .pending-ingest` |
| Note + valuable uncaptured meta | 3-5 line pointer to the note | append the pointer (normal flow) |
| No substantive note | normal flow (steps below) | normal flow |

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

### 3. Write the file

```
raw/notes/sessions/YYYY-MM-DD-<slug>.md
```

### 4. Update the pending-ingest signal

Add the path to `cache/.pending-ingest` (create the file if absent):

```
raw/notes/sessions/YYYY-MM-DD-<slug>.md
```

### 5. Confirm to the user

Show the path created and remind:
- The file will be proposed for ingestion at the next session start (via the SessionStart hook).
- Manual ingestion is available immediately: `/ingest raw/notes/sessions/YYYY-MM-DD-<slug>.md`.
