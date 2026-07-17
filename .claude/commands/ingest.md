---
description: Ingest sources from raw/ into the wiki via a domain-expert agent (batch, idempotent, hash-based)
argument-hint: [--force] [--frames] [--headless] [--domain-hint=<slug>] [path-or-folder — empty = all of raw/]
---

Run the INGEST workflow from CLAUDE.md on: $ARGUMENTS

**Idempotent batch mode.** Behavior:

- No argument → full sweep of `raw/`.
- Argument = folder → scan that subtree.
- Argument = file → force re-ingest **of that file only**.
- `--force` flag (combinable with folder or full sweep) → treat every file as **modified**, even if its sha256 is unchanged. Useful after an expert agent evolved (`/evolve-agent`) to apply the new reflexes to already-ingested sources. **No duplicates created**: re-ingest updates existing pages (sources, entities, concepts) rather than creating new ones with different slugs.
- `--frames` flag (combinable with `--force` and a file/folder) → tells the agent the goal is to **extract missing visual frames**. The agent must re-read the transcript, produce a `## Frame requests` block per the convention, and not modify anything else in existing pages. Usable alone (`--frames`) or combined (`--force --frames`) on an already-ingested transcript.
- `--headless` flag → **non-interactive mode**, intended for a single file argument (not a folder or full sweep — batch triage of ambiguous cases still needs a human). Replaces every point that would otherwise call `AskUserQuestion` with a deterministic rule (see step 2 and step 4b). Set automatically by the `ingest(path, domain_hint)` MCP tool in `scripts/mcp/mcp-wiki.py` — not intended for manual interactive use.
- `--domain-hint=<slug>` flag (combinable with `--headless` only) → skips expert-agent disambiguation in step 2 if `.claude/agents/<slug>-expert.md` exists. Ignored (falls back to normal step-2 resolution) if `<slug>` has no matching expert agent.

For each in-scope file, from the **main context**:

### 1. State detection

Run `bash scripts/wiki-maint/scan-raw.sh [scope]` (no argument = all of `raw/`; with folder or file = subtree). The script outputs one line per file:

```
NEW      raw/...    → never seen
SKIP     raw/...    (covered-by: <slug>)   → already covered by a wiki page
MODIFIED raw/...    (covered-by: <slug>, sha-changed)   → covered but content changed
```

Detection is **robust**: it checks exact match on `source_path`, then on `covered_paths` (list of all raw paths covered by a composite page), then on parent directory. This avoids false "NEW" entries when an agent synthesized several files into a single page without listing each file individually.

Arbitration:

- `SKIP` → ignore (unless `--force` → treat as `MODIFIED`).
- `NEW` / `MODIFIED` → proceed to step 2.

**`--force` mode**: explicitly tell the expert agent in its prompt that the source has **already been ingested** (cite the existing source page) and that it's an **additive** re-ingest. The agent must read existing pages, identify what's missing, add only that, not rewrite content that's already correct. Update `ingested:` only if content was added.

**`--frames` mode**: tell the agent the goal is **exclusively** to produce frame requests for this transcript. Spawn instruction:

- Re-read the source transcript.
- Produce a `## Frame requests` block per the vault convention (cf. CLAUDE.md).
- **Don't modify anything else** in existing pages — no textual content update, no `ingested:` bump.
- If no detectable visual in the transcript → answer "no frame to declare" and don't produce the block.

If video/audio/URL not transcribed → chain `scripts/video/transcribe.sh` first.

### 2. Expert-agent proposal (user validation) — or automatic resolution in `--headless` mode

**Ingest is delegated to a domain-expert agent.** The main context doesn't write pages — it dispatches.

