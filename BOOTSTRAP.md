# BOOTSTRAP.md — portable LLM-Wiki personalization prompt

> You (Claude) are reading this file in a fresh clone of `tetra-plg/boiling-brain`. Your mission: walk the user through an interview, infer their architecture, scaffold their personalized LLM-Wiki instance, then clean up.
>
> **Language**: detect the user's language from their first messages (or from the system locale if you can infer it) and run the entire interview, generate every file and write every comment in that language. If unsure, ask the question in English before continuing. Do not maintain multiple versions of the prompt — adapt on the fly. Be direct, no prose. The `AskUserQuestion` calls must be asked as specified.
>
> **Language persistence**: the language detected here becomes the value of the `{{vault_language}}` placeholder (human label: `English`, `Français`, `Español`, `Deutsch`, `日本語`…). That value is then injected into `CLAUDE.md` and into every domain agent so that **all wiki pages produced by `/ingest` are written in that language**, regardless of the original source language. An EN source in a FR vault yields FR pages; the reverse is just as true. Confirm the language with the user at the end of Q1 if you have any doubt.

---

## Section 1 — Preamble (to internalize)

### 1.1 What an LLM Wiki is

An **LLM Wiki** is a personal wiki maintained by an LLM:

- The human drops raw sources (notes, video transcripts, PDFs, web clippings, official docs, repo snapshots) into `raw/` — **immutable**.
- **Per-domain expert agents** (one per declared domain) ingest those sources, write into `wiki/sources/`, `wiki/concepts/`, `wiki/entities/`, and their signature deliverable (`cheatsheets/`, `syntheses/`, `diagrams/`).
- **Slash-commands** orchestrate: `/ingest`, `/query`, `/save`, `/lint`, `/evolve-agent`, and conditionally `/ingest-video`, `/sync-repos`.
- The wiki is **always derivable** from `raw/`. No orphan knowledge. No invented links.

### 1.2 Roles

- **Human**: curates sources, asks questions, validates trade-offs.
- **LLM (you during bootstrap, then the expert agents thereafter)**: read, synthesize, cross-reference, maintain. Never invent outside sources.

### 1.3 Structuring principles (to engrave during bootstrap)

- `raw/` = never modified, never overwritten, hash-addressed (`source_sha256`).
- `cache/` = transient, never referenced from the wiki.
- Internal links as `[[wikilinks]]` Obsidian-style, pages in kebab-case, YAML frontmatter mandatory.
- Tiered loading: every page carries `summary_l0` (≤140 chars) + `summary_l1` (2-5 sentences). Lets agents scan a domain without loading bodies.
- No ingestion from memory or conversation: one source = one file in `raw/`.

### 1.4 What you'll do (overview)

1. 7-question interview (Section 2).
2. Inference of 5 properties per domain (Section 3).
3. Per-domain + global validation (Section 4).
4. Generation: placeholder substitution, per-domain duplication, conditional removals, this file moved to ADR, git reset (Section 5).
5. Optional GitHub remote (Section 6).
6. Onboarding wrap-up + 3 next actions (Section 7).

---

## Section 2 — Step 1, Interview (7 questions)

Ask the questions **sequentially**. Store every answer in an internal variable. **Move on only when the previous one is resolved.**

### Q1 — Identity

Ask 2 plain-text questions, sequential, not via `AskUserQuestion`:

1. "What's your full name? (e.g. *Maria Dupont*, *Carlos Silva*)"
   → Store as `name`. Extract the **first name** (1st token before the space) lowercased to compute `vault_name = <firstname>-vault`.
   → For hyphenated first names ("Jean-Marc"), split on **spaces only**: `vault_name = jean-marc-vault`.

2. "What's your short professional role (1 line)? (e.g. *Lead data engineer at Acme Corp*, *Post-doc researcher in genomics at CNRS*)"
   → Store as `role`.

**Parsing:**
- `name` = raw answer to Q1.1 (e.g. `"Maria Dupont"`).
- `role` = raw answer to Q1.2.
- `vault_name` = `<first_token_lowercase>-vault`. The "first token" is obtained by splitting on **spaces only** (not on hyphens). So `"Maria Dupont"` → `maria-vault`, `"Jean-Marc Lefebvre"` → `jean-marc-vault`. Confirm silently, no dedicated question.

### Q2 — Knowledge domains

