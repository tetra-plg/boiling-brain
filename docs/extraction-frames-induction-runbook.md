---
type: decision
domains: [meta]
created: 2026-04-29
updated: 2026-04-30
sources: []
summary_l0: "Long-video frame extraction: dense sampling + image-diff + cross-induction with transcript + batch validation + markdown transcription"
summary_l1: |
  This runbook describes a 9-step process to extract relevant frames from long videos (>30 min) where simple methods under-extract. Each step crosses several signals: dense sampling, pixel-diff computation, agent-driven visual cataloging, validation against the transcript (±30s), high-resolution extraction, batch manual validation, then markdown transcription of the content. Applicable to every wiki domain. Recommended for visually dense videos or suspected under-extraction.
---
# Runbook — Frame extraction by cross-induction (sampling × image-diff × transcript × manual validation × markdown transcription)

> Cross-domain asset. Reusable by every expert agent of the wiki. Domain specifics (specific software UIs, OCR profiles, cheatsheet formats) are pushed into the **Domain annexes** section at the end of the runbook.

## Problem

Long videos (>30 min) — coachings, conferences, software demos, UI tutorials, commented replays — alternate between slides, screen captures, schemas and talking head. Simple methods miss frames:

- **Direct frame requests by the expert agent** (light mode `/ingest-video`): systematic under-extraction on dense videos. The agent doesn't "see" anything — it infers from the transcript phrases like "look at this table", but misses visuals shown without explicit verb cues, or conversely over-extracts visually pretty but pedagogically empty frames.
- **Global-threshold image-diff**: misses subtle transitions (color change inside a grid, menu pop-up, "build animation" slide). Also: promotes "pretty but not pedagogical" frames.
- **Exhaustive visual cataloging without transcript**: promotes duplicates (the same visual during 2 minutes of discussion = 1 useful frame, not 10).

→ Need a process that **cross-references several signals** and keeps the human in the loop for ambiguous decisions — and that produces **queryable markdown** for every frame, not just an image.

## Discarded options

