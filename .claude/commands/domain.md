---
description: Manage a vault domain's lifecycle (add/rename/remove) post-bootstrap
argument-hint: <add|rename|remove> <slug> [<new-slug>] [--archive|--purge] [--include-historical] [--audit-migration] [--dry-run]
---

# /domain

Manage a domain's lifecycle in a BoilingBrain vault **after the initial bootstrap**. The command dispatches on the first word of `$ARGUMENTS`:

- `/domain add <slug>` — instantiate a new domain (agent, memory, hub) and insert it into every canonical declaration.
- `/domain rename <old-slug> <new-slug>` — rename a domain everywhere, disambiguating tricky cases (composed slugs, prose word, wikilink aliases).
- `/domain remove <slug>` — strip a domain from the vault's active surface. `--archive` (default) preserves history; `--purge` proposes case-by-case sweeps through history too.

**Out of scope** (cf. issue #38): cross-domain source migration between existing domains, domain merging, domain splitting, non-Latin slugs.

## Preliminaries (always)

Before any dispatch:

### 1. Verify the context

- The cwd must be the root of an instantiated vault (not the template repo). If `CLAUDE.md.tpl` exists at the root → STOP, explain to the user that the command only runs inside a cloned vault.
- The `template-upstream` remote must be configured (otherwise the `.tpl` fetch for `add` fails):

  ```bash
  git remote get-url template-upstream 2>/dev/null || {
    git remote add template-upstream https://github.com/tetra-plg/boiling-brain.git
    git fetch template-upstream --tags
  }
  ```

  The fallback URL points to the official template `tetra-plg/boiling-brain`. If the vault was bootstrapped from a **fork**, configure `template-upstream` manually toward the fork before running `/domain add` (otherwise the `.tpl` files will come from the official template, not the fork).

### 2. Detect the vault's conventions

Capture into variables, to reuse below:

- **`VAULT_LANGUAGE`**: the value can be non-ASCII (`Français`, `Español`, `Deutsch`, `日本語`…) **and** the key can be translated (the bullet is localized at bootstrap time: `Langue du vault` in FR, `Idioma del vault` in ES, etc.). Detection cascade:
  1. `grep -oE '(Vault language|Langue du vault|Idioma del vault|Sprache des Tresors|Vault言語)[^*]*\*\*[^*]+\*\*' CLAUDE.md` — covers known labels; the value class `[^*]+` allows any Unicode character between the `**`.
  2. If nothing matched, generic fallback: `grep -nE '^\s*-\s*\*\*[^*]+\*\*.*language|^\s*-\s*\*\*[^*]+\*\*.*langue|^\s*-\s*\*\*[^*]+\*\*.*idioma' CLAUDE.md`.
  3. If still nothing, **ask the user** via `AskUserQuestion` ("What language is this vault written in?") instead of silently defaulting to `English` (which would render an EN agent inside a FR/ES/… vault). Cf. issue #43 review: silent fallback was the bug detected during the `/update-vault` test on BB.
  4. Store the value exactly as found (preserve `Français`, not `Francais`).
- **`MEMORY_CONVENTION`**: list `.claude/agent-memory/` and observe whether subdirectories have the `-expert` suffix or not.
  - If `.claude/agent-memory/<slug>-expert/` exists for ≥1 domain → convention `with-suffix`.
  - If `.claude/agent-memory/<slug>/` (no suffix) → convention `bare`.
  - If mixed → ask the user via `AskUserQuestion` which convention to apply (and flag a Radar item for future consistency).
- **`EXISTING_DOMAINS`**: `ls wiki/domains/*.md` filtered, excluding any non-domain hubs (prefix `_`). A domain's slug = basename minus `.md`.
- **`EXISTING_AGENTS`**: `ls .claude/agents/*-expert.md` (the `-expert.md` suffix is required for `/ingest`'s dynamic dispatch).
- **`INGEST_IS_HARDCODED`**: `grep -E '(<[a-z-]+-expert>|recommended.*<[a-z-]+>)' .claude/commands/ingest.md`. If the grep finds an explicit mapping → `true`. Default since bootstrap: `false` (dynamic dispatch, cf. ingest.md L48 "propose one or more expert agents from those present in .claude/agents/").

### 3. Dispatcher

Parse `$ARGUMENTS`:

```
<sub> <slug> [<new-slug>] [--flags...]
```

`<sub>` ∈ {`add`, `rename`, `remove`}. If missing or invalid → print usage and stop. Everything else is passed to the corresponding subsection.

---

## Sub-command: `add <slug>`

### Phase 1 — Interactive interview

Bundle the questions into **a single `AskUserQuestion` call** (max 4 questions; optional fields as conditional follow-ups).

Pass 1 questions (4 questions, single-select unless stated otherwise):

1. **Domain label** (free-form, e.g. `Astrophysics`, `Mental Performance`).
2. **Deliverables signature** (multiSelect among: `cheatsheets`, `syntheses`, `diagrams`, `entities`, `concepts`, `cartographies`). The issue highlights the multi-deliverable case (e.g. `cheatsheets + syntheses`).
3. **Position in `CLAUDE.md`'s list** (single-select): "insert between **<slug-i>** and **<slug-i+1>**" for each adjacent pair from `EXISTING_DOMAINS`, plus the "at the end" option. The issue is explicit: insertion is conceptual, not alphabetical.
4. **Audit migration?** (`Yes` / `No, later`) — triggers the `--audit-migration` pass after rendering.

Pass 2 (free-form text input, not via `AskUserQuestion`):

- `summary_l0` (≤140 chars).
- `summary_l1` (structured paragraph, 50-150 words).
- `domain_intro_paragraph` (1-2 sentences at the top of the hub).
- `taxonomy` (initial sub-themes, e.g. bulleted list).
- `domain_specific_observation_section` (free-form list of angles the agent should look for in a source of the domain — **authored in `VAULT_LANGUAGE`**, not translated from a placeholder).
- `trigger_examples` (typical visual triggers for frames, e.g. `result tables, architecture diagrams`).
- *Optional — leave empty to omit the corresponding blocks*: `authority_table_section`, `co_ingest_section`, `confidentiality_section`, `frames_visual_formats` (override the default), `hub_pivot_marker` (marker if this hub is the vault's pivot).

### Phase 2 — Fetch the upstream templates

```bash
git fetch template-upstream --tags
TPL_AGENT=$(git show template-upstream/main:.claude/agents/domain-expert.md.tpl)
TPL_MEMORY=$(git show template-upstream/main:.claude/agent-memory/domain-memory.md.tpl)
TPL_HUB=$(git show template-upstream/main:wiki/domains/domain.md.tpl)
```

If any `git show` fails → STOP, explain that the upstream template isn't reachable.

### Phase 3 — Rendering

Substitute the `{{...}}` placeholders:

- `{{domain_slug}}` → `<slug>` argument.
- `{{domain_label}}` → interview answer.
- `{{bootstrap_date}}` → today's date `YYYY-MM-DD`.
- `{{summary_l0}}`, `{{summary_l1}}`, `{{domain_intro_paragraph}}`, `{{taxonomy_section}}`, `{{domain_specific_observation_section}}`, `{{trigger_examples}}` → interview answers.
- `{{deliverables_signature_block}}` → generate a multi-line block listing each chosen deliverable with a short descriptive sentence (e.g. `One cheatsheet `wiki/cheatsheets/<topic>.md` per sub-theme — synthesis tables, thresholds, matrices.`).
- `{{authority_table_section}}`, `{{co_ingest_section}}`, `{{confidentiality_section}}`, `{{frames_visual_formats}}`, `{{hub_pivot_marker}}`, `{{related_domains_section}}` → leave empty if the user provided nothing. If the placeholder appears alone on a line → remove the whole line.
- `{{model}}` → `claude-sonnet-4-6` (template default) unless the user overrides.
- `{{maxTurns}}`, `{{effort}}` → default values observed in existing agents (`grep -h '^maxTurns:\|^effort:' .claude/agents/*-expert.md | sort -u`).
- `{{vault_language}}` → detected `VAULT_LANGUAGE`.

If `VAULT_LANGUAGE != English`, translate the narrative sections of the rendered template (prompt body, descriptions, hub intro) while keeping the technical YAML fields in English (`name`, `tools`, `model`, `memory`, `permissionMode`, `maxTurns`, `effort`).

### Phase 4 — Destination paths

Consistent with the detected conventions:

| Rendered source | Destination |
|---|---|
| `TPL_AGENT` rendered | `.claude/agents/<slug>-expert.md` |
| `TPL_MEMORY` rendered | `.claude/agent-memory/<slug>(-expert)/MEMORY.md` per `MEMORY_CONVENTION` |
| `TPL_HUB` rendered | `wiki/domains/<slug>.md` |

Also create an empty `.claude/agents/<slug>-expert.suggestions.md` (will be filled by `/ingest`, then consumed by `/evolve-agent`).

### Phase 5 — Insertion into the canonical declarations

For each file: **read** it, **compute the patch**, **show the preview**, then apply after global validation (cf. "Validation & application" section).

- **`CLAUDE.md`**:
  - `## User domains` section: insert a new numbered entry at the position chosen in Phase 1. **Increment by 1 the number of every entry downstream of the insertion** (regex `^(\d+)\. ` → captures + 1).
  - `## Per-domain expert agents` section: insert the line `- \`<slug>-expert\` — deliverables: <deliverables summary>. <signature one-liner>.` at the same relative position.
- **`README.md`**: if a "Domains" table or bullet list exists, insert the line. Otherwise log a warning "README has no domain table detected, edit manually".
- **`wiki/index.md`**: `## Domains` or `## Domaines` section, insert the line `- [[domains/<slug>]] — <summary_l0>`.
- **`wiki/overview.md`**: section listing domains, insert a similar line.
- **`.claude/commands/ingest.md`**: if `INGEST_IS_HARDCODED == false`, **do not touch** — dynamic dispatch will automatically find `<slug>-expert.md` on the next `/ingest`. If `true` (vault that customized its ingest.md), locate the mapping and add an entry; log a warning.

### Phase 6 — `--audit-migration` (if requested)

Goal: identify existing sources / concepts / entities that actually belong to the new domain and should be re-tagged.

Two-pass pipeline (cf. issue #38: the second-pass LLM filter is mandatory — without it, ~25/30 candidates are lexical false positives):

1. **Lexical pre-selection**: extract 8-12 keywords from `summary_l1` + `taxonomy_section` (words ≥4 chars, lowercase, FR/EN stopwords excluded). `grep -ilE '(\bword1\b|\bword2\b|…)' wiki/sources/*.md wiki/concepts/*.md wiki/entities/*.md` → candidates list.
2. **LLM filter**: for each candidate, read its frontmatter (full `summary_l1`) + its current `domains:`. Evaluate in-context (no agent spawn): "Does this candidate belong to the `<slug>` domain? Give a verdict among `yes`, `no`, `uncertain` with a one-line justification." Keep only confident `yes` for the pre-selection; `uncertain` can be presented in a second batch.

3. **User presentation**: `AskUserQuestion` multiSelect, pre-checked only the `yes`, listing `<path> — <verdict>: <justification>` per option (max 4 per batch, paginated successively if >4 candidates).

4. **Application**: for each validated candidate, edit the frontmatter's `domains:` to add `<slug>` (preserving existing domains).

### Phase 7 — Final validation + apply

Cf. shared "Validation & application" section.

---

## Sub-command: `rename <old-slug> <new-slug>`

### Phase 1 — Pre-validation

- Refuse if `<new-slug>` already exists as a domain (`wiki/domains/<new-slug>.md` present OR `.claude/agents/<new-slug>-expert.md` present) → STOP, ask the user to pick another slug or to `remove` first.
- Refuse if `<new-slug>` is not in `[a-z0-9-]+` (strict kebab-case ASCII — explicitly out of scope: non-Latin).
- Refuse if `<old-slug>` does not exist in `EXISTING_DOMAINS`.

### Phase 2 — Exhaustive scan

```bash
bash scripts/scan-domain-refs.sh <old-slug> > /tmp/scan-rename.txt
```

Bucket the output by reading each line (field 1 = bucket).

### Phase 3 — Per-bucket presentation

Present the **global summary** first (per-bucket counters), then ask bucket by bucket. No bulk validation — each category has its own protocol.

#### `B1 CANONICAL` (active declarations)

`AskUserQuestion` Pattern D (file selection, multiSelect, **all pre-checked**). Description per file: occurrence count and 1-2 example lines. The user can uncheck if an occurrence looks suspicious.

#### `B2 FRONTMATTER` (`domains:` field)

`AskUserQuestion` Pattern D, **all pre-checked**. Mechanical substitution, safe — this is metadata, not prose.

#### `B3 WIKILINK` (`[[domains/<old>]]` without alias)

`AskUserQuestion` Pattern D, **all pre-checked**. Substitution `[[domains/<old>]]` → `[[domains/<new>]]`.

#### `B4 ALIAS` (`[[domains/<old>|Label]]`)

**One by one**. For each alias:

```json
{
  "question": "Wikilink alias at <path>:<line> — '[[domains/<old>|<Label>]]'. What do you want?",
  "options": [
    {"label": "Rename slug + keep label", "description": "[[domains/<new>|<Label>]] — useful if the label was deliberately different"},
    {"label": "Rename slug + sync label", "description": "[[domains/<new>|<NewLabel>]] — useful if the label tracked the slug"},
    {"label": "Leave as-is", "description": "Skip this occurrence"}
  ]
}
```

`<NewLabel>` is derived from `<new>` (Capitalize first, hyphens → spaces). The user can override via "Other".

#### `B5 COMPOSED` (composed slugs)

**One by one**. For each candidate (e.g. `equipe-agents-roles-<old>`):

```json
{
  "question": "Composed slug at <path>:<line> — '<composed>'. Contains '<old>' but looks like a standalone identifier. Rename?",
  "options": [
    {"label": "Leave as-is", "description": "<composed> is a separate concept (Recommended)"},
    {"label": "Rename", "description": "Substitute <old> → <new> inside <composed> → <new-composed>"}
  ]
}
```

If the user picks "Rename", apply the substitution to every occurrence (filename + references) of that composed slug.

#### `B6 PROSE` (word in body text)

**One by one** with one line of context. For each hit:

```json
{
  "question": "Prose occurrence at <path>:<line>. Context: '<line content>'. Rename?",
  "options": [
    {"label": "Leave as-is", "description": "Natural-language word, not the slug"},
    {"label": "Rename", "description": "Substitute <old> → <new> on this line"}
  ]
}
```

To limit noise: if >30 PROSE hits, propose an initial grouped batch "keep everything by default, I uncheck the ones to rename" (Pattern D, **nothing pre-checked**).

#### `B7 LOGTAG`

Sensitive bucket: these tags structure historical log entries. Present via `AskUserQuestion` Pattern D, **nothing pre-checked**. The user opts in pattern by pattern. Display the warning: "renaming a log tag = rewriting a historical fact, usually prefer skip".

#### `B8 HIST` (historical traces)

**Skip by default**. If the `--include-historical` flag is set, present by sub-bucket (log / decisions / syntheses / sources) with `AskUserQuestion` Pattern D, **nothing pre-checked**. Display the warning: "historical pages describe a past state of the vault. Rewriting them = falsifying history."

#### `B9 DRIFT`

**Final warning, never auto-fix**. List the hits in the final report with a recommendation for manual review.

### Phase 4 — Physical renames

Once all bucket validations are collected:

```bash
# Agent + suggestions
mv .claude/agents/<old>-expert.md .claude/agents/<new>-expert.md
[ -f .claude/agents/<old>-expert.suggestions.md ] && mv .claude/agents/<old>-expert.suggestions.md .claude/agents/<new>-expert.suggestions.md
[ -f .claude/agents/<old>-expert.suggestions.archive.md ] && mv .claude/agents/<old>-expert.suggestions.archive.md .claude/agents/<new>-expert.suggestions.archive.md

# Memory (respect MEMORY_CONVENTION)
mv .claude/agent-memory/<old>${SUFFIX}/ .claude/agent-memory/<new>${SUFFIX}/

# Hub
mv wiki/domains/<old>.md wiki/domains/<new>.md
```

Inside **each** renamed file, substitute all internal references to the slug and the label (frontmatter `name:`, `description:`, bodies, etc.).

### Phase 5 — `CLAUDE.md` renumbering

The rename doesn't touch the numbered position by default. Propose (`AskUserQuestion`):
- "Keep the same numeric position" (default).
- "Re-position conceptually" (re-ask question 1.3 from `add`).

### Phase 6 — Validation + apply

Cf. shared section.

---

## Sub-command: `remove <slug>`

Flags: `--archive` (default) | `--purge` | `--include-historical` (modifies `--archive` to propose history case-by-case, without triggering the global `--purge` mode).

### Phase 1 — Pre-validation

- Refuse if `<slug>` is the **only domain** in the vault (`|EXISTING_DOMAINS| == 1`) → the ecosystem doesn't work without at least one domain. Cf. `BOOTSTRAP.md`.
- Refuse if `<slug>` does not exist in `EXISTING_DOMAINS`.

### Phase 2 — Scan

```bash
bash scripts/scan-domain-refs.sh <slug> > /tmp/scan-remove.txt
```

### Phase 3 — Per-bucket presentation

**`--archive` (default) invariant — STRICT.** The only files physically deleted are those listed in Phase 4:

- `.claude/agents/<slug>-expert.md` (+ `.suggestions.md` + `.suggestions.archive.md`)
- `.claude/agent-memory/<slug>${SUFFIX}/`
- `wiki/domains/<slug>.md`

**No other file deletion.** Content pages (`wiki/sources/`, `wiki/concepts/`, `wiki/entities/`, `wiki/decisions/`, `wiki/syntheses/`) are:

- **edited** in their frontmatter (B2 removes the slug from `domains:`),
- or have **lines removed** in their body (B3/B4 on orphan wikilinks).

If a page becomes orphaned (`domains: []` after removal), a dedicated dialog is proposed (cf. B2 step 2) — **deleting that page stays opt-in case-by-case**, never in batch, never pre-checked.

If you catch yourself proposing the deletion of a content page in batch ("Delete the N pages") in `--archive` mode → you've violated the invariant: abort, rebuild the plan.

Modes:

- **`--archive`** (default): edits B1-B4 (lines / frontmatter / wikilinks). B5/B6/B7 silently skipped (final warnings). B8 fully preserved (untouched, not even proposed). B9 warning.
- **`--purge`**: edits B1-B4 **plus** proposes B5/B6/B7/B8 case-by-case (same protocols as `rename`, the action being removal of the occurrence). File deletion stays limited to Phase 4 unless explicit per-page opt-in.
- **`--include-historical`** (modifies `--archive`): proposes B8 sub-bucket by sub-bucket without pre-check. Still no file deletion by default — the B8 action remains line edit or frontmatter edit.

#### B1 CANONICAL (active)

`AskUserQuestion` Pattern D, **all pre-checked**. Removal of the line (or numbered entry) corresponding to the slug.

#### B2 FRONTMATTER

The B2 action is **always a frontmatter edit, never a page deletion**. It runs in two steps.

**Step 1 — slug removal.** `AskUserQuestion` Pattern D, **all pre-checked**. For each page with `domains: [...]` containing `<slug>`: remove `<slug>` from the list, keep the other domains. B8 HIST pages (located in `wiki/log.md`, `wiki/decisions/`, `wiki/syntheses/`, `wiki/sources/`) are **excluded from this step in `--archive` mode** — their frontmatter isn't edited (cf. Phase 3 invariant + B8).

**Step 2 — orphans.** For each page where removal leaves `domains: []`, dedicated **one-by-one** dialog (never in batch, never pre-checked):

```json
{
  "question": "Page <path> becomes orphan (domains: []) after removing <slug>. What do you want?",
  "options": [
    {"label": "Re-tag", "description": "Pick another domain from EXISTING_DOMAINS"},
    {"label": "Leave orphan", "description": "domains: [] — page stays in place, will be flagged by /lint (Recommended)"},
    {"label": "Delete the page", "description": "Explicit opt-in — only relevant for mono-domain pages that purely describe the removed domain"}
  ]
}
```

"Delete the page" is **opt-in per page**, never in batch. If more than 3 orphans, present the dialog in alphabetical path order; the user can answer "Leave orphan" on all of them to skip through quickly.

#### B3 WIKILINK / B4 ALIAS

`AskUserQuestion` Pattern D, **all pre-checked**. Removal of the host line (wikilinks `[[domains/<slug>]]` lose their target once `wiki/domains/<slug>.md` is deleted). If the line contains other useful content → ask the user (split the line or keep it).

#### B5/B6/B7

`--archive`: silent skip, listed in the final warnings.
`--purge`: proposed case-by-case ("remove the line? replace with empty text?").

#### B8 HIST

**Invariant reminder**: B8 pages live in `wiki/log.md`, `wiki/decisions/`, `wiki/syntheses/`, `wiki/sources/`. They record the vault's past state and are **never deleted by `/domain remove --archive`**, even indirectly via the "orphan page" B2 step 2 dialog (B8 pages are excluded from B2 entirely in `--archive`).

- **`--archive`** (default): B8 fully preserved. No prompt, no frontmatter edit, no line edit.
- **`--include-historical`**: propose by sub-bucket (log / decisions / syntheses / sources) with `AskUserQuestion` Pattern D, **nothing pre-checked**. The action is **line edit** (remove the slug mention from the body) or frontmatter edit (remove the slug from `domains:`), not file deletion. B8 page deletion = explicit opt-in case-by-case via the same 3-option dialog as B2 step 2 (never in batch).
- **`--purge`**: implies `--include-historical`. B8 page deletion stays opt-in case-by-case via the dedicated dialog.

### Phase 4 — Physical deletions

**Exhaustive list — `--archive` ONLY physically deletes these files**:

```bash
rm .claude/agents/<slug>-expert.md
rm -f .claude/agents/<slug>-expert.suggestions.md
rm -f .claude/agents/<slug>-expert.suggestions.archive.md
rm -rf .claude/agent-memory/<slug>${SUFFIX}/
rm wiki/domains/<slug>.md
```

Any additional deletion (orphan content page opt-in via B2 step 2, B8 page opt-in under `--include-historical` or `--purge`) is **validated case-by-case** by the user via the dedicated dialog, and journaled separately in the final report (Phase 6) under `Content pages deleted (opt-in)`, distinct from `Domain files deleted (Phase 4)`.

### Phase 5 — `CLAUDE.md` renumbering

Renumber the entries downstream of the deleted position in `## User domains`. Same for any other numbered list.

### Phase 6 — Validation + apply

Cf. shared section.

---

## Validation & application (shared across the 3 sub-commands)

### A. Scan phase (read-only)

The command always begins by producing a **change plan** without modifying anything. Steps 1-3 of each sub-command are pure reads.

### B. Preview phase

Show the user:

- **Global summary**: "Vault: <path>. Sub-command: <sub>. Slug(s): <slugs>. Buckets impacted: B1:<N1>, B2:<N2>, …".
- **List of physical renames** (files + directories).
- **List of modified files** (grouped by bucket).
- **Warnings**: B9 DRIFT, B5/B6/B7 skipped (under `--archive`), cross-bucket inconsistencies if detected.

### C. Final validation phase

`AskUserQuestion`:

```json
{
  "question": "Apply the changes?",
  "header": "Apply?",
  "options": [
    {"label": "Apply", "description": "Run renames + edits + deletions"},
    {"label": "Apply (dry-run)", "description": "List the shell commands without executing them (debug)"},
    {"label": "Abort", "description": "Do nothing, keep the plan in /tmp"}
  ]
}
```

### D. Apply phase

Strict order (physical renames first to avoid editing files that are about to disappear):

1. Physical renames (`mv`).
2. Physical deletions (`rm`).
3. Content edits (substitutions, line removals, renumbering).
4. File creations (template rendering for `add`).

If a step fails mid-way:
- Log the error, **do not continue**.
- Suggest the user git-checkpoint (`git status` + commit/stash) before retrying.
- The plan lives in `/tmp/domain-plan-<timestamp>.txt` for debugging.

### E. Journaling phase

Append to `wiki/log.md`:

```
## [YYYY-MM-DD] domain | <sub> <slug>[<→ new-slug>]

<N> files touched. Buckets: <B1:N1, B2:N2, …>. Warnings: <B9 hits if present, B5/B6/B7 skipped if --archive>.
```

### F. Final report

- Counters per bucket (touched / skipped).
- List of untreated warnings (numeric drift, skipped composed slugs, etc.).
- Next step suggested:
  - After `add`: `/ingest raw/<recent-folder>/` to test the new agent on a source.
  - After `rename`: `/lint` to check that no wikilink still points to the old slug.
  - After `remove`: `/lint` to detect orphans.

---

## Principles

- **History is sacred**: by default, `wiki/log.md`, `wiki/decisions/*`, `wiki/syntheses/*`, `wiki/sources/*` are never rewritten. Explicit opt-in via `--include-historical` or `--purge`.
- **Ambiguity → human**: any case where a heuristic could be wrong (composed, prose, aliases) is presented individually to the user. No silent rewrite.
- **Idempotence**: re-running the command on a domain that's already added/renamed/removed must produce an empty or minimal plan (and say so).
- **Don't touch the dynamic dispatch**: `/ingest` loads its agents by reading `.claude/agents/` — adding/removing the `<slug>-expert.md` file is enough. Don't edit `.claude/commands/ingest.md` unless a hardcoded mapping is detected.