Ask in plain free-text (no `AskUserQuestion` — the list is open):

```
List the knowledge domains you want to maintain.
Format: kebab-case slugs, comma-separated.
Example: data-science, ml-ops, devops, leadership, writing
Tip: cluster rather than splinter when natural. No cap — declare as many as relevant.
```

**Parsing:**
- `domains = [slugs...]`. Trim every slug. Validate kebab-case, fix silently otherwise.
- If 0 domain → re-ask, saying at least 1 is needed.
- For each slug, infer a `domain_label` via human title-casing (e.g. `astro-physics` → `Astronomy & Physics`, `ai` → `AI`). You will display it at validation time.

**Slug → human-label mapping (domain title)**:
- ASCII kebab-case slug (e.g. `market`, `paleo-dna`).
- The human label is derived for display: capitalize + accents if relevant (e.g. `marche` → `Marché`, `paleo-dna` → `Paleo-DNA`).
- On ambiguity (e.g. slug `cs` → `Computer Science` or `Customer Success`?), ask the user to confirm the human label.

### Q3 — Hub pivot

Dynamic single-select with one option per domain + "none". **Before asking the question**, show this short reminder in plain text:

> "If you hesitate, pick 'none' — you can designate a hub later via `/evolve-agent`."

Build the JSON dynamically:

```json
{
  "questions": [{
    "question": "Which domain plays the role of hub pivot (feeds the others)?",
    "header": "Hub pivot",
    "multiSelect": false,
    "options": [
      {"label": "<domain_slug_1>", "description": "<domain_slug_1> tools / feeds the other domains."},
      {"label": "<domain_slug_2>", "description": "<domain_slug_2> tools / feeds the other domains."},
      ...
      {"label": "none", "description": "My domains are independent. I'll designate a hub later via /evolve-agent if needed."}
    ]
  }]
}
```

**Concrete example** for `domains = [poker, ai, factory, work, tech]`: 5 options labeled `poker`/`ai`/.../`tech` + the `none` option. Static description: "The hub pivot is the domain that tools or feeds the others. Example: AI feeds the Factory (agents) and Work (LLM management techniques)."

**Parsing:**
- `hub_pivot = <slug>` or `null` if "none".

### Q4 — Active projects

Free-text (natural prose, free format):

```
Describe your 2-3 currently active projects (1 line per project, in natural language).

Example:
I'm following an MTT poker masterclass to improve my tournament play
I'm rebuilding my Factory plugin in a multi-agent architecture

(Leave empty if no active project right now.)
```