1. Analyze the source: title, location in `raw/`, content excerpt (~200 lines), cross-ref with `wiki/domains/`.
2. Propose one or more expert agents from those present in `.claude/agents/` (each domain declared at bootstrap has its `<domain>-expert.md`) with **confidence level** and **short justification**.
3. **Not `--headless`** → ask validation via `AskUserQuestion`:
   - **High confidence** → "Recommended" option as default + 2-3 alternatives + "other".
   - **Low / ambiguous confidence** → list of available experts without recommendation + "other".
   - **Obvious cross-domain** → multiSelect to spawn several experts in parallel.
4. **`--headless`** → resolve without asking, in this order:
   a. `--domain-hint=<slug>` given and `.claude/agents/<slug>-expert.md` exists → use that agent directly, skip the confidence analysis from steps 1-2.
   b. Otherwise, if steps 1-2's analysis produced exactly **one** candidate at **high confidence** → use it directly.
   c. Otherwise (ambiguous, cross-domain, low/medium confidence, or an invalid `--domain-hint`) → **do not ingest this file**. Leave its path in `cache/.pending-ingest` (do not add it to `PROCESSED_PATHS` in step 4c), and record it for the final report's `needs-human-triage` section (step 5) with the candidates considered and why none was auto-selected. An invalid `--domain-hint` (slug with no matching `.claude/agents/<slug>-expert.md`) is treated exactly like no hint at all — fall through to (b).
5. If the user chooses "other" or customizes (non-headless only), honor their pick.

### 3. Spawning the expert agent

Read `.claude/agent-output-contract.md` once at the start of the run; inject it integrally into every spawn prompt below.

For each validated agent, launch an `Agent` call with:

- `subagent_type`: the chosen agent.
- **Prompt** containing:
  - Path of the raw file to ingest.
  - A fresh domain snapshot: run `bash scripts/mcp/wiki-cli.sh scan-domain <d>` and paste its output verbatim under a `## Domain snapshot` heading. Regenerate it for every spawn (never once per batch) so intra-batch pages created by earlier sources are visible. If the command fails (or is denied in `--headless` mode), omit the snapshot — the agent produces its own via its Domain orientation reflex.
  - Path of `wiki/domains/<d>.md`.
  - The full content of `.claude/agent-output-contract.md`.
  - Instruction: execute the ingest end-to-end, then return the three blocks (`## Ingest summary`, `## Radar items`, `## Evolution suggestions`) per the contract. The agent **does not write** to `wiki/log.md`, `wiki/radar.md`, or `.claude/agents/*.suggestions.md` — the main context handles propagation.

The main context no longer builds a flat page-title list — the snapshot (counts + centrality + summaries) is both cheaper and richer, and the agent drills down on demand with the same CLI.

Cross-domain → multiple agents in parallel (same multi-tool call).

### 4. Collection and journaling

When the agent(s) have returned their report, the **main context** writes (never the agent):

1. **`wiki/log.md`** ← append summary line from `## Ingest summary` (`## [YYYY-MM-DD] ingest | <source title> (agent: <name>)` + 2-3 lines on pages created/updated/deliverables). **`--headless`** → append `, mode: headless, hint: <domain_hint|none>` inside the same parenthetical, e.g. `## [2026-07-02] ingest | My Source (agent: tech-expert, mode: headless, hint: tech)`. Files deferred to `needs-human-triage` (step 2, branch 4c) get **no** `wiki/log.md` entry — nothing was written for them.
2. **`wiki/radar.md`** ← append entries from `## Radar items` under the relevant thematic section. If no section matches, append to a `## Triage` block at the top of the file and flag this in the final report.
3. **`.claude/agents/<domain>-expert.suggestions.md`** ← append the `## Evolution suggestions` block (timestamped `### [YYYY-MM-DD HH:MM] source: <path>`). Skip if the block is "N/A".
4. **`wiki/index.md`** ← update if the agent's pages aren't already linked.

Centralizing writes in the main context prevents drift and inconsistent formatting across agents.

### 4b. Frame extraction (if present)

If the agent's report contains a `## Frame requests` block, handle **before** the final report:

