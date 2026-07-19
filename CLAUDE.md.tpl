# {{vault_name}} — Personal wiki schema

This vault is an **LLM Wiki**: a knowledge ecosystem maintained by an LLM, centered on the user ({{name}}) and their domains of interest.

## Roles

- **Human**: curates sources, asks questions, guides the analysis.
- **LLM (you)**: read, synthesize, cross-reference, maintain. You don't invent — you rely on cited sources.

## Architecture

```
.claude/
  agents/        # Claude Code subagents — one expert per domain (+ accumulated suggestions for evolution)
  agent-memory/  # cross-session memories per agent (domain state, pending patterns)
  commands/      # slash commands (/ingest, /ingest-video, /query, /save, /lint, /evolve-agent, /domain, /update-vault, /create-issue{{slash_commands_extras}})
  rules/         # conventions auto-loaded by Claude Code via the `paths` field in their frontmatter
  template-version  # template version this vault is aligned with

raw/                 # IMMUTABLE raw sources — what the wiki references.
  notes/             # personal experience notes (text)
  transcripts/       # video/audio transcripts (YYYY-MM-DD-slug.md + timestamps)
  videos-meta/       # video pointers/metadata
  frames/            # frames effectively used by the wiki (promoted from cache)
{{tracked_repos_arborescence}}  # + articles/, pdfs/, clippings/... as needed

cache/                 # TRANSIENT artifacts — never referenced by the wiki, purgeable at any time.
  videos/              # downloaded/dropped videos, removed after transcription
  audio/               # extracted audio, removed after transcription
  frames/              # candidate frames, promoted to raw/frames/ if used
{{tracked_repos_cache}}
wiki/          # LLM-generated pages. You own this layer.
  index.md     # minimal human portal (overview, radar, log, domains)
  log.md       # chronological journal (ingest, query, lint, evolve)
  radar.md     # open questions & points of attention — fed at every ingest
  overview.md  # user portrait, updated continuously
  domains/     # root pages of major domains (hubs)
  entities/    # people, companies, products, places
  concepts/    # ideas, theories, frameworks
  sources/     # one page per ingested source (YYYY-MM-DD-slug.md)
  syntheses/   # archived substantial answers
  decisions/   # architectural choices about the vault itself (ADR-lite)
  cheatsheets/ # synthesis tables, thresholds, matrices
  diagrams/    # Mermaid / ASCII diagrams

scripts/       # utilities (audio extraction, transcription, frame sampling, image-diff{{tracked_repos_scripts_extras}})
  migrations/  # breaking migrations between template versions, invoked by /update-vault
```

## User domains

{{domains_section}}

Each domain has a page in `wiki/domains/` that serves as a hub.

## Conventions

Writing conventions (frontmatter, slugs, callouts, immutability of `raw/`) are formalized in `.claude/rules/` and **auto-loaded** by Claude Code via the `paths` field in each rule's frontmatter. See `.claude/rules/frontmatter.md`, `.claude/rules/pages-wiki.md`, `.claude/rules/raw-vs-cache.md`.

Three critical residual rules:

- **`raw/` is strictly immutable.** No exceptions. No agent or script ever rewrites a file in `raw/`.
- **YAML frontmatter is mandatory** on every wiki page, with `source_sha256` computed via `shasum -a 256 <file>` — never a textual placeholder.
- **Slugs in `kebab-case.md`**, internal links as `[[wikilinks]]` Obsidian-style.

## Per-domain expert agents

Ingestion is **delegated to a domain-expert agent** matching the source. Agents live in `.claude/agents/`:

{{agents_section}}

Each agent has a **deliberately open** prompt (not a closed checklist) and **writes directly** into `wiki/` pages it owns (sources, concepts, entities, etc.). It concludes with three parsable blocks per `.claude/agent-output-contract.md`: `## Ingest summary`, `## Radar items`, `## Evolution suggestions`. The **main context** (not the agent) appends those blocks to `wiki/log.md`, `wiki/radar.md`, and `.claude/agents/<domain>-expert.suggestions.md` to feed `/evolve-agent`.

Operational memory lives in `.claude/agent-memory/<domain>/` (`MEMORY.md` + `patterns_pending.md` + free-form notes): the agent reads it at startup and updates it at ingest end. Distinct from `.suggestions.md` (behavioral rules for `/evolve-agent`). No `.claude/rules/agent-memory.md` — subagents don't load `.claude/rules/` from the main context.

