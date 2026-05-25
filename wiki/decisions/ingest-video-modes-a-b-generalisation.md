---
type: decision
domains: [meta]
created: 2026-04-29
updated: 2026-04-30
sources: []
summary_l0: "Video frames generalization: A/B modes for every expert agent, packaged scripts, mandatory markdown transcription"
summary_l1: |
  The decision unifies video extraction across all agents through two complementary modes: light mode A ("frame requests" declared by the agent) for visual-poor videos, heavy mode B (cross-induction in 9 steps) for visual-dense videos. The main context dynamically proposes the right mode based on density and duration. Each agent receives a "Visual frames" section with domain-specific verbal triggers. Extraction scripts packaged (sample-frames.sh, diff-frames.py). Every promoted frame must be transcribed as markdown to make content queryable without re-viewing.
---
# Decision — Generalize `/ingest-video` & frame extraction across all agents

## Problem

Before this decision, two video frame-extraction pipelines coexisted but neither was usable cleanly by the expert agents:

1. **Light mode ("frame requests")** — the agent declares timestamps from the transcript via a `## Frame requests` block. Implemented in [.claude/commands/ingest-video.md](../../.claude/commands/ingest-video.md). The `## Visual frames` section was historically absent from most agents.

2. **Heavy mode ("cross-induction")** — 8-step pipeline documented in [[decisions/extraction-frames-induction-runbook]]. No integration into `/ingest-video`, no packaged script (ffmpeg/Python commands inline in the runbook), runbook initially scoped to a single use case.

Consequences:
- Several agents could capture nothing visual from their videos.
- Heavy mode stayed a sub-case, while visually dense videos exist in every domain (software demos, tool captures, dashboards, schemas).
- No tooling to reproduce the heavy mode outside of a human copy-pasting ffmpeg commands.
- **Orphan frames**: a frame promoted without markdown transcription forces every future `/query` to re-analyze the image at every call — recurring cost, loss of grep/search indexability.

## Discarded options

- **Heavy mode only, drop the light mode**: we'd lose the simple "2-4 frames on a 1-hour talk" reflex without having to spin up an 8-step pipeline. Too costly for visual-poor videos.
- **Light mode only, don't generalize the heavy mode**: we'd keep systematic under-extraction on dense videos (≥30 min, ≥10 visuals).
- **Silent auto-trigger of mode A vs B**: the main context switches without asking. Risky — invests heavy compute on videos that didn't deserve it, or misses frames by staying on light mode.
- **Systematic `AskUserQuestion` before every video**: adds an interruption to every ingest, even on obvious podcasts.

## Retained decision

### A. The two modes coexist and are usable by every agent

- **Mode A (light, frame requests)**: `## Visual frames` section inserted into every expert agent prompt generated from the template, with domain-specific verbal triggers.
- **Mode B (heavy, cross-induction)**: [[decisions/extraction-frames-induction-runbook]] runbook *domain-agnostic*, domain specifics moved to **Domain annexes**. The pipeline is driven by `/ingest-video` and the main context, not by the agent — so no agent prompt changes for mode B.

### B. `/ingest-video` proposes the right mode, the user picks

After transcription + standard ingest, `/ingest-video` computes signals (duration, density of visual mentions in the transcript, number of frames declared by the agent) and proposes A / B / Skip via `AskUserQuestion` with a justified recommendation. No silent auto-trigger. Explicit overrides available: `--induction`, `--mode-a`, `--skip-frames`.

### C. Heavy-pipeline scripts packaged

- [scripts/video/sample-frames.sh](../../scripts/video/sample-frames.sh): dense ffmpeg sampling with parameterizable cadence (default 20 s).
- [scripts/video/diff-frames.py](../../scripts/video/diff-frames.py): optional ROI image-diff (default full frame `0,0,1,1`), parameterizable threshold, markdown output of transitions.

### D. Mandatory markdown transcription after promotion (Step 9 of the runbook)

Every promoted frame (mode A as well as mode B) **must** be transcribed as structured markdown into the wiki page that consumes it — to make the content queryable by `/query` without re-viewing. Format depends on the visual type (table / Mermaid / code / KPI list / semantic description). A frame without markdown transcription is an ingest defect.

## Why

- **Wiki coherence**: every agent gets the same frames primitive, otherwise domains outside the original sub-case stay blind.
- **Cost respect**: mode B is worth the investment only on sufficiently dense videos; the user proposal avoids silent over-extraction.
- **No dubious implicit default**: full-frame ROI by default, no specific geometry imposed on every video.
- **Queryable index**: markdown transcription at promotion time pays off immediately on every future `/query`. Without it, indexing debt accumulates.

## Scope of changes

| File | Action |
|---|---|
| [[decisions/extraction-frames-induction-runbook]] | Domain-agnostic rewrite + Domain annexes (empty skeletons to enrich as ingests come in) + Step 9 |
| `.claude/agents/<domain>-expert.md` (all) | `## Visual frames` section (mode A) with domain triggers + mandatory markdown transcription |
| [scripts/video/sample-frames.sh](../../scripts/video/sample-frames.sh), [scripts/video/diff-frames.py](../../scripts/video/diff-frames.py) | Packaged in the template |
| [.claude/commands/ingest-video.md](../../.claude/commands/ingest-video.md) | A/B dispatcher (user proposal) + mode B pipeline branch |
| [CLAUDE.md](../../CLAUDE.md) | INGEST-VIDEO section updated |
| `wiki/domains/<d>.md` | Cross-ref to the runbook |

## Open questions

- **Refine domain-specific verbal triggers**: the initial lists (inserted into each agent at bootstrap) are starter proposals. They should evolve with the first video ingests in each domain.
- **Runbook domain annexes**: today they're skeletons. To be enriched from real ingests (no premature invention).
- **Markdown transcription performance**: is an expert agent always capable of faithfully transcribing a complex schema? To measure on real cases and tune (maybe a specialized deliverable for complex diagrams).
- **Full-multiSelect batch mode at Step 6**: on batches of 50+ unambiguous frames, a batch mode without per-frame question would be acceptable. To test.

## Cross-refs

- [[decisions/extraction-frames-induction-runbook|Cross-induction runbook]] (the heavy pipeline itself)