**`--headless`** → do not extract or ask anything. Annotate the block verbatim on the ingested source page (same placement as the "no video in cache" case below — a `> [!question] Frame requests pending — run /ingest --frames on this source` callout followed by the `## Frame requests` block), then include `Frame requests: N declared — deferred (headless mode)` in the final report. Stop here; do not run steps 1-4 below.

**Not `--headless`**:

1. Check if a source video is available in `cache/videos/` (look for a file whose name matches the slug of the ingested transcript).
2. If video available:
   a. For each `FRAME: HH:MM:SS | slug | description` line: extract via `./scripts/video/extract-frames.sh <video_path> <timestamp> cache/frames/<slug>.png` (applies a default +5s offset — compensates for the lag between verbal mention and visual display).
   b. Show all extracted frames to the user in a single batch (`AskUserQuestion`).
   c. On validation → `cp cache/frames/<slug>.png raw/frames/YYYY-MM-DD-<source-slug>-<slug>.png`.
   d. On rejection → propose 3 quick alternatives without re-asking the user to specify an offset: extract at T-10s (`offset=-5`), T+0s (`offset=0`) and T+20s (`offset=15`) via `./scripts/video/extract-frames.sh <video> <timestamp> cache/frames/<slug>-altN.png <offset>`, show all 3 as a batch, validate or annotate `> [!question] Frame not extracted` if none works.
3. If no video in cache: tell the user the declared timestamps with the expected description — they can re-run manually or annotate the frames as `> [!question]`.
4. Include in the final report: `Frames: N promoted · M rejected` (or `Frame requests: N declared — video not available in cache`).

### 4c. Pending-ingest purge

Remove from `cache/.pending-ingest` the paths processed in this run (NEW + MODIFIED) and the stale SKIP entries detected at step 1. The main context accumulates these throughout the run: `PROCESSED_PATHS` = all NEW + MODIFIED paths from step 1; `STALE_SKIP_PATHS` = SKIP entries that were already present in `.pending-ingest` at step 1.

```bash
bash scripts/wiki-maint/purge-pending-ingest.sh "${PROCESSED_PATHS[@]}" "${STALE_SKIP_PATHS[@]}"
```

`--headless` files deferred to `needs-human-triage` (step 2, branch 4c above) are excluded from `PROCESSED_PATHS` — they remain in `.pending-ingest` for a future interactive run.

### 5. Final overall report

Format:

```
N new · M updated · K unchanged (skipped) · L orphans
```

Followed by:

- Per source: agent invoked, pages touched, deliverables produced.
- Evolution suggestions surfaced (pointer to `.suggestions.md` files).
- Contradictions detected (between sources or against the existing wiki).
- Open questions for the user.
- Orphans (pages `wiki/sources/` whose raw has disappeared — no auto-deletion).

**`--headless` mode additions** (cf. `docs/superpowers/specs/2026-07-02-mcp-headless-ingest-design.md` §4.2, §5.1):

- If the file was deferred (step 2, branch 4c): add a `needs-human-triage` section listing the file's path, the candidate expert agents considered, and why none was auto-selected. No pages were written for this file.
- Always end the report with a `## Pages` heading — **exactly two `#` characters, a level-2 heading, never `###` or any other level** — followed by one line per page created or updated by this run, in the form `- <path> (<type>, new|updated)`. Empty (just the `## Pages` heading, no lines) if the file was deferred to `needs-human-triage`. This block is specific to `--headless` — the interactive report format above is unchanged.

## Notes

- One source = one main agent (even if cross-domain, one agent leads the `wiki/sources/` page; the others enrich concepts/entities in their domain).
- If no expert agent fits and the user picks "other" → the main context performs the generic ingest (current fallback behavior).
- If the `/evolve-agent <domain>` command exists, it consumes the `.suggestions.md` to evolve the agent's prompt.

## Final step — normalise markdown

After all pages are written/updated, format the produced markdown so it stays
consistent and the CI `format-check` job passes:

```bash
python3 scripts/wiki-maint/format-md.py --write "wiki/**/*.md"
```