The agent dispatch in `/ingest` proposes an agent with a confidence level + justification, then the user validates via `AskUserQuestion`. See `.claude/commands/ingest.md` for details.

Beyond ingest, experts can be **selectively** delegated read-side judgment tasks — per-domain radar triage (`/radar`), the semantic pass of `/lint`, and a mono-domain judgment `/query`. Delegation is never the default: fact retrieval and cross-domain questions stay in the main context (tiered loading). See `.claude/agent-output-contract.md` (Read-side delegation contract) and the `/radar`, `/lint`, `/query` commands.

## Workflows

Detailed workflows live in `.claude/commands/`. Summary table:

| Slash-command | Role |
|---|---|
| `/ingest [path]` | Idempotent ingestion of `raw/` files via the matching domain-expert agent |
| `/ingest-video <url-or-path>` | Pipeline: video → transcript → ingest → frames (optional) |
| `/sync-repos [names]` | Immutable snapshot of tracked GitHub repos (if `tracked-repos.config.json` is present) |
| `/query <question>` | Search the wiki with citations, optional archive |
| `/save <slug>` | Archive the latest synthesis into `wiki/syntheses/` |
| `/radar [domain]` | Show the radar; selectively delegate per-domain triage to domain experts |
| `/lint` | Detect contradictions, orphans, gaps |
| `/evolve-agent <domain>` | Curated evolution of an agent's prompt from its accumulated suggestions |
| `/domain <add\|rename\|remove> <slug>` | Manage a domain's lifecycle post-bootstrap (instantiate / rename / strip across all canonical declarations + frontmatters + wikilinks, with bucketed validation) |
| `/update-vault` | Pull upstream template improvements (versioned migration machine) |
| `/create-issue [type]` | Open a sanitized issue on the upstream template repo from the current context |
| `/compress-bb [slug]` | Save the current session journal into `raw/notes/sessions/YYYY-MM-DD-<slug>.md` |

For the radar: "show me the radar" / "what's on the agenda today" → read `wiki/radar.md` + extract accumulated agent suggestions (≥2 occurrences OR judged structural). **If a radar entry concerns the template environment** (bug or gap touching `scripts/`, `.claude/commands/`, `BOOTSTRAP.md`, or any file propagated by `/update-vault`), suggest the user file it via `/create-issue <type>` — don't create the issue yourself, just surface the command.

## Architectural decisions

Structural choices about the vault (workflows, conventions, tooling — not knowledge domains) go to `wiki/decisions/` in ADR-lite format: Problem → Discarded options → Decision → Why → Open questions. No numbering, descriptive slug. If a decision is revised, create a new one that cites and supersedes the old.

## Session start (signals from `cache/`)

At the start of each session, check the signals left in `cache/`:

- **`cache/.pending-ingest`**: paths awaiting ingestion. Run `bash scripts/scan-raw.sh` first — purge silently the `SKIP` (stale, already ingested), suggest `/ingest <path>` for `NEW` / `MODIFIED` entries. Remove the file if empty.
- **`cache/.session-pending`**: the previous session had unjournaled changes (commits + modified files detected by the `Stop` hook). Suggest `/compress-bb <slug>` to archive the journal into `raw/notes/sessions/`. Delete the file after the proposal.

These checks are silent if the files are absent.

## Writing principles

- Vault language: **{{vault_language}}** — every wiki page is written in this language, regardless of the source's original language. Technical terms in VO (original) when the VO usage is dominant.
- One page = one idea/entity. >400 lines → split.
- Always cite sources (`sources:` frontmatter + `[[source-slug]]` inline for specific claims).
- Short lists and tables > long paragraphs.
- Neutral tone for `entities/`, `concepts/`. More personal for `overview` and `domains/`.

## What NOT to do

- **One source = one file in `raw/`.** No ingestion from memory or conversation. To bring in a personal takeaway: drop it first as `raw/notes/YYYY-MM-DD-<topic>.md`, then ingest normally.
- **Never reference `cache/` from the wiki.** Its contents may disappear at any time.
- **Never modify files in `raw/`.** A source that evolves → new file, never overwrite.
- **No page for every concept mentioned in passing**: threshold ≥ 2 sources OR judged structural by the user.
- **No long introductions, no meta-commentary.**
