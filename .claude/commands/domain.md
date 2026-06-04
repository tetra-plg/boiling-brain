---
description: Manage a vault domain's lifecycle (add/rename/remove) post-bootstrap
argument-hint: <add|rename|remove> <slug> [<new-slug>] [--archive|--purge] [--include-historical] [--audit-migration] [--dry-run]
---

# /domain

Dispatch on the first word of `$ARGUMENTS`:

- `add <slug>` — instantiate (agent + memory + hub) + insert into canonical declarations.
- `rename <old> <new>` — rename everywhere, disambiguating composed slugs, prose words, aliases.
- `remove <slug>` — strip from active surface. `--archive` (default) preserves history; `--purge` sweeps history too.

**Out of scope** (#38): cross-domain source migration, merging, splitting, non-Latin slugs.

## Preliminaries

1. **Context** — cwd must be a vault, not the template. STOP if `CLAUDE.md.tpl` at root. Ensure `template-upstream` remote (fallback `https://github.com/tetra-plg/boiling-brain.git`; configure manually if the vault is from a fork).

2. **Conventions**:
   - **`VAULT_LANGUAGE` cascade** (non-ASCII values and translated keys both possible — bullet is localized at bootstrap: `Langue du vault`, `Idioma del vault`, etc.):
     1. `grep -oE '(Vault language|Langue du vault|Idioma del vault|Sprache des Tresors|Vault言語)[^*]*\*\*[^*]+\*\*' CLAUDE.md` (class `[^*]+` accepts any Unicode value).
     2. Generic fallback: `grep -nE '^\s*-\s*\*\*[^*]+\*\*.*(language|langue|idioma)' CLAUDE.md`.
     3. Still nothing → **`AskUserQuestion`** ("What language is this vault?"). **Never silently default to English** (would render an EN agent in a FR/ES/… vault — cf. #43 review).
     4. Store the value verbatim (`Français`, not `Francais`).
   - `MEMORY_CONVENTION` — observe `.claude/agent-memory/`: `with-suffix` (`<slug>-expert/`) vs `bare`. If mixed, ask + flag Radar item.
   - `EXISTING_DOMAINS` / `EXISTING_AGENTS` — `ls wiki/domains/*.md` / `ls .claude/agents/*-expert.md`.
   - `INGEST_IS_HARDCODED` — `grep -E '(<[a-z-]+-expert>|recommended.*<[a-z-]+>)' .claude/commands/ingest.md`. Default `false` (dynamic dispatch).

3. **Validation patterns** (reused below):
   - **P-all** — `AskUserQuestion` multiSelect, all pre-checked. Mechanical safe substitution.
   - **P-none** — `AskUserQuestion` multiSelect, nothing pre-checked. Sensitive, opt-in.
   - **P-1by1** — `AskUserQuestion` single-select per occurrence. Ambiguous, human judgment required.

---

## add `<slug>`

1. **Interview** (bundled `AskUserQuestion`):
   - `domain_label`, `deliverables_signature` (multiSelect: `cheatsheets`, `syntheses`, `diagrams`, `entities`, `concepts`, `cartographies`), `position` (between which existing pair? conceptual, not alphabetical), `audit_migration?` (yes/no).
   - Free-form follow-up: `summary_l0` (≤140 chars), `summary_l1` (50-150 words), `domain_intro_paragraph`, `taxonomy`, `domain_specific_observation_section` (**authored in `VAULT_LANGUAGE`**, not translated), `trigger_examples`. Optional (empty → drop block): `authority_table_section`, `co_ingest_section`, `confidentiality_section`, `frames_visual_formats`, `hub_pivot_marker`.

2. **Fetch templates** — `git show template-upstream/main:<path>` for `.claude/agents/domain-expert.md.tpl`, `.claude/agent-memory/domain-memory.md.tpl`, `wiki/domains/domain.md.tpl`. STOP on any fetch failure.

3. **Render** — substitute `{{...}}`. Empty optional block alone on a line → remove the line. `{{model}}` / `{{maxTurns}}` / `{{effort}}` inferred from peer agents (`grep -hE '^(model|maxTurns|effort):' .claude/agents/*-expert.md | sort | uniq -c | sort -rn | head -1` per field — pick the dominant value); fallback `claude-sonnet-4-6` if no peer. If `VAULT_LANGUAGE != English`, translate narrative sections; keep technical YAML in EN (`name`, `tools`, `model`, `memory`, `permissionMode`, `maxTurns`, `effort`).

4. **Destinations** (per `MEMORY_CONVENTION`):
   - `.claude/agents/<slug>-expert.md`
   - `.claude/agent-memory/<slug>(-expert)/MEMORY.md`
   - `wiki/domains/<slug>.md`
   - Empty `.claude/agents/<slug>-expert.suggestions.md`.

5. **Insert into canonical declarations**:
   - `CLAUDE.md` — `## User domains` (insert numbered entry at chosen position, **increment downstream numbers** via regex `^(\d+)\. ` → captures + 1) + `## Per-domain expert agents` (same relative position).
   - `README.md`, `wiki/index.md`, `wiki/overview.md` — insert bullet `[[domains/<slug>]] — <summary_l0>` in the matching section.
   - `.claude/commands/ingest.md` — **only if `INGEST_IS_HARDCODED == true`**. Default: skip, dynamic dispatch picks up `<slug>-expert.md` automatically.

6. **`--audit-migration`** (if Yes):
   1. Lexical pre-selection: 8-12 keywords from `summary_l1` + `taxonomy`, `grep -ilE` across `wiki/sources|concepts|entities/*.md`.
   2. **LLM filter pass** (mandatory — without it ~25/30 candidates are lexical false positives, cf. #38): per candidate, evaluate in-context "belongs to `<slug>`? yes/no/uncertain + 1-line justification". Keep confident `yes`.
   3. `AskUserQuestion` multiSelect (max 4 per batch, paginate), pre-check `yes` only. Format option: `<path> — <verdict>: <justification>`.
   4. Edit `domains:` of validated candidates (add `<slug>`, preserve existing).

7. **Validate & apply** — see shared section.

---

## rename `<old>` `<new>`

1. **Pre-validation** — refuse if `<new>` exists (as `wiki/domains/<new>.md` or `.claude/agents/<new>-expert.md`); if `<new>` not `[a-z0-9-]+`; if `<old>` not in `EXISTING_DOMAINS`.

2. **Scan** — `bash scripts/wiki-maint/scan-domain-refs.sh <old>`, bucket the output (field 1).

3. **Per-bucket protocol**:

   | Bucket      | What                                                                                       | Pattern      | Action                                         |
   | ----------- | ------------------------------------------------------------------------------------------ | ------------ | ---------------------------------------------- |
   | CANONICAL   | Slug in the 5 active declarations                                                          | P-all        | Substitute                                     |
   | FRONTMATTER | `domains:` field across `wiki/**/*.md`                                                     | P-all        | Substitute                                     |
   | WIKILINK    | `[[domains/<old>]]` no alias                                                               | P-all        | Substitute                                     |
   | ALIAS       | `[[domains/<old>\|Label]]`                                                                 | P-1by1       | Dialog A                                       |
   | COMPOSED    | Other kebab slugs containing `<old>`                                                       | P-1by1       | Dialog B                                       |
   | PROSE       | Slug word in body. If >30 hits, propose initial P-none group "keep all, uncheck to rename" | P-1by1       | Dialog C                                       |
   | LOGTAG      | Tagging patterns in `wiki/log.md`                                                          | P-none       | Warn: rewriting a log tag = falsifying history |
   | HIST        | Refs in log / decisions / syntheses / sources                                              | Skip default | `--include-historical` → P-none by sub-bucket  |
   | DRIFT       | Numeric counts in prose (`N domains`, `N expert agents`)                                   | —            | Final warning, no auto-fix                     |

   **Dialog A — ALIAS**:

   ```json
   {
     "question": "Alias at <path>:<line> — '[[domains/<old>|<Label>]]'. Action?",
     "options": [
       { "label": "Rename slug + keep label", "description": "[[domains/<new>|<Label>]]" },
       {
         "label": "Rename slug + sync label",
         "description": "[[domains/<new>|<NewLabel>]] (NewLabel derived: capitalize, hyphens → spaces; user-overridable via Other)"
       },
       { "label": "Leave as-is", "description": "Skip this occurrence" }
     ]
   }
   ```

   **Dialog B — COMPOSED**:

   ```json
   {
     "question": "Composed slug '<composed>' at <path>:<line>. Rename?",
     "options": [
       { "label": "Leave as-is", "description": "Separate concept (Recommended)" },
       { "label": "Rename", "description": "<composed> → <new-composed> everywhere" }
     ]
   }
   ```

   **Dialog C — PROSE**:

   ```json
   {
     "question": "Prose at <path>:<line>. Context: '<line>'. Rename?",
     "options": [
       { "label": "Leave as-is", "description": "Natural-language word" },
       { "label": "Rename", "description": "Substitute on this line" }
     ]
   }
   ```

4. **Physical renames** — `mv` for `.claude/agents/<old>-expert.md` (+ `.suggestions[.archive].md` if present), `.claude/agent-memory/<old>${SUFFIX}/`, `wiki/domains/<old>.md`. Inside each renamed file, substitute slug + label references (frontmatter `name:`, `description:`, body).

5. **`CLAUDE.md` position** — ask: keep same numeric position (default) or re-position conceptually.

6. **Validate & apply** — see shared section.

---

## remove `<slug>` [`--archive` (default) | `--purge` | `--include-historical`]

### Pre-validation

Refuse if `<slug>` is the **only domain** (`|EXISTING_DOMAINS| == 1`, cf. BOOTSTRAP.md). Refuse if `<slug>` not in `EXISTING_DOMAINS`.

### `--archive` invariant — STRICT

The only files physically deleted are Phase 4's exhaustive list (agent, memory dir, hub). **No other file deletion** in `--archive` mode. Content pages (`wiki/sources|concepts|entities|decisions|syntheses/`) are **edited** (frontmatter `domains:` strip) or have **lines removed** (B3/B4 orphan wikilinks). If a content page becomes orphan (`domains: []` after strip), deletion is **opt-in case-by-case** via the orphan dialog — never in batch, never pre-checked.

If you catch yourself proposing batch deletion of content pages → abort, rebuild plan.

### Per-bucket by mode

| Mode                   | B1-B4                                | B5/B6/B7                       | B8 HIST                                                                 | B9            |
| ---------------------- | ------------------------------------ | ------------------------------ | ----------------------------------------------------------------------- | ------------- |
| `--archive` (default)  | Edit (line / frontmatter / wikilink) | Skip silent → final warnings   | Fully preserved, no prompt                                              | Final warning |
| `--include-historical` | Same as archive                      | Same                           | P-none by sub-bucket, action = edit (not delete)                        | Same          |
| `--purge`              | Same as archive                      | P-1by1 (delete the occurrence) | Implies `--include-historical`; page deletion stays opt-in case-by-case | Same          |

**B2 FRONTMATTER — two steps**:

- _Step 1_: P-all, remove `<slug>` from each `domains:` list (keep others). B8 HIST pages **excluded in `--archive`** (their frontmatter untouched).
- _Step 2 — orphan dialog_ (one-by-one, never batch, never pre-checked):

  ```json
  {
    "question": "Page <path> orphan (domains: []) after removing <slug>. Action?",
    "options": [
      { "label": "Re-tag", "description": "Pick another domain from EXISTING_DOMAINS" },
      {
        "label": "Leave orphan",
        "description": "domains: [] — page stays, flagged by /lint (Recommended)"
      },
      {
        "label": "Delete the page",
        "description": "Explicit opt-in — only for mono-domain pure-description pages"
      }
    ]
  }
  ```

  If >3 orphans, present in alphabetical path order — user can answer "Leave orphan" rapidly.

### Phase 4 — Physical deletions (exhaustive)

```bash
rm .claude/agents/<slug>-expert.md
rm -f .claude/agents/<slug>-expert.suggestions.md .claude/agents/<slug>-expert.suggestions.archive.md
rm -rf .claude/agent-memory/<slug>${SUFFIX}/
rm wiki/domains/<slug>.md
```

Opt-in deletions (orphan content pages from B2 step 2, B8 pages under `--include-historical`/`--purge`) are journaled separately in the final report as `Content pages deleted (opt-in)`, distinct from `Domain files deleted (Phase 4)`.

### `CLAUDE.md` renumbering

Renumber downstream entries in `## User domains`.

---

## Validate & apply (shared)

1. **Scan** — read-only, produces a change plan.
2. **Preview** — show: global summary (vault, sub, slug, bucket counters), physical renames, modified files grouped by bucket, warnings (B9, skipped B5/B6/B7 in `--archive`).
3. **Final validation** — `AskUserQuestion`: `Apply` / `Apply (dry-run, list shell commands only)` / `Abort (keep plan in /tmp)`.
4. **Apply order** — physical renames → physical deletions → content edits → file creations. On mid-way failure: log error, **do not continue**, suggest `git status` checkpoint, plan kept at `/tmp/domain-plan-<timestamp>.txt`.
5. **Journal** — append to `wiki/log.md`:

   ```
   ## [YYYY-MM-DD] domain | <sub> <slug>[ → <new>]

   <N> files touched. Buckets: <B1:N1, B2:N2, …>. Warnings: <…>.
   ```

6. **Final report** — counters touched/skipped per bucket, untreated warnings, suggested next step (`/ingest raw/...` after add; `/lint` after rename/remove).

---

## Principles

- **History is sacred** — `wiki/log.md`, `decisions/`, `syntheses/`, `sources/` never rewritten by default. Opt-in via `--include-historical` / `--purge`.
- **Ambiguity → human** — composed slugs, prose words, aliases are never auto-rewritten.
- **Idempotence** — re-running on an already-applied state produces an empty/minimal plan and says so.
- **Don't touch dynamic dispatch** — adding/removing `<slug>-expert.md` in `.claude/agents/` is enough; only edit `.claude/commands/ingest.md` if `INGEST_IS_HARDCODED == true`.
