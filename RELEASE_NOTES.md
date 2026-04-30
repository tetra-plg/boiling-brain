# Release notes

> Use this file as input for `gh release create`. Each section is a self-contained release.

---

## v1.0.0 — First public release

**BoilingBrain** is an opinionated, runnable template for an **LLM Wiki**: a personal knowledge base where you curate the sources and a team of domain expert agents maintain the wiki layer on top. Built for Claude Code, written to be cloned, interviewed, and personalized in 5–10 minutes.

This is the first public release. The template has been used to scaffold real vaults during development (Phases 0 → 5c) and is considered stable for the documented flow. Future releases will iterate on the bootstrap interview, agent prompts, and domain-deduction heuristics based on community feedback.

### Why you might care

Karpathy floated the idea of "let LLMs maintain a wiki." BoilingBrain is one concrete answer to **what that wiki, the agents, and the ingest protocol need to look like** for the setup to keep working past a few weeks of use. The full comparison is in the README — short version: hash-addressed immutable sources, one expert agent per domain, tiered loading for sublinear queries, idempotent `/ingest`, first-class video pipeline, an explicit human-curated agent evolution loop, and ADR-lite decisions.

### What's in the box

- `BOOTSTRAP.md` — portable interview prompt (FR, ~600 lines) that walks you through 7 questions, deduces a per-domain configuration, validates it, and scaffolds the vault. Then deletes itself into `wiki/decisions/` as an ADR trace.
- 9 templated files (`*.tpl`) with **28 documented placeholders** (`PLACEHOLDERS.md`).
- 8 generic slash commands shipped: `/ingest`, `/ingest-video`, `/query`, `/save`, `/lint`, `/evolve-agent`, `/update-vault`, optional `/sync-repos`.
- 8 generic scripts: `scan-raw.sh`, `transcribe.sh`, `sample-frames.sh`, `extract-frames.sh`, `diff-frames.py`, `backfill-summaries.py`, `enrich-hub.py`, optional `sync-repos.sh`.
- 4 architectural decisions in `wiki/decisions/` (tiered loading, immutable repo snapshots, induction-based frame extraction, ingest-video modes).
- `.obsidian/` config generated at bootstrap with a graph filter that hides `raw/` and `cache/`, plus colorGroups per domain.

### How to bootstrap

```bash
gh repo clone tetra-plg/boiling-brain ~/my-vault
cd ~/my-vault
claude
```

Then in Claude Code:

```
Lis BOOTSTRAP.md et exécute le prompt.
```

The interview is in French — translations are not blocking for v1 but welcome as PRs.

### Highlights of this release

- **Hash-based idempotent ingest**: drop a source in `raw/`, run `/ingest`, never duplicate. `--force` re-applies new agent reflexes to existing sources.
- **One expert agent per domain**: declared at bootstrap, evolved over time via `/evolve-agent` with a human-curated diff workflow — no silent self-modification.
- **Tiered loading**: every page carries `summary_l0` (≤140 chars) + `summary_l1` (~50-150 words) so agents scan domains without paying full body cost.
- **Video pipeline**: `/ingest-video` covers YouTube + local files, with mode A (declarative frame requests) and mode B (image-diff induction) for visual-heavy content. Frames are transcribed to markdown (tables, Mermaid, LaTeX, etc.) so queries don't re-OCR.
- **External docs as immutable snapshots**: `/sync-repos` clones a GitHub repo at HEAD's SHA into `raw/tracked-repos/<sha>/`. New SHA = new snapshot, never overwritten.
- **`/update-vault`**: cherry-pick improvements from this template into already-bootstrapped vaults via a `template-upstream` remote.
- **Tooling**: `.github/ISSUE_TEMPLATE/` (bug + feature), `PULL_REQUEST_TEMPLATE.md`, `CONTRIBUTING.md` with a generic-only scope rule, `CHANGELOG.md`.

### Known limitations

- Bootstrap interview is **French only**. EN translation is a v0.3 candidate.
- No automated tests yet for `BOOTSTRAP.md` flow — manual scratch-clone testing only (procedure documented in `CONTRIBUTING.md`).
- The frame-extraction mode B pipeline (image-diff induction) requires `ffmpeg` and Python — install before running `/ingest-video --induction`.
- Tested on macOS + zsh + Claude Code. Linux should work; Windows is untested.

### Coming next

- EN translation of `BOOTSTRAP.md` (community contribution welcome).
- Automated smoke test for the bootstrap (clone → interview answers piped → assert structure).
- More architectural decisions promoted from real usage into `wiki/decisions/`.

### Thanks

To Andrej Karpathy for the original sketch — this is one concrete attempt at making it production-shaped.

---

## Notes for the maintainer (do NOT include in the public release body)

When publishing :

```bash
# tag the current main
git -C ~/Workspace/llm-wiki-template tag -a v1.0.0 -m "v1.0.0 — first public release"
git -C ~/Workspace/llm-wiki-template push origin v1.0.0

# make the repo public
gh repo edit tetra-plg/boiling-brain --visibility public --accept-visibility-change-consequences

# create the release using the body above (everything before the horizontal rule)
gh release create v1.0.0 \
  --repo tetra-plg/boiling-brain \
  --title "v1.0.0 — First public release" \
  --notes-file <(sed -n '/^## v1.0.0/,/^---$/p' RELEASE_NOTES.md | sed '$d')
```

Sanity-check before going public :
- `grep -rinE "pierre|le guern|merim|peije|kill.?tilt|hermes" --exclude-dir=.git .` returns nothing.
- All `tetra-plg/llm-wiki-template` references replaced with `tetra-plg/boiling-brain`.
- `BOOTSTRAP.md` examples are all anonymized (Maria Dupont / Carlos Silva / Acme Corp / data-science / ml-ops / etc.).
