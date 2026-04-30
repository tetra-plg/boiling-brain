# BoilingBrain

![status: experimental](https://img.shields.io/badge/status-experimental-orange) ![license: MIT](https://img.shields.io/badge/license-MIT-blue) ![claude code](https://img.shields.io/badge/built%20for-Claude%20Code-purple)

> Bootstrap template for an **LLM Wiki** — a personal knowledge base curated by you and maintained by LLM agents.

## Status

Early-stage. The template works end-to-end and has been used to scaffold real vaults, but expect breaking changes to `BOOTSTRAP.md` and `*.tpl` files before a v1.0.0. See [CHANGELOG.md](./CHANGELOG.md) for milestones. Bug reports and generic-improvement PRs welcome — see [CONTRIBUTING.md](./CONTRIBUTING.md).

## Quick start

```bash
gh repo clone tetra-plg/boiling-brain ~/my-vault
cd ~/my-vault
claude
```

Then in Claude Code:

```
Lis BOOTSTRAP.md et exécute le prompt.
```

The interview takes 5-10 minutes. At the end your vault is personalized, the template's git history is reset, and you can run your first `/ingest`. Detailed flow → [How to bootstrap](#how-to-bootstrap) below.

## What is an LLM Wiki?

A vault where:

- **You** curate sources (notes, transcripts, articles, repo docs) into an immutable `raw/` folder.
- **Domain expert agents** ingest those sources and write the wiki layer (`wiki/sources/`, `wiki/concepts/`, `wiki/entities/`, etc.) — one agent per domain you care about.
- **Slash commands** (`/ingest`, `/query`, `/lint`, `/evolve-agent`, …) orchestrate the agents.
- The wiki is **always derivable from `raw/`** — no orphan knowledge, no hallucinated links.

The pattern follows Karpathy's "knowledge compilation" idea: keep the source of truth compact, hash-addressed and immutable; let LLMs maintain a queryable layer on top.

## How does this differ from Karpathy's LLM Wiki?

Karpathy's LLM Wiki is a **concept**: notes maintained by an LLM, with the LLM filling cross-references and refactoring on demand. BoilingBrain is an **opinionated, runnable implementation** of that concept — with concrete trade-offs you can either accept or fork. Specifically :

| Dimension | Karpathy's sketch | BoilingBrain |
|---|---|---|
| **Source of truth** | Notes in a folder, LLM rewrites freely | `raw/` is immutable, hash-addressed (`source_sha256`); the wiki layer is always derivable |
| **Agent topology** | One LLM doing everything | One **expert agent per domain**, declared at bootstrap, with deliverable signatures (cheatsheets, syntheses, diagrams) and per-domain prompts that evolve over time via `/evolve-agent` |
| **Idempotence** | Manual | `/ingest` is hash-based and idempotent — re-running doesn't duplicate; `--force` re-applies new agent reflexes to existing sources |
| **Multimodal** | Text-only typically | First-class video pipeline (`/ingest-video`): download → transcribe → frame extraction (mode A declarative or mode B image-diff induction) → markdown transcription of visuals (tables, Mermaid, LaTeX) so queries don't re-OCR each time |
| **Queries at scale** | Load and read | **Tiered loading**: every page carries `summary_l0` (≤140 chars) + `summary_l1` (~50-150 words). Agents scan a domain via TOC L0, descend to L1 then L2 only when relevant — sublinear in body size |
| **External code/docs** | Out of scope | `/sync-repos` snapshots GitHub repos by SHA into `raw/tracked-repos/<sha>/`, immutable, never overwritten |
| **Self-improvement** | Implicit, ad-hoc | Explicit human-curated loop: each agent appends `Evolution suggestions` per ingest, `/evolve-agent <domain>` reviews + applies the diff, archives integrated suggestions |
| **Architectural decisions** | Mixed into notes | ADR-lite in `wiki/decisions/` with a fixed structure (Problem → Options → Decision → Why → Open questions) |

Said otherwise: Karpathy says "let LLMs maintain a wiki." BoilingBrain says "*here's what the wiki layout, the agent contract, the ingest protocol and the evolution loop need to look like for that to actually scale past a few weeks of use.*" The opinions come from real usage — fork them if they don't fit.

## Why a template?

This repo is the **scaffolding**, not a usable instance. It contains:

- Generic slash commands (`/ingest`, `/ingest-video`, `/query`, `/save`, `/lint`, `/evolve-agent`, optional `/sync-repos`).
- Generic scripts (`scan-raw.sh`, `transcribe.sh`, `sample-frames.sh`, `diff-frames.py`, `extract-frames.sh`, `backfill-summaries.py`, `enrich-hub.py`, optional `sync-repos.sh`).
- Templated files (`*.tpl`) with `{{placeholder}}` markers that need to be filled with **your** name, role, domains, and projects.
- A unified `domain-expert.md.tpl` that gets instantiated **once per domain** you declare at bootstrap time, with domain-specific deliverables, observation triggers and frame-visual formats.

## Do NOT clone this repo directly

This template is not meant to be cloned and edited by hand. Each placeholder has dependencies on others (e.g. domain count drives how many agent files exist; the hub-pivot domain gets a special marker; `/sync-repos` is included only if you declare GitHub repos to track).

A **bootstrap prompt** (`BOOTSTRAP.md`, shipped at the root of this repo) walks you through a structured interview, generates the resolved files, and writes them to your machine.

Among other questions, the bootstrap asks whether you want to track GitHub repos (i.e. snapshot their docs by SHA into `raw/`); if yes, `/sync-repos` is included. Otherwise it's removed.

## How to bootstrap

See [Quick start](#quick-start) above for the commands. A few details on what happens during and after the bootstrap:

- `BOOTSTRAP.md` and `PLACEHOLDERS.md` are moved into `wiki/decisions/` as ADR traces — you can re-read them later to understand how your vault was generated.
- The template's `.git/` is replaced by a fresh history (clean start, no leftover template commits).
- An optional GitHub remote is created via `gh repo create` if you confirm during the interview.

If you really want to clone manually and skip the bootstrap, read every `*.tpl` file, fill placeholders by hand, and rename to drop `.tpl`. You will probably forget the cross-file consistency checks the bootstrap prompt enforces.

## Architecture in 60 seconds

```
.claude/
  agents/        # one <domain>-expert.md per domain you declared
  agent-memory/  # one MEMORY.md per agent (state of the domain)
  commands/      # slash commands (generic, no per-instance customization)

raw/             # IMMUTABLE source files. Never modified after first write.
cache/           # transient artifacts (downloaded videos, audio, frames). gitignored.

wiki/            # the LLM-maintained layer.
  index.md       # minimal portal: overview, radar, log, domains
  log.md         # chronological journal
  radar.md       # open questions and points of attention
  overview.md    # your portrait
  domains/       # one hub per domain
  sources/ entities/ concepts/ syntheses/ cheatsheets/ diagrams/ decisions/

scripts/         # utilities (transcription, frame extraction, image-diff, summary backfill, hub enrichment, ...)

CLAUDE.md        # project-wide LLM instructions (architecture, conventions, workflows)
tracked-repos.config.json  # OPTIONAL: list of GitHub repos to snapshot via /sync-repos
```

## Tiered loading

Every wiki page carries two extra frontmatter fields:

- `summary_l0` — single line, ≤140 chars. Telegraphic. Used as TOC entry when an agent scans an entire domain.
- `summary_l1` — 2-5 sentences (~50-150 words). Used when the agent decides whether to load the full body.

This lets agents (and you, via `/query`) navigate the wiki without paying the full body cost on every page they consider. See `wiki/decisions/tiered-loading-wiki.md` for the rationale.

## Slash commands shipped

| Command | Purpose |
|---|---|
| `/ingest [path]` | Batch idempotent ingestion of files from `raw/` via domain experts. Hash-based, no duplicates. |
| `/ingest-video <path-or-url>` | Pipeline: download → transcribe → ingest transcript → propose frame extraction (mode A / B / skip). |
| `/query <question>` | Answer from indexed pages with citations; optionally archive the synthesis. |
| `/save <slug>` | Archive the current synthesis into `wiki/syntheses/<slug>.md`. |
| `/lint [domain]` | Detect contradictions, orphans, missing cross-references, gaps. |
| `/evolve-agent <domain>` | Curated update to a domain expert's prompt, fed by accumulated `.suggestions.md`. |
| `/sync-repos [names]` *(optional)* | Snapshot GitHub repos by SHA into `raw/tracked-repos/` (or any `dest` declared per source). |
| `/update-vault` | Cherry-pick improvements from the upstream template into your vault instance. |

## Workflow loop

1. Drop a source into `raw/` (note, transcript, PDF, repo doc snapshot).
2. Run `/ingest`. Main context proposes a domain expert; you confirm via `AskUserQuestion`. Agent writes `wiki/sources/`, `wiki/concepts/`, `wiki/entities/`, optionally cheatsheets / syntheses / diagrams. Open questions land in `wiki/radar.md`.
3. Tomorrow morning, ask "show me the radar" — Claude reads `radar.md` and the accumulated `.suggestions.md` of each agent, proposes the day's priorities.
4. After a few ingestions in a domain, run `/evolve-agent <domain>` to fold accumulated suggestions back into the expert's prompt.
5. Use `/query` whenever you need to answer something from the corpus. Substantial answers can be archived via `/save`.

## FAQ

### Do I need to know which domains I want before bootstrapping?

Roughly. The bootstrap interview will ask you to list 3-6 domains with a one-line description each, mark one as "hub pivot" if you have a domain that feeds the others, and indicate per-domain deliverables (cheatsheets? diagrams? syntheses?). You can add domains later by writing a new agent file by hand — it's just a copy of an existing one with the placeholders filled differently.

### Why one agent per domain instead of a single generic agent?

Because each domain has different observation triggers, deliverable signatures, and visual frame formats. A poker source needs a 13×13 range grid; an astrophysics source needs LaTeX equations and EXIF metadata; a management source has confidentiality concerns. A single prompt that tries to cover all of these dilutes the signal. The unified `domain-expert.md.tpl` solves this by being templated rather than generic at runtime.

### What about the `/evolve-agent` loop — is it dangerous?

No. `/evolve-agent <domain>` reads the suggestions accumulated by an expert across ingestions, proposes a **diff**, and waits for your approval before writing. The previous prompt is preserved (suggestions integrated are archived in a separate file). It's an **explicit, human-curated** improvement loop, not silent self-modification.

### Can I keep my `raw/` folder separate from this repo?

Recommended actually — `raw/` is gitignored by default (see `.gitignore`). Your sources are personal; commit only the `wiki/` layer if at all. Many users keep the whole vault in a private repo separate from the template clone.

### How do I handle large videos?

The `LLMWIKI_VIDEO_CACHE` environment variable points to a directory where video files are stored. Default is `cache/videos/` (in-vault). Override to an external SSD or a dedicated cache directory if you process many or large videos. The wiki itself never references `cache/` — only `raw/transcripts/` and `raw/frames/` are referenced.

### How do I add my own domain-specific tools?

Drop them in `.claude/commands/` (slash-commands) or `scripts/` (utilities). They live in your instance and never need to be merged back into the template.

**Concrete example:** in one of the early instances of this template, the user added `/extract-range-grid` — a poker-specific OCR pipeline for range matrices — alongside the core pipeline. The slash-command (`.claude/commands/extract-range-grid.md`) and the Python script (`scripts/extract-range-grid.py`) live in their vault, not here. Yours can do the same for whatever your domains need: a LaTeX renderer, a k8s manifest validator, a financial-statement parser — anything that's a natural extension of one of your domains.

### What about secrets / credentials?

Don't commit them. Use the `.gitignore` (already excludes `cache/`, `raw/`, `Clippings/`). For repo-syncing via `/sync-repos`, authentication relies on `gh auth login` — no tokens stored in the vault.

## License

MIT. See `LICENSE` (added by GitHub when the repo was created).

## Contributing

This template is opinionated. The opinions come from real usage. If you have a generic improvement (better hub structure, better tiered-loading default, a missing slash command), feel free to open an issue or PR. Domain-specific tooling — keep it in your own instance and document it in your README.

---

*Generated as part of the Phase 2 scaffolding of the LLM Wiki bootstrap.*