- **Extract everything every 5 s**: 800–1000 frames per video, unmanageable manually, huge noise.
- **Total delegation to an agent**: without human validation, systematic biases (e.g. the agent keeps everything "new" even when it's a trivial variant of a previous slide).
- **Image-diff alone**: see Problem.
- **Transcript alone (frame requests)**: see Problem.
- **Image-only (PNG without markdown transcription)**: without transcription, every `/query` must re-analyze the image, loses grep/search indexability, raises recurring cost.

## Retained decision: 9-step process

### Step 1 — Dense sampling

**Goal**: materialize on disk enough candidates so the image-diff finds every transition.

**Default cadence by video type**:

| Video type | Cadence | Typical sample volume |
|---|---|---|
| Dense coaching (matrix slides, grids, fast UI demos) | every 20 s | 100–250 |
| Conference / talk with text slides | every 30 s | 60–150 |
| Software demo / UI tutorial | every 20–30 s | 80–200 |
| Punctuated interview / talking head | every 60 s | 30–80 |
| Quiz / short slides | every 60 s | 30–60 |

**Standard command** (packaged in [scripts/video/sample-frames.sh](../../scripts/video/sample-frames.sh)):
```bash
scripts/video/sample-frames.sh "$VIDEO" /tmp/<slug>-samples/ [cadence_seconds]
```

Output: 1280×720 PNGs in the samples folder, plus a `.cadence` file remembering the cadence for step 2.

### Step 2 — Image-diff filtering

**Goal**: eliminate redundant samples (continuous talking head, stable slide).

**Method**: for each `(sample_n, sample_n+1)` pair, compute the average grayscale pixel difference. Optionally restrict the computation to an **ROI** (region of interest) to ignore an unchanging zone (overlay, watermark, fixed webcam).

**Command** (packaged in [scripts/video/diff-frames.py](../../scripts/video/diff-frames.py)):
```bash
scripts/video/diff-frames.py /tmp/<slug>-samples/ \
  [--roi x,y,w,h] \
  [--threshold 12.0] \
  --output /tmp/<slug>-transitions.md
```

**Default ROI: `0,0,1,1`** (full frame, no exclusion). Only use a custom ROI if you know that a specific area carries no relevant visual information — see the **Domain annexes** section for documented ROIs per use case. Do not apply a "standard" ROI blindly, it is a source of false negatives.

**Default threshold: `12.0`**. Lower → more transitions kept (and more noise). Higher → you miss subtle transitions.

Output: `/tmp/<slug>-transitions.md`, table `# | sample_path | estimated_timestamp | diff_mean`. Typical reduction ×3 to ×5 vs. samples.

### Step 3 — Visual cataloging (Explore agent)

**Goal**: for each transition, classify the visual and decide KEEP / DUPLICATE / SKIP.

**Delegated to an `Explore` agent** per video (parallelizable in background if multiple videos batched). Sample prompt:

```
For each transition frame in /tmp/<slug>-transitions.md:
- Read the PNG.
- Classify the visual type: TEXT SLIDE / TABLE / SCHEMA / UI CAPTURE / CODE / DASHBOARD / PHOTO / TALKING HEAD / TRANSITION / OTHER.
- Describe the content in 1 line (e.g. "4-column comparison table: tool name, latency, price, hit rate").
- Verdict: KEEP (unique pedagogical content) / DUPLICATE (minor variant of the previous one) / SKIP (talking head, pure transition, non-pedagogical content).
- Suggested slug (kebab-case) if KEEP.

Output: markdown table with columns # | timestamp | type | description | verdict | suggested slug.
```

For domains with their own UI-recognition heuristics (see Domain annexes), enrich the prompt with those heuristics.

### Step 4 — Cross-induction frames × transcript

**Critical goal**: validate every `KEEP` frame by looking at **what the speaker says ±30 s around the timestamp**.

For each `KEEP` frame from the step 3 table:
- Extract the transcript window `[t-30s, t+30s]`.
- Annotate: main quote (short verbatim), concept addressed, justification (why this frame deserves extraction).
- If the transcript window mentions **no pedagogical element justifying the frame** → **DOWNGRADE to SKIP** even if marked KEEP at cataloging.

**Benefits**:
- Avoids "pretty but not pedagogical" frames.
- Allows attaching a quote to every promoted frame (directly reusable in the markdown transcription of step 9).
- Guarantees that videos are covered proportionally to their actual pedagogical richness.

**Output**: consolidated table `/tmp/<slug>-induction.md` — **extraction contract**. Columns: `# | timestamp | type | description | transcript quote | concept | final verdict | slug`.

### Step 5 — Native 1080p extraction

Re-extraction from the source file at validated timestamps, full resolution:

```bash
ffmpeg -nostdin -i "$VIDEO" -ss 00:HH:MM:SS -frames:v 1 -q:v 1 \
  /tmp/<slug>-finals/<slug>.png -y
```

`-ss` **AFTER** `-i` for frame-perfect precision. On very long videos (>25 min of seek), a pragmatic mode puts `-ss` before `-i` to gain time at the cost of lower precision.

### Step 6 — Manual batch validation

**Goal**: settle final ambiguities and capture nuances agents miss.

**Single batch mode** (preferred to reduce interruptions):
- All extracted frames presented in a single `AskUserQuestion` multiSelect.
- Per-frame options: Promote / Duplicate / Skip / Re-extract (±5 s).
- The main context reads each PNG (Claude vision) and presents a synthetic textual description to help the user decide without manually opening each image.

**Frame-by-frame mode** (fallback for highly ambiguous videos):
- `open /tmp/<slug>-finals/<frame>.png` → opens in Preview.
- `Read` the frame → description.
- `AskUserQuestion` one by one.

**Observed cadence**: ~30–60 s per decision in frame-by-frame mode → ~80–150 min for 150 frames. The batch mode typically divides this by 3–4.

### Step 7 — Physical promotion to `raw/frames/`

For each "Promote" frame:
```bash
cp /tmp/<slug>-finals/<frame>.png \
   raw/frames/YYYY-MM-DD-<source-slug>-<final-slug>.png
```

### Step 8 — Re-spawn expert agent (forced re-ingest)

Re-spawn the domain expert agent in **forced re-ingest mode** on the source page, with the following context:
- The list of promoted frames (paths `raw/frames/...`).
- The induction table (transcript quote ±30 s + concept per frame).
- Explicit instruction to enrich the relevant wiki pages (`wiki/sources/`, `wiki/concepts/`, `wiki/cheatsheets/`, `wiki/syntheses/`) with these frames.
- Explicit instruction to **transcribe each frame as markdown** (Step 9).

The expert agent stays free in their editorial choices (which frame goes into which page, which concept deserves a new page, etc.) — the runbook gives them the frames + their pedagogical context, not a page plan.

### Step 9 — Markdown transcription of the visual content

**Fundamental goal**: make each frame's content **queryable as text**. Without transcription, every `/query` must re-analyze the image (recurring cost, no grep/search). This is the main wiki-side deliverable — the PNG image is just the supporting evidence.

For each promoted frame, the expert agent opens the PNG (`Read`) and writes the transcription into the wiki page that consumes the frame. Format depends on the visual type:

| Type | Transcription format | Structural example |
|---|---|---|
| **Table / grid** | Markdown table reproducing line by line, column by column | `\| col1 \| col2 \|` |
| **Schema / diagram** | Mermaid if topology allows, otherwise structured node + relations list | ` ```mermaid\ngraph TD ... ` or `- Node A → Node B (relation)` |
| **Code / terminal** | Code block with detected language, reproduces the readable content | ` ```python\n... ` or ` ```bash\n... ` |
| **Dashboard / KPI** | Markdown list of indicators with values and units | `- p95 latency: 312 ms` |
| **Text slide** | Title + bullets, literal reproduction | `### <title>\n- bullet 1\n- bullet 2` |
| **Photo / illustration** | Semantic description: subject, composition, caption if visible | "Photograph of a telescope, visible caption 'M51 — 60 min exposure'" |
| **UI capture** | Structured description: interface zones, buttons / fields / values visible | `Left panel: list of N items. Right panel: form with 3 fields (X, Y, Z).` |

**Non-optional rule**: a promoted frame without markdown transcription is an ingest defect. If the agent can't transcribe (illegible image, insufficient zoom, irreducible ambiguity), it flags it as `> [!question]` rather than leaving the image orphaned.

**Bonus**: the transcript quote ±30 s extracted at Step 4 must be cited next to the markdown transcription — the double layer (transcribed visual + speaker verbatim) maximizes the value of future `/query`.

## Visual-recognition heuristics (generic)

Signals that orient toward `KEEP` rather than `DUPLICATE` or `SKIP` at Step 3:

- **New structured text** on screen (title, table headers, slide bullets) absent from previous frames.
- **Explicit slide transition** (banner, animation, slide number).
- **Overlay / annotation** added by the presenter (circles a zone, arrow, highlight).
- **Capture of a different software** (UI change, new menu, pop-up).
- **Page / tab change** in a browser demo.
- **New chart / number** displayed.

Signals that orient toward `DUPLICATE`:
- Minor variant of the previous slide (cursor moved, progress bar advanced, value incremented).
- Same slide commented over time.

Signals that orient toward `SKIP`:
- Talking head, library backdrop, pure transition (fade, black screen).
- Intro / outro slide with no pedagogical content.

For heuristics specific to a piece of software or a course format, see **Domain annexes** below.

## When to apply this process (Mode B)

- Video > 30 min with ≥ 10 expected distinct visuals.
- Video where you suspect that `/ingest-video` light mode (frame requests by the agent) is under-extracting: high density of visual mentions in the transcript but few frame requests declared by the agent.
- First video of a new format for a domain (calibrate heuristics before scaling).
- Re-extraction of a video whose frames were lost / are low-resolution / lack the markdown transcription.

## When NOT to apply

- Conceptual spoken video (talking head, podcast, audio-only interview) → `/ingest-video` light mode is enough, the expert agent declares 2–4 frame requests if needed.
- Video < 15 min with ≤ 3 visuals → manual frame requests are faster.

## Existing tools to reuse

- [scripts/video/transcribe.sh](../../scripts/video/transcribe.sh) — local Whisper (mlx-whisper).
- [scripts/video/sample-frames.sh](../../scripts/video/sample-frames.sh) — Step 1.
- [scripts/video/diff-frames.py](../../scripts/video/diff-frames.py) — Step 2.
- [scripts/video/extract-frames.sh](../../scripts/video/extract-frames.sh) — one-shot extraction (`/ingest-video` mode A).
- [/ingest-video](../../.claude/commands/ingest-video.md) — orchestrator, proposes mode A / B / Skip.
- `AskUserQuestion` — interactive batch validation.

## Open questions

- **Automate step 4 (transcript induction)**: can an agent generate the cross table without bias? To test on multiple domains.
- **Step 6 full-multiSelect batch**: on batches of 50+ unambiguous frames (e.g. 100% KEEP quiz), a pure batch mode without per-frame question would be acceptable.
- **Markdown transcription automation by type**: can we delegate to a visual agent without quality dropping? Test on tables, schemas, dashboards.

---

## Domain annexes

Specifics to apply at Step 2 (ROI), Step 3 (UI-recognition heuristics) and post-Step 7 (post-processing) depending on the video's domain.

> This section is deliberately light in the template. As you ingest videos of a domain, add here the useful ROIs, UI heuristics, OCR profiles or cheatsheet formats you'll discover empirically. A good annex entry names **a precise video format** ("coaching X with fixed bottom-left webcam"), not an entire domain.

### Annex — `<your-domain>`

To enrich as ingests come in. Initial candidate heuristics:

- **Software interface captures**: new conversation, new panel → systematic KEEP.
- **Architecture / topology diagrams**: nodes + arrows → reproduce as Mermaid at Step 9.
- **Benchmark / pricing / observation graphs**: axes + curves → transcribe as a value table or semantic description.

Duplicate this annex for each of your domains declared at bootstrap.