**Automatic parsing**:
- For every non-empty line, extract a kebab-case `slug` (2-4 keywords condensed from the sentence) and keep the full sentence as `description`.
- Example: `"I'm following an MTT poker masterclass for 2026"` → `{slug: "mtt-poker-masterclass", description: "MTT poker masterclass 2026"}`.
- If the line is too short to extract a meaningful slug → `project-1`, `project-2`, etc.
- `projects = [{slug, description}, ...]`. Empty list accepted (you'll use `"(to be filled in)"` later).

### Q5 — Source types

Multi-select 6 options:

```json
{
  "questions": [{
    "question": "Which source types do you plan to ingest?",
    "header": "Source types",
    "multiSelect": true,
    "options": [
      {"label": "Personal notes", "description": "Reflections, takeaways, personal drafts."},
      {"label": "Video transcripts", "description": "YouTube + local files. Enables /ingest-video and the frames pipeline."},
      {"label": "PDFs", "description": "Papers, ebooks, slides."},
      {"label": "Web clippings", "description": "Blog articles, threads, posts."},
      {"label": "Official docs", "description": "SDKs, APIs, frameworks."},
      {"label": "GitHub repos", "description": "Tracking evolving projects. Enables /sync-repos."}
    ]
  }]
}
```

**Parsing:**
- `source_types = [labels...]`.
- `ingest_video_enabled = "Video transcripts" in source_types` (boolean).
- `has_tracked_repos = "GitHub repos" in source_types` (boolean).

### Q6 — Ingestion cadence

Single-select 3 options:

```json
{
  "questions": [{
    "question": "At what cadence do you plan to ingest?",
    "header": "Cadence",
    "multiSelect": false,
    "options": [
      {"label": "< 1 per week", "description": "Low volume. Favors cost (haiku/medium by default)."},
      {"label": "1 to 3 per week", "description": "Standard cadence."},
      {"label": "> 3 per week", "description": "High volume. Favors quality (sonnet/high by default on dense non-pivot agents)."}
    ]
  }]
}
```

**Parsing:**
- `cadence ∈ {"low", "medium", "high"}`.

### Q7 — Video storage (conditional)

Ask **only if** `ingest_video_enabled = true`. Free-text:

```
Path of the video cache (where videos are stored before transcription).
Default: cache/videos/ (inside the vault, on your main disk).
If you have an external SSD for heavy videos: provide its path (e.g. /Volumes/T7/llm-wiki-cache/videos/).
```

**Parsing:**
- `video_cache_path` = answer, default `cache/videos/` if empty.

---

## Section 3 — Step 2, Inference (B1-B5 per domain)

For each `domain_slug` in `domains`, infer 5 properties. **You do this work, not the user.** They will validate afterwards.

### B1 — `trigger_examples` (4-6 verbal phrases)

Phrases you'd hear in a video transcript of this domain that signal a visual is on screen. Infer from the label.

**Generate the phrases in the vault language** (`{{vault_language}}` — captured at the very start of the interview). Example patterns are given in EN below; use them as a calibration template, then translate / adapt to the target language. If the user is German, generate German phrases; if Spanish, Spanish; etc. Don't mix languages.

Calibration patterns:
- **Data / numbers / matrices** (poker, finance, sport stats) → "look at the table", "here's the grid", "you can see them", "this column", "this cell".
- **Schemas / architectures / flows** (ai, devops, factory, tech) → "this diagram", "here's the architecture", "this flowchart", "this arrow", "this component".
- **Formulas / equations** (physics, math, astro) → "this formula", "here's the equation", "this proof", "this calculation".
- **Interfaces / tools / screenshots** (devtool, UX) → "look at the screen", "here's the screenshot", "this button", "this UI".
- **Reflective / management / qualitative** (work, leadership, philosophy) → 0-3 phrases only, e.g. "this framework", "this mental model", "here's the matrix".

**Concrete example for `data-science` (vault_language = English)**: `["look at the table", "this chart", "this curve", "here's the confusion matrix", "you can see the histogram"]`.

**Concrete example for `data-science` (vault_language = Français)**: `["regardez le tableau", "ce graphique", "cette courbe", "voilà la matrice de confusion", "vous voyez l'histogramme"]`.

### B2 — `deliverables` (signature deliverable)

Heuristic:
- **Technical-dense** domain (numbers, ranges, rates, KPIs) → `[cheatsheets]`.
- **Reflective** domain (patterns, frameworks, takeaways) → `[syntheses]`.
- **Systems** domain (architectures, flows, components) → `[diagrams]`.
- **Mixed** domain → `[cheatsheets, syntheses]`. Typical for `ai` (numbers AND patterns).

Always implicitly add the base deliverables: `[sources, entities, concepts]` (universal).

### B3 — `co_ingest_partners`

- If `hub_pivot != null` AND `domain_slug != hub_pivot` → `co_ingest_partners = [hub_pivot]`.
- If `domain_slug == hub_pivot` or `hub_pivot == null` → `co_ingest_partners = []`.

### B4 — `model` / `effort` / `maxTurns`

Decision table:

| Condition | model | effort | maxTurns |
|---|---|---|---|
| `is_hub_pivot = true` | `sonnet` | `high` | `80` |
| Technical-dense domain (B2 contains `cheatsheets`) | `sonnet` | `high` | `60` |
| `cadence = "high"` AND not pure reflective | `sonnet` | `high` | `60` |
| Otherwise (default) | `haiku` | `medium` | `60` |

**Priority on conflict**:
1. `is_hub_pivot = true` → always `sonnet/high/80`.
2. Otherwise, `deliverables` contains `cheatsheets` → `sonnet/high/60` (technical density justifies the cost even at low cadence).
3. Otherwise, `cadence = high (>3/week)` → `sonnet/high/60` (volume justifies quality).
4. Default → `haiku/medium/60`.

### B5 — `is_hub_pivot`

Trivial: `is_hub_pivot = (domain_slug == hub_pivot)`.

### B6 — frames_visual_formats (4-6 markdown transcription formats)

For each domain, infer 4-6 useful formats to transcribe video frames into structured markdown.

Patterns by domain type:
- **Data / numbers / matrices** (poker, finance, sport stats): "Markdown table", "table with depth × position columns", "13×13 grid", "numerical leaderboard".
- **Schemas / architectures / flows** (ai, factory, devops): "Mermaid diagram", "flowchart", "graph LR", "sequenceDiagram".
- **Formulas / equations / proofs** (physics, math, biostat): "LaTeX block", "inline equation", "variables table", "step-by-step proof".
- **Interfaces / tools / screenshots** (devtool, UX): "UI description", "keyboard shortcuts table", "bullet list of clicked buttons".
- **Reflective / management / qualitative** (work, leadership): "2D framework × axes table", "pattern bullet list", "boxed memorable quote".

The user can edit these at domain validation.

### Other side inferences

- `summary_l0` (≤140 chars): generate a draft from label + deliverable. E.g. `"AI hub — agents, LLM, orchestration. Tools the Factory and feeds LLM management techniques."`.
- `summary_l1` (2-5 sentences): same draft, more detailed.
- `domain_intro_paragraph`: 2-3 lines under the hub's H1.
- `parcours_short`: draft 2-4 bullets from Q1 `role` + Q4 `projects`. To be edited later by the user.
- `taxonomy_section`: leave initially empty (`(to be fleshed out as ingests come in)`) — the user doesn't want to invent a taxonomy cold.
- `authority_table_enabled`: `true` for reflective domains where source authority matters (ai, science, analytical work); `false` otherwise. You can decide from the label.
- `confidentiality_block`: non-empty only for `work` or any domain the user has explicitly flagged sensitive (ask during validation if in doubt).
- `bootstrap_date`: shell `date +%Y-%m-%d`.

---

## Section 4 — Step 3, Validation (per domain + global)

### 4.1 Per-domain validation

**For each** `domain_slug` (loop), display a markdown recap block then ask an `AskUserQuestion`:

```markdown
### Domain: {{domain_label}} (`{{domain_slug}}`)

- **Hub pivot**: {{ "yes ⭐" if is_hub_pivot else "no" }}
- **Signature deliverable**: {{ deliverables joined }} — {{ 1-line justification }}
- **Trigger phrases** (visuals in video transcripts):
  - "{{ trigger_1 }}"
  - "{{ trigger_2 }}"
  - …
- **Co-ingest partners**: {{ co_ingest_partners or "[] (none)" }}
- **Model**: {{ model }} · **Effort**: {{ effort }} · **MaxTurns**: {{ maxTurns }}
```

Then:

```json
{
  "questions": [{
    "question": "Domain {{domain_slug}} — do you validate this config?",
    "header": "Domain validation",
    "multiSelect": false,
    "options": [
      {"label": "✅ Validate this domain", "description": "Keep the inference as-is."},
      {"label": "✏️ Adjust", "description": "Edit one or more of the 5 properties (triggers, deliverables, co-ingest, model/effort/maxTurns, hub pivot)."}
    ]
  }]
}
```

On "✏️ Adjust":

1. Show an `AskUserQuestion` **multiSelect**: "Which properties do you want to edit?" with 5 options (B1 trigger_examples, B2 deliverables, B3 co_ingest_partners, B4 model/effort/maxTurns, B5 frames_visual_formats).
2. For each ticked property only, prompt with the current value displayed and ask for the new one.
3. Re-display the edited recap, ask again for validation.

**Once the domain is validated (✅ or after adjustment)**, ask immediately:

```json
{
  "questions": [{
    "question": "Which color for \"{{domain_slug}}\" in the Obsidian graph?",
    "header": "Graph color",
    "multiSelect": false,
    "options": [
      {"label": "🔵 Turquoise", "description": "#2BC7D3 — AI, tech, digital. rgb=2869203"},
      {"label": "🟢 Green", "description": "#51C463 — sciences, health, nature. rgb=5358691"},
      {"label": "🟠 Orange", "description": "#E07B39 — management, sport, competition. rgb=14711609"},
      {"label": "🔴 Red", "description": "#E05252 — poker, gaming, intensity. rgb=14701138"}
    ]
  }]
}
```

→ Store `domain_color_rgb = <chosen option's rgb value>` for this domain (used in Section 5 to generate `.obsidian/graph.json`). If the user picks "Other" and enters a hex `#RRGGBB`, convert via `R*65536 + G*256 + B`.

### 4.2 Global validation

Once every domain has been individually validated, show a full recap:

```markdown
## Final recap

**Identity**: {{name}} — {{role}}
**Vault**: `{{vault_name}}`
**Cadence**: {{cadence}}
**Source types**: {{source_types joined}}
{{ "**Video storage**: " + video_cache_path if ingest_video_enabled else "" }}

**Active projects**:
- {{ project_1.slug }} | {{ project_1.description }}
- ...

**Domains** ({{N}}):
- {{ domain_1_slug }} {{ "⭐" if pivot }} — {{ deliverables }} — {{ model }}/{{ effort }}/{{ maxTurns }}
- ...
```

Then:

```json
{
  "questions": [{
    "question": "All good?",
    "header": "Final validation",
    "multiSelect": false,
    "options": [
      {"label": "✅ All good, scaffold it", "description": "Run vault generation."},
      {"label": "↩️ Restart the interview from scratch", "description": "Goes back to Q1. All answers are wiped."}
    ]
  }]
}
```

If "↩️" → restart from Q1. Otherwise → Section 5.

---

## Section 5 — Step 4, Vault generation

Run in **this exact order**. Use `Edit replace_all=true` or `sed` for substitutions, `Bash` for `mv`/`rm`/`cp`/`git`.

### 5.1 Substitution of the 29 placeholders (reference: `PLACEHOLDERS.md` at the root)

For each `.tpl` file in the repo (CLAUDE.md.tpl, wiki/index.md.tpl, wiki/log.md.tpl, wiki/overview.md.tpl, wiki/radar.md.tpl, wiki/domains/domain.md.tpl, .claude/agents/domain-expert.md.tpl, .claude/agent-memory/domain-memory.md.tpl):

- Load the content.
- Substitute every **global** placeholder: `{{name}}`, `{{vault_name}}`, `{{vault_language}}` (human label of the language detected at the interview — see *Language persistence* directive at the top of this prompt), `{{role}}`, `{{parcours_short}}`, `{{bootstrap_date}}`, `{{has_tracked_repos}}` (and its conditional sections: `{{slash_commands_extras}}`, `{{tracked_repos_arborescence}}`, `{{tracked_repos_cache}}`, `{{tracked_repos_scripts_extras}}`, `{{sync_repos_section}}`).
- Substitute the computed **cross-domain** placeholders: `{{domains_section}}`, `{{domains_index_section}}`, `{{domains_links}}`, `{{projects_links}}`, `{{agents_section}}`.

**Note**: `tracked-repos.config.json.tpl` contains no placeholder, skip substitution. The final rename is handled in Section 5.6.

> For `{{has_tracked_repos}} = false`, the 5 conditional placeholders become empty strings (cf. table in `PLACEHOLDERS.md`).
> For `{{has_tracked_repos}} = true`, copy the full `### SYNC-REPOS` block provided in **Annex D** below (verbatim, replacing the `{{sync_repos_section}}` placeholder).

### 5.2 Per-domain duplication — agents

For each `domain_slug` in `domains`:

```bash
cp .claude/agents/domain-expert.md.tpl .claude/agents/{{domain_slug}}-expert.md
```

Then substitute in the copy the **17 per-domain placeholders**: `{{domain_slug}}`, `{{domain_label}}`, `{{is_hub_pivot}}`, `{{hub_pivot_marker}}`, `{{summary_l0}}`, `{{summary_l1}}`, `{{domain_intro_paragraph}}`, `{{taxonomy_section}}`, `{{related_domains_section}}`, `{{deliverables}}`, `{{deliverables_signature_block}}`, `{{trigger_examples}}`, `{{frames_visual_formats}}`, `{{co_ingest_partners}}`, `{{co_ingest_section}}`, `{{authority_table_enabled}}`, `{{authority_table_section}}`, `{{confidentiality_block}}`, `{{confidentiality_section}}`, `{{domain_specific_observation_section}}`, `{{model}}`, `{{effort}}`, `{{maxTurns}}`.

### 5.3 Per-domain duplication — hubs

For each `domain_slug`:

```bash
cp wiki/domains/domain.md.tpl wiki/domains/{{domain_slug}}.md
```

Substitute the per-domain placeholders (same values as 5.2, except we don't rewrite everything — see mapping in PLACEHOLDERS.md).

### 5.4 Per-domain duplication — agent memories

For each `domain_slug`:

```bash
mkdir -p .claude/agent-memory/{{domain_slug}}
cp .claude/agent-memory/domain-memory.md.tpl .claude/agent-memory/{{domain_slug}}/MEMORY.md
```

Substitute.

### 5.5 Conditional removals

**If `ingest_video_enabled = false`**:

```bash
rm .claude/commands/ingest-video.md
rm scripts/transcribe.sh scripts/sample-frames.sh scripts/extract-frames.sh scripts/diff-frames.py
rm wiki/decisions/extraction-frames-induction-runbook.md
rm wiki/decisions/ingest-video-modes-a-b-generalisation.md
```

**If `has_tracked_repos = false`**:

```bash
rm .claude/commands/sync-repos.md
rm scripts/sync-repos.sh
rm tracked-repos.config.json.tpl    # or its rendered output if already substituted
rm wiki/decisions/tracked-repos-immutable-snapshots.md
```

### 5.6 Renaming substituted `.tpl` files to their final name

Once substitution is done, rename the **unique** templates (not those duplicated per domain, already renamed):

```bash
mv CLAUDE.md.tpl CLAUDE.md
mv wiki/index.md.tpl wiki/index.md
mv wiki/log.md.tpl wiki/log.md
mv wiki/overview.md.tpl wiki/overview.md
mv wiki/radar.md.tpl wiki/radar.md
# If has_tracked_repos = true:
mv tracked-repos.config.json.tpl tracked-repos.config.json
```

Remove the original `.tpl` that have been duplicated (their job is done):

```bash
rm .claude/agents/domain-expert.md.tpl
rm wiki/domains/domain.md.tpl
rm .claude/agent-memory/domain-memory.md.tpl
```

### 5.7 Move `BOOTSTRAP.md` and `PLACEHOLDERS.md` into ADR

Consultable trace of the bootstrap:

```bash
mv BOOTSTRAP.md wiki/decisions/bootstrap-prompt.md
mv PLACEHOLDERS.md wiki/decisions/placeholders-reference.md
```

### 5.8 Conditional directories (raw/ and cache/)

The base subfolders `raw/notes/`, `raw/transcripts/`, `raw/videos-meta/`, `raw/frames/` already exist in the template via `.gitkeep`. Only create the **conditional** subfolders:

```bash
# If "PDFs" was ticked in Q5:
mkdir -p raw/pdfs && touch raw/pdfs/.gitkeep

# If "Web clippings" was ticked in Q5:
mkdir -p raw/articles && touch raw/articles/.gitkeep

# If "Official docs" was ticked in Q5:
mkdir -p raw/docs && touch raw/docs/.gitkeep

# Always (cache/ structure):
mkdir -p cache/frames && touch cache/frames/.gitkeep

# If ingest_video_enabled = true:
mkdir -p cache/videos/inbox cache/audio && touch cache/videos/inbox/.gitkeep cache/audio/.gitkeep

# If has_tracked_repos = true:
mkdir -p cache/sync-repos && touch cache/sync-repos/.gitkeep
```

### 5.9 Generate `.obsidian/graph.json`

Create the `.obsidian/` folder and write the `graph.json` file from the colors collected in Section 4.1:

```json
{
  "search": "-path:\"raw\" path:\"wiki\" -path:\"wiki/sources\" -path:\"wiki/log\"",
  "showTags": false,
  "showAttachments": false,
  "hideUnresolved": true,
  "showOrphans": false,
  "colorGroups": [
    // For each domain_slug (in the order declared at Q2):
    {
      "query": "[\"domains\":{{domain_slug}}]",
      "color": {
        "a": 1,
        "rgb": {{domain_color_rgb}}
      }
    }
  ],
  "collapse-filter": false,
  "collapse-color-groups": true,
  "collapse-display": false,
  "collapse-forces": true,
  "showArrow": false,
  "close": true
}
```

Also create a minimal `.obsidian/app.json`:

```json
{
  "legacyEditor": false,
  "livePreview": true
}
```

### 5.10 Record the template version + git reset + initial commit

```bash
# Record the template SHA before deleting its history.
# Used by /update-vault to know which point to start listing new commits from.
TEMPLATE_SHA=$(git rev-parse HEAD)
echo "$TEMPLATE_SHA" > .template-bootstrap-sha

# Enrich .claude/template-version with the SHA and the bootstrap date.
# This file is the source of truth for the /update-vault migration machine.
TEMPLATE_VERSION=$(grep '^template-version:' .claude/template-version | awk '{print $2}')
cat > .claude/template-version <<EOF
template-version: ${TEMPLATE_VERSION}
template-sha: ${TEMPLATE_SHA}
last-updated: {{bootstrap_date}}
EOF

rm -rf .git/
git init
git add -A
git commit -m "initial vault — generated via BOOTSTRAP.md on {{bootstrap_date}}"
```

### 5.11 Optional MCP setup

Ask:

```json
{
  "questions": [{
    "question": "Do you want to enable the MCP server to access your wiki from any Claude Code instance?",
    "header": "MCP Wiki",
    "multiSelect": false,
    "options": [
      {"label": "✅ Yes, set it up now", "description": "Runs bash scripts/setup-mcp.sh. Prerequisites: Python 3 + internet connection for pip."},
      {"label": "❌ No, I'll do it later", "description": "Run bash scripts/setup-mcp.sh from the vault whenever you want."}
    ]
  }]
}
```

- **Yes**: run `bash scripts/setup-mcp.sh` (from the vault root). On pip error, show the error message + manual fallback: `pip install "fastmcp>=2.14"` then re-run.
- **No**: skip.

---

## Section 6 — Step 5, Optional GitHub remote

Ask:

```json
{
  "questions": [{
    "question": "Do you want to create a GitHub repo for your {{vault_name}} vault?",
    "header": "Remote",
    "multiSelect": false,
    "options": [
      {"label": "✅ Yes, private", "description": "gh repo create {{vault_name}} --private --source=. --push"},
      {"label": "✅ Yes, public", "description": "gh repo create {{vault_name}} --public --source=. --push"},
      {"label": "❌ No, I'll handle it manually", "description": "No action. You can add a remote later with git remote add origin <url>."}
    ]
  }]
}
```

Per the answer:

- **Private**: `gh repo create {{vault_name}} --private --source=. --push`
- **Public**: `gh repo create {{vault_name}} --public --source=. --push`
- **Manual**: skip.

**If `gh` is not installed or not authenticated** (catch the `gh repo create` error):
- Switch to manual.
- Show: "`gh` unavailable. To add a remote later: `gh auth login` then `gh repo create {{vault_name}} --private --source=. --push`."

**Handling `gh repo create` errors**:

- **Name already taken** ("repository already exists"): re-ask "The name `{{vault_name}}` is already taken. Which name should we use? (or leave empty to skip the push)".
- **Expired authentication** ("HTTP 401"): show "`gh auth login` required. Switching to manual mode: here are the commands to run later: `gh repo create <name> --private --source=. --push`." and continue the bootstrap without the remote.
- **Other error**: show the raw error + switch to manual as above.

---

## Section 7 — Step 6, Final onboarding wrap-up

Show a clean text message:

```
🎉 Your vault `{{vault_name}}` is ready.

Identity: {{name}} — {{role}}
Active domains ({{N}}): {{ domain_1, domain_2, ... }}
Available pipeline: /ingest, /query, /save, /lint, /evolve-agent{{ ", /ingest-video" if ingest_video_enabled }}{{ ", /sync-repos" if has_tracked_repos }}, /update-vault, /compress-bb

Three guided next actions:

1. Drop your first source into `raw/notes/<YYYY-MM-DD-topic>.md` (or `raw/transcripts/`, `raw/pdfs/`, etc. depending on the format).
2. Run `/ingest` — Claude will propose the matching expert agent and you'll validate via AskUserQuestion.
3. Edit `wiki/overview.md` to flesh out your portrait: background, activities, intentions. The generated draft is just a starting point.

To update your vault when the template evolves: `/update-vault`.

Bootstrap trace: wiki/decisions/bootstrap-prompt.md (what you just ran) + wiki/decisions/placeholders-reference.md (detailed mapping).

Happy ingesting.
```

---

## Annexes

### A. List of generated files (mental checklist)

- `CLAUDE.md` (at the root)
- `wiki/index.md`, `wiki/log.md`, `wiki/overview.md`, `wiki/radar.md`
- For each domain: `wiki/domains/<slug>.md` + `.claude/agents/<slug>-expert.md` + `.claude/agent-memory/<slug>/MEMORY.md`
- `wiki/decisions/bootstrap-prompt.md`, `wiki/decisions/placeholders-reference.md`
- Conditional: `tracked-repos.config.json`, `wiki/decisions/tracked-repos-immutable-snapshots.md`, `wiki/decisions/extraction-frames-induction-runbook.md`, `wiki/decisions/ingest-video-modes-a-b-generalisation.md`
- `raw/` structure: `notes/`, `transcripts/`, `videos-meta/`, `frames/` (pre-existing via .gitkeep) + conditional (`pdfs/`, `articles/`, `docs/`)
- `cache/` structure: `frames/` + conditional (`videos/inbox/`, `audio/`, `sync-repos/`)
- `.obsidian/graph.json` (graph filters + colorGroups per domain) + `.obsidian/app.json`
- Fresh `.git/`, initial commit landed.

### B. Files NOT to touch

- `LICENSE`, `.gitignore`, `README.md` (the README can be updated by the user later for their own instance — don't rewrite it during bootstrap).
- `scripts/scan-raw.sh`, `scripts/backfill-summaries.py`, `scripts/enrich-hub.py` (generic, stay as-is).
- The non-conditional slash-commands: `/ingest`, `/query`, `/save`, `/lint`, `/evolve-agent`, `/update-vault`.

### C. If you get stuck

If a step in Section 5 fails (e.g. a placeholder forgotten in a file, a `.tpl` that won't substitute):

1. **Don't** run the final `git init` until everything is clean.
2. Show the precise error to the user, propose a manual fix or a step retry.
3. The original `.git/` still exists until 5.8 has run — you can always `git diff` to compare against the initial state.

Once the fresh `git init` is done, the template's history is gone. That's intentional (clean start — the user begins with a pristine repo, no template noise).

### D. SYNC-REPOS block to inject into CLAUDE.md

When `has_tracked_repos = true`, copy this block verbatim in place of the `{{sync_repos_section}}` placeholder in CLAUDE.md.

````markdown
### SYNC-REPOS (`/sync-repos [names]`)

Sync the docs of external GitHub repos (frameworks, tools, projects you follow) into `raw/`, while strictly preserving immutability.

**Manifest**: `tracked-repos.config.json` at the vault root. Fields per source:
- `name` (slug, invocation key), `repo` (`owner/name` GitHub, e.g. `vercel/next.js`, `nf-core/sarek`, `your-org/your-repo`), `branch` (typically `main`)
- `dest` (vault-relative path, without the `<shortsha>/`) — free, you define the layout
- `paths` (optional, default `default_paths` of the manifest) — only those paths are copied from the clone
- `exclude_paths` (optional, default `default_exclude_paths` of the manifest) — paths removed from the snapshot **after** copy. Tolerant `rm -rf`: a missing path is silently ignored.

Manifest-level defaults: `default_paths` and `default_exclude_paths`. These defaults apply to any source that doesn't override them.

**SHA-keyed snapshot principle.** Each sync creates `<dest>/<shortsha>/` (shortsha = first 7 chars of the HEAD SHA of `branch`). If that folder already exists → skip. A merge into `main` upstream = a new SHA = a new snapshot beside the old. Old snapshots are **never** modified or deleted.

**Target resolution** (main context):
- no argument → interactive multiSelect (`AskUserQuestion`) over manifest sources, to avoid an unintended "sync all".
- explicit names (`next sarek`) → those sources.

**Mechanics** (`scripts/sync-repos.sh`):
1. `gh api repos/<repo>/commits/<branch>` → HEAD SHA.
2. If `<dest>/<shortsha>/` exists → `SKIPPED`.
3. Otherwise: `gh repo clone --depth=1 -b <branch>` into `cache/sync-repos/<name>/`, copy listed `paths` to `<dest>/<shortsha>/`, write `.sync-meta.json` (repo, branch, sha, synced_at, paths), clean up the clone.

**Chaining `/ingest`.** For each `CREATED <path>` line surfaced by the script: chain `/ingest <path>` sequentially.

**Logging.** Entry in `wiki/log.md`:
```
## [YYYY-MM-DD] sync-repos | N snapshots created
<list>
```

**Add a new repo**: edit `tracked-repos.config.json`, then `/sync-repos <new-name>`.
````

---

*End of the portable prompt. Now run Section 2.*
