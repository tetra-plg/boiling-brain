---
description: Ingest a video (local file or YouTube URL) via audio extraction, transcription, then domain-expert ingest
argument-hint: <path-or-url> [--induction|--mode-a|--skip-frames|--resume]
---

Run the INGEST-VIDEO workflow from CLAUDE.md on: $ARGUMENTS

## Pipeline

### 1. Audio acquisition + transcription

**If `--resume <slug>` is passed**: skip this step. Check that `raw/transcripts/YYYY-MM-DD-<slug>.md` (and associated meta) is present — if so, jump straight to step 2. If absent → explicit error. The `--resume` mode is used when transcription was produced by an upstream pipeline (remote transcription, manual intervention, etc.).

**Otherwise (standard flow)**:

- If YouTube URL: `yt-dlp -x --audio-format m4a -o "cache/audio/<slug>.%(ext)s" <url>`.
- If local file: move into `${LLMWIKI_VIDEO_CACHE:-cache/videos}/`, then `ffmpeg -i <video> -vn -acodec copy cache/audio/<slug>.m4a`.
- Local transcription (whisper.cpp or mlx-whisper) → `raw/transcripts/YYYY-MM-DD-<slug>.md` with timestamps. Use `scripts/transcribe.sh` which already covers these steps for both cases.
- Create `raw/videos-meta/YYYY-MM-DD-<slug>.meta.md` (URL, duration, hash, location).
- Purge `cache/audio/<slug>.m4a`.

#### Video storage convention: `LLMWIKI_VIDEO_CACHE`

Environment variable used by `scripts/transcribe.sh`, `scripts/sample-frames.sh` and `scripts/extract-frames.sh` to locate downloaded videos:

- **Default**: `cache/videos/` (internal disk, inside the vault).
- **Override**: export `LLMWIKI_VIDEO_CACHE` to an external disk or dedicated folder if video volume exceeds internal disk capacity.

For non-YouTube videos downloaded manually (browser extension, drag-and-drop), drop the file into `cache/videos/inbox/` then invoke the pipeline with that local path.

#### Mode A fallback if full video unavailable

If the full video couldn't be downloaded (e.g. external cache not mounted at clip time), Mode A (frame requests, step 4a) can fetch each frame on demand via `yt-dlp --download-sections "*HH:MM:SS-HH:MM:SS+15"` (~15s short segment) then `ffmpeg`. Mode B (cross-induction) requires the full video — not possible in fallback.

### 2. Standard ingest on the transcript

Chain to `/ingest <transcript_path>` → dispatch to the domain-expert agent.

The agent receives, in addition to the standard context, the frames convention:

```
Frames convention (excerpt from CLAUDE.md):
## Frame requests
- FRAME: HH:MM:SS | slug | Precise description of the expected visual
Cumulative criteria:
(1) Explicit verbal confirmation in the transcript that a visual is on display.
(2) One visual = one frame: group multiple references to the same visual, declare only one timestamp (first complete display).
Expected outcome: 2-4 frames max per hour of video (variable by visual density of the domain).
```

All expert agents have a `## Visual frames` section in their prompt — they can therefore return a `## Frame requests` block regardless of domain.

### 3. Extraction-mode choice (proposal to the user)

After the expert agent has returned its report, **propose** the extraction mode best suited to this video via `AskUserQuestion`. No silent switch.

**Override flags** (consumed in priority, no proposal shown):
- `--induction` → force mode B (cross-induction).
- `--mode-a` → force mode A (frame requests from the agent).
- `--skip-frames` → skip extraction.

**Signals to compute** before the proposal:
- `duration_min`: video duration in minutes (from the `duration` field of the `.meta.md` frontmatter).
- `visual_mentions`: count of visual-pattern occurrences in the transcript. **Bilingual EN+FR list** (extend with other languages as needed depending on the source-transcript language):
  - **EN patterns**: `look at`, `here's`, `here is`, `you can see`, `you'll see`, `this diagram`, `this table`, `this chart`, `this graph`, `this figure`, `this slide`, `this image`, `this dashboard`, `this pipeline`, `this code`, `on screen`, `on the screen`, `take a look`, `notice this`.
  - **FR patterns**: `regardez`, `voilà`, `vous voyez`, `ce schéma`, `ce tableau`, `cette grille`, `ce diagramme`, `cette image`, `à l'écran`, `cette capture`, `ce dashboard`, `ce flux`, `cette pipeline`, `ce code`, `ce slide`, `ce graphique`, `cette courbe`, `cette photo`.
  - Case-insensitive matching for both lists.
- `mentions_per_min`: `visual_mentions / duration_min`.
- `frame_requests_count`: number of entries in the agent's `## Frame requests` report block (0 if block absent).

**Computed recommendation**:
- **Recommend Mode A** if: `frame_requests_count` > 0 and consistent with `visual_mentions` (typical case: agent declared 2-4 frames on a conceptual video, or more on a dense video with many configurations).
- **Recommend Mode B** if:
  - `duration_min ≥ 30` AND `mentions_per_min ≥ 0.3` AND `frame_requests_count` ≤ 30% of the "expected" count (`visual_mentions / 3` as a rough heuristic) → suspected under-extraction.
  - OR `visual_mentions ≥ 10` AND `frame_requests_count` == 0 (agent declared no frames but transcript signals many visuals).
- **Recommend Skip** if: `duration_min < 15` AND `visual_mentions == 0`.

**Presentation** (`AskUserQuestion`, single-select 3 options):

```
Question: "Which frame-extraction mode for this video?
Signals: duration Xm · Y visual mentions · Z frame requests from the agent
→ Recommendation: <Mode X>"

Options:
- Mode A — agent's frame requests (Z frames)
- Mode B — cross-induction (sampling + image-diff + transcript)
- Skip — no frame extraction
```

The recommended option is marked "(Recommended)" and placed first.

**Logging**: the final decision (mode + signals + any override) is journaled in `wiki/log.md` on the same line as the ingest:
```
## [YYYY-MM-DD] ingest-video | <title> (agent: <name>, mode: A|B|skip, duration Xm, Y mentions, Z frames)
```

### 4a. Mode A — direct frame requests (existing pipeline)

For each `FRAME: HH:MM:SS | slug | description` line of the `## Frame requests` block:

1. Extract the frame: `./scripts/extract-frames.sh <video_path> <timestamp> cache/frames/<slug>.png`.
2. Show all extracted frames to the user as a batch via `AskUserQuestion`.
3. On validation → `cp cache/frames/<slug>.png raw/frames/YYYY-MM-DD-<source-slug>-<slug>.png`.
4. On rejection → propose a retry at timestamp ±X s, or annotate `> [!question] Frame not extracted` in the source page.
5. **Re-spawn the expert agent** on the source page in forced re-ingest mode, with the list of promoted frames + their transcript citation ±30 s. The agent must transcribe each frame as markdown in the relevant wiki page (cf. "Visual frames" section of its prompt + Step 9 of the runbook).
6. Report: `Mode A frames: N promoted · M rejected`.

### 4b. Mode B — cross-induction

Follows the runbook [wiki/decisions/extraction-frames-induction-runbook.md](../../wiki/decisions/extraction-frames-induction-runbook.md):

1. **Dense sampling**: `scripts/sample-frames.sh <video> /tmp/<slug>-samples/ <cadence>`. Cadence depends on video type (cf. runbook table, default 20 s for dense videos, 30 s for talks, 60 s for quizzes).
2. **Image-diff**: `scripts/diff-frames.py /tmp/<slug>-samples/ [--roi …] [--threshold …] --output /tmp/<slug>-transitions.md`. ROI is only applied if a **domain annex** of the runbook justifies it for this video type; otherwise full frame by default.
3. **Visual cataloging**: spawn an `Explore` agent with the transitions table and the prompt of Step 3 of the runbook → table classified `KEEP / DUPLICATE / SKIP`.
4. **Transcript induction**: for each `KEEP` frame, extract the `[t-30s, t+30s]` transcript window and annotate it (citation, concept, justification). Downgrade to `SKIP` if no pedagogical justification. Output: `/tmp/<slug>-induction.md`.
5. **Manual batch validation**: show the induction table to the user in a single `AskUserQuestion` multiSelect (Promote / Duplicate / Skip / Re-extract). The main context reads each candidate PNG and presents a textual description per option.
6. **1080p extraction**: for each `Promote` frame: `ffmpeg -nostdin -i <video> -ss <ts> -frames:v 1 -q:v 1 /tmp/<slug>-finals/<slug>.png -y`.
7. **Promotion**: `cp /tmp/<slug>-finals/<slug>.png raw/frames/YYYY-MM-DD-<source-slug>-<slug>.png`.
8. **Re-spawn the expert agent** on the source page in forced re-ingest, with: list of promoted frames, transcript citation ±30 s per frame, explicit instruction to **transcribe each frame as markdown** (Step 9 of the runbook) into `wiki/sources/`, `wiki/concepts/`, `wiki/cheatsheets/`, `wiki/syntheses/` depending on the agent's deliverables.
9. Report: `Mode B frames: N promoted · M skipped · K re-extracted`.

### 5. SKIP mode

If SKIP is retained: no frame extraction. Annotate in the source page: `> [!info] Frame extraction skipped — video judged non-visual or too short.`. Log in `wiki/log.md`.

### 6. Disposition of the local video

For local videos (not YouTube): propose deletion / out-of-vault archiving (`~/Archive/llm-wiki-videos/`) / retention (discouraged). **This step happens after frame extraction** (mode A, mode B or skip).

---

**Note**: dispatch to the domain-expert agent goes through standard `/ingest` — no shortcut path. The agent receives the frames convention in its spawn context; it has a `## Visual frames` section across all domains.
