# Changelog

All notable changes to this template are documented here. Format inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Versions are milestones, not strict semver. Breaking changes to `BOOTSTRAP.md` or `*.tpl` are flagged in the release notes.

---

## [v1.1.0] — unreleased

### Added

- **`scripts/mcp/mcp-wiki.py`**: stdio MCP server (FastMCP ≥ 2.14) exposing 5 tools — `scan_domain` (tiered loading L0), `preview_page` (L1), `read_page` (L2), `search_wiki`, `drop_to_raw`. The server reads `WIKI_PATH` to locate the vault.
- **`scripts/mcp/setup-mcp.sh`**: standalone installer — installs `fastmcp` (pipx first, pip --user fallback), registers the server via `claude mcp add -s user` (cross-project), adds the `Stop` hook to `~/.claude/settings.json`, and appends the instructions block to `~/.claude/CLAUDE.md` (idempotent via marker).
- **`/compress-bb`**: slash-command to save the current session journal into `raw/notes/sessions/YYYY-MM-DD-<slug>.md`, ready for `/ingest`.
- **Hooks**: `Stop` hook (`scripts/hooks/check-session-activity.sh`) detects commits + modified files → writes `cache/.session-pending`; `SessionStart` hook detects `.pending-ingest` and `.session-pending` and proposes the follow-up actions.
- **`/query` tiered loading**: L0 scan first, then L1/L2 descent only when relevant — reduces context consumption for broad questions.
- **`scripts/migrations/v1.1.0.md`**: interactive migration invoked by `/update-vault` for vaults < 1.1.0. Runs `setup-mcp.sh` (MCP + global Stop hook) and patches the vault's `CLAUDE.md` to add the "Session start" section that drives the reading of `cache/.pending-ingest` and `cache/.session-pending` signals.
- **`/update-vault`**: optional `target-branch` argument to test pre-release feat branches before merge (e.g. `/update-vault feat/v1.2.0`). Default behavior unchanged (target `main`). (#30)
- **`/domain`**: new slash-command to manage a vault's domain lifecycle post-bootstrap. Three sub-commands:
  - `/domain add <slug>` — interactive interview, fetches the 3 templates (`domain-expert.md.tpl`, `domain-memory.md.tpl`, `domain.md.tpl`) from `template-upstream` on the fly, renders them respecting vault conventions (memory-dir suffix, vault language), and inserts the new domain into the 5 canonical declaration files (`CLAUDE.md`, `README.md`, `wiki/index.md`, `wiki/overview.md`, and `.claude/commands/ingest.md` only if hardcoded dispatch is detected). Optional `--audit-migration` flag scans existing sources/concepts/entities for candidates to re-tag, with a second-pass LLM filter to cut lexical false positives.
  - `/domain rename <old-slug> <new-slug>` — full vault scan via `scripts/wiki-maint/scan-domain-refs.sh`, bucketed presentation (canonical / frontmatter / wikilink / alias / composed / prose / log-tag / historical / numeric-drift), case-by-case validation for ambiguous buckets (composed slugs, prose words, wikilink aliases). Physical renames of `<slug>-expert.md`, `<slug>-expert.suggestions[.archive].md`, memory dir, and `wiki/domains/<slug>.md`.
  - `/domain remove <slug>` — `--archive` (default) strips the domain from active declarations while preserving historical traces in `wiki/log.md`, `wiki/decisions/`, `wiki/syntheses/`, `wiki/sources/`. `--purge` proposes the historical sweep case-by-case. `--include-historical` opt-in for archive mode. (#38)
- **`scripts/wiki-maint/scan-domain-refs.sh`**: helper script (called by `/domain rename` and `/domain remove`) that scans the entire vault for a slug and emits a line-oriented report categorized in 9 buckets. Convention aligned with `scan-raw.sh` (machine-parseable, exit codes 0/1, env var `VAULT_PATH` for inter-vault testing). (#38)
- **MCP tiered-loading refactor — 7 new tools**: `scan_concepts(domain, query, top)`, `scan_entities(...)`, `scan_decisions(...)`, `scan_syntheses(...)`, `scan_cheatsheets(...)`, `scan_diagrams(...)`, `scan_sources(...)`. Per-type drill-down inside a domain. Without `query`, return the top N pages by centrality (incoming wikilinks). With `query`, filter via case + separator-insensitive tokenisation and rank by centrality.
- **`scripts/mcp/smoke_test.py`**: standalone harness that invokes every MCP tool against a real vault (`WIKI_PATH=…`), prints OK/FAIL against the v1.1.0 token gates, and exits non-zero on failure. Used as the gate before tagging v1.1.0.

### Added (ingest + agent surface)

- **`.claude/agent-output-contract.md`**: factorized contract specifying the three output blocks every expert agent returns (`## Ingest summary`, `## Radar items`, `## Evolution suggestions`) with the conceptual derivation rule. Injected into agent prompts at spawn by `/ingest`. (#19)
- **`/ingest`**: parses `## Radar items` from agent reports and propagates them to `wiki/radar.md`; purges processed and stale entries from `cache/.pending-ingest` at end of run. (#19, #24)
- **`.claude/agents/domain-expert.md.tpl`**: section "How you report back" refactored — references the contract, clarifies that the main context (not the agent) writes downstream files. (#19, #25)
- **`/evolve-agent`**: reads `.claude/agent-memory/<domain>/patterns_pending.md` in read-only mode to disambiguate suggestions. (#26)
- **`CLAUDE.md.tpl`**: section "Per-domain expert agents" documents the agent-output-contract and the agent-memory convention (no separate rule — subagents do not see `.claude/rules/`). (#26)

### Added (L3 readiness)

- **ADR template** (`wiki/decisions/decision.md.tpl`): frontmatter fields `verdict`, `verdict_date`, `verdict_evidence` (all opt-in, null by default) + `## Real feedback` section with T+30/60/90d placeholders. (#18)
- **`revisit_after` frontmatter field** on `type: decision` and `type: concept` pages (opt-in). (#18)
- **`/lint`**: flag ADRs ≥ 90 days without `verdict`, and pages whose `revisit_after` is past. (#18)

### Fixed (alpha feedback)

- **`/compress-bb`**: document "When NOT to use" to avoid redundancy with substantive `raw/notes/` (#22).
- **`scripts/wiki-maint/scan-raw.sh`**: avoid silent kill under `set -euo pipefail` when `source_sha256` absent on composite pages (#23).
- **`/update-vault`**: track applied migrations individually via `applied-migrations:` field in `.claude/template-version` — fixes silent skip of migrations added retroactively (after a version bump). Vaults pre-v1.1.0 auto-populate the field at first run post-upgrade. (#31)
- **`scripts/mcp/setup-mcp.sh`**: quote heredoc delimiter and pass shell vars via `os.environ` — vault paths containing `"` or `\` no longer corrupt the Python hook registration silently (review finding A).
- **`scripts/mcp/setup-mcp.sh`**: surface pipx install errors instead of swallowing stderr — real cause visible when fastmcp installation fails (review finding C).
- **`scripts/mcp/mcp-wiki.py`**: `scan_domain` now accepts an optional `limit` parameter (default `0` = no limit) and surfaces capping in the output (`X / Y pages`) — large domains no longer lose pages silently (#36, review finding D).

### Changed

- **Breaking — scripts layout**: `scripts/` reorganised into feature subdirectories (`video/`, `wiki-maint/`, `mcp/`, `hooks/`). Only `sync-repos.sh` and `migrations/` remain at the root. Existing vaults are migrated automatically by the `v1.1.0` migration (`scripts/migrations/v1.1.0.md`), which `git rm`s the stale flat paths and re-registers the MCP server at its new absolute path.
- **`/update-vault` — 3-way merge on file propagation**: replaces the silent overwrite (`git show template:path > vault:path`) with a content-only 3-way merge (`git merge-file`) using the previous template baseline. Vault files unchanged vs baseline fast-forward (same as before); customised vault files are auto-merged with template changes when edits don't collide; real conflicts (overlapping edits on the same lines, or files added on both sides with different content) prompt the user with four resolution options (keep markers, take template, keep vault, skip). Local edits on tracked-by-template files now survive across `/update-vault` runs.
- **`/update-vault` — slash-command slimmed to ~170 lines (from ~350)** by extracting two helper scripts: `scripts/wiki-maint/detect-vault-version.sh` (version detection + applied-migrations back-fill) and `scripts/wiki-maint/propagate-templates.sh` (file propagation with 3-way merge). The markdown command focuses on LLM-driven orchestration (AskUserQuestion, branching decisions, migration sub-workflows); the shell scripts carry their own documentation and `--help`.
- **`.claude/commands/compress-bb.md`**: translated to EN (v1.0.3 alignment, no functional change).
- **`scripts/mcp/mcp-wiki.py`**: `preview_page` outputs a whitelisted set of frontmatter fields (`type`, `domains`, `created`, `updated`, `summary_l0`, `sources`, `status`, `verdict`) instead of every field — controls verbosity with the new ADR L3 fields (review finding B).
- **Breaking — `scan_domain` return format**: no longer dumps all pages of the domain. Returns a compact hierarchical view: the `wiki/domains/<domain>.md` hub `summary_l1`, page counts per type with explicit pointers to the new `scan_<type>` tools, and the top 10 pages by centrality. Estimated reduction: ~94% on a 388-page domain (measured against BoilingBrain `ia`, dropping from ~23k to ~900 tokens).
- **Breaking — `search_wiki` return format**: replaced `<path>:<line>: <extract>` with an enriched line per result: `<path> (<type>) — <summary_l0> — wikilinks: [<slugs>]`. Matching is now tokenised (case + separator insensitive); ranking is by centrality (backlinks).
- **`scripts/mcp/setup-mcp.sh` self-heals the `~/.claude/CLAUDE.md` global block**: detects the pre-#47 5-tool block via marker and replaces it in place with the new 12-tool + tiered-loading description (12 tools = 5 originals + 7 new `scan_<type>`). Vaults already at v1.1.0 (migrated pre-#47) can re-run `bash <vault>/scripts/mcp/setup-mcp.sh` directly to refresh the LLM instructions, no `applied-migrations` edit needed. The MCP tools themselves are auto-discovered by Claude Code at session start — only the LLM-facing instructions need this refresh.
- **`/update-vault` — `force-rerun: true` migration flag**: a migration whose frontmatter contains `force-rerun: true` is re-evaluated at every `/update-vault` even when its slug is already in `applied-migrations`. Closes the case where a previously-applied migration ships a content fix that must re-execute on already-migrated vaults (e.g. `v1.1.0.md` after the #41 MCP refactor: `setup-mcp.sh` was extended to write a 12-tool LLM instructions block, but the migration had already run with the 5-tool version, so vaults stuck with the outdated block until re-run). Idempotency is the migration author's responsibility — `force-rerun: true` migrations must be safe to re-apply (a no-op when the target state is already reached).
- **`scripts/migrations/v1.1.0.md` is now marked `force-rerun: true`**: ensures every vault at v1.1.0 re-runs `setup-mcp.sh` at the next `/update-vault`, refreshing the LLM instructions block, re-checking the MCP registration, and re-checking the Stop hook entry. No-op on already-current state.

### Migration from v1.0.x

Migration to v1.1.0 is **handled by `/update-vault`**:

```bash
# In your bootstrapped vault:
/update-vault
```

`/update-vault` detects the local version (1.0.x) → target 1.1.0, propagates the new files (`scripts/mcp/mcp-wiki.py`, `scripts/mcp/setup-mcp.sh`, `scripts/hooks/check-session-activity.sh`, `.claude/commands/compress-bb.md`, `scripts/migrations/v1.1.0.md`, `/query` updated), then invokes the `v1.1.0` migration which:

1. Announces the additions and what it will mutate (`~/.claude/settings.json`, `~/.claude/CLAUDE.md`, `<vault>/CLAUDE.md`).
2. Proposes 3 options via `AskUserQuestion`: **Enable** (full setup) / **Patch vault CLAUDE.md only** (skip global mutations) / **Skip**.
3. If **Enable**: runs `bash scripts/mcp/setup-mcp.sh --vault-path <vault>` (idempotent — pip-installs `fastmcp` if missing, merges mcpServers + Stop hook, appends a marker-bounded block to `~/.claude/CLAUDE.md`).
4. Patches the vault's `CLAUDE.md` to insert the `## Session start (signals from cache/)` section (idempotent — title-based detection).
5. Dedicated commit, then bumps `.claude/template-version` to 1.1.0.

Neither `~/.claude/settings.json`, `~/.claude/CLAUDE.md`, nor `<vault>/CLAUDE.md` is ever rewritten — only content is added or merged.

If you prefer to migrate manually, read [scripts/migrations/v1.1.0.md](scripts/migrations/v1.1.0.md) which describes exactly what to change.

**Post-update actions** (one-time, after `/update-vault` completes):

- **Restart Claude Code** to reload the MCP server subprocess with the updated `scripts/mcp/mcp-wiki.py` (otherwise `scan_domain` still runs with the previously loaded code).
- **Optional — refresh the vault's `CLAUDE.md`**: PR-B enriches the "Per-domain expert agents" section of `CLAUDE.md.tpl` with references to `.claude/agent-output-contract.md` and `.claude/agent-memory/`. Existing vaults can re-align manually by diffing their `CLAUDE.md` against the new `CLAUDE.md.tpl`. Not blocking — `/ingest` reads the contract directly from disk.
- **Optional — re-run `setup-mcp.sh` if your vault path contains special characters** (`"`, `\`): the pre-PR-E heredoc could corrupt the Stop hook registration silently. Re-run `bash scripts/mcp/setup-mcp.sh --vault-path "$(pwd)"` to re-register with the fixed quoting.

## [v1.0.3] — 2026-05-06

Launch readiness pass: every file shipped at bootstrap or propagated by `/update-vault` is now in EN, plus a `{{vault_language}}` placeholder so wiki output language is decoupled from source language.

### Added

- **README "Who is this for?" section** placed before the FAQ. Frames visitor expectations (solo curators using Claude Code + Obsidian, opinionated-defaults audience, thinking-partner use case) and faux amis (team wikis, hosted SaaS, vector RAG, non-Claude-Code agents, no-code expectation).
- **README graph screenshot** ([docs/graph.png](docs/graph.png)) inserted right after the badges. Visual proof that domain clusters auto-emerge from the linking structure.
- **`{{vault_language}}` global placeholder** (29th placeholder, documented in `PLACEHOLDERS.md`). Captures the language detected at the bootstrap interview as a human label (`English`, `Français`, `Español`…), then injected into `CLAUDE.md` and every domain-expert agent so wiki pages are always written in the vault language regardless of source language.

### Changed

- **i18n template pass — every artifact translated to EN.** Every file shipped to a fresh vault at bootstrap, then propagated by `/update-vault`, is now in EN to remove the LLM mimicry risk where Claude was nudged toward FR by the surrounding prose. Files translated:
  - `BOOTSTRAP.md` (700+ lines, end-to-end, with EN AskUserQuestion payloads)
  - `CLAUDE.md.tpl`, `.claude/agents/domain-expert.md.tpl`, `.claude/agent-memory/domain-memory.md.tpl`
  - The 5 `wiki/*.tpl` (index, log, overview, radar, domain hub)
  - The 4 `.claude/rules/*.md` (frontmatter, pages-wiki, raw-vs-cache, sanitization-issues)
  - The 9 `.claude/commands/*.md` (ingest, ingest-video, query, save, lint, evolve-agent, sync-repos, update-vault, create-issue)
  - The `tracked-repos.config.json.tpl` schema_note
  - The 3 wiki ADRs (tracked-repos-immutable-snapshots, ingest-video-modes-a-b-generalisation, extraction-frames-induction-runbook)
  - Existing v1.0.1 and v1.0.2 changelog entries retro-translated to EN for consistency with the launch.
  - Multilingual at runtime is preserved via the `Detect the user's language` directive in `BOOTSTRAP.md` and the `{{vault_language}}` placeholder injected into per-vault `CLAUDE.md` and agents.
- **README polish** for the public launch: bootstrap command translated to EN (with italic note "Works in any language — the bootstrap interview adapts to your phrasing"); version label `(v1.0.0)` → `(v1.0)` (timeless); badge `status-experimental-orange` → `status-alpha-yellow` (humility was below reality); sections reordered so `What is an LLM Wiki?` and `How does this differ from Karpathy's LLM Wiki?` land before `Prerequisites` and `Quick start` (concept before installation for the Twitter visitor).

### Fixed

- **Source language vs vault language decoupling.** Before this fix, `CLAUDE.md.tpl` had `Français` hardcoded in its writing principles, and `domain-expert.md.tpl` had "titres en français". Consequence: an EN user bootstrapped a vault and every page produced by `/ingest` came out in French regardless of the source. The new `{{vault_language}}` placeholder + the explicit directive (*"Source language has no incidence on output language; quote sources verbatim, write commentary in the vault language"*) close that loop.
- **`/ingest-video` visual-mention detection was FR-only.** The `visual_mentions` counter relied on a regex of FR phrases (`regardez`, `voilà`, `cette grille`…), so on EN transcripts the counter silently stayed at 0 and Mode B (cross-induction) was never recommended. The pattern list is now bilingual EN+FR (extensible to other languages), restoring the recommendation logic for non-FR transcripts.

### Repo-level (post-merge, not in code)

These actions happen at release time outside the PR diff but are part of the v1.0.3 launch readiness:

- **Default branch** switched from `develop` to `main` (the v1.0.3 commit is the cutover point).
- **GitHub description** updated to *"Opinionated implementation of Karpathy's LLM Wiki pattern — maintained by domain-expert agents (Claude Code)."* (mentions Karpathy for post-thread discoverability).
- **GitHub topics** expanded to 8–10 covering `karpathy`, `llm-wiki`, `personal-knowledge-base`, `pkm`, `second-brain`, `claude-code`, `obsidian`, `agent-based`, `wiki-template`.
- **Seed issues** opened to signal a live project (Bootstrap support for non-Claude-Code agents; "before/after" walkthrough; share-your-instance discussion).

### Migration from v1.0.2

`/update-vault` propagates `BOOTSTRAP.md`, the templates, `.claude/rules/` and `.claude/commands/` automatically. **However**, two artifacts are user-owned and stay untouched by `/update-vault`:

- `CLAUDE.md` (your live one, derived from the template at bootstrap)
- `.claude/agents/<domain>-expert.md` (one per domain you declared)

To benefit from `{{vault_language}}` in an existing vault:

1. Edit your `CLAUDE.md` writing principles section. Replace the hardcoded language line (`Français.` or whatever was substituted at bootstrap) with: `Vault language: **<your language label>** — every wiki page is written in this language, regardless of the source's original language. Technical terms in VO when the VO usage is dominant.`
2. For each `<domain>-expert.md` in `.claude/agents/`, find the writing-language line ("Pages are in `kebab-case.md`, titles in <language>...") and replace with: `Pages are in `kebab-case.md`. Writing language: titles and bodies in the vault language declared in `CLAUDE.md`. The original source language has no incidence — quote sources verbatim, translate commentary into the vault language.`

A migration script `scripts/migrations/v1.0.3-vault-language.md` may be added in a follow-up patch if demand warrants automation.

## [v1.0.2] — 2026-05-01

### Added

- **`.claude/rules/`**: three transverse conventions formalized (frontmatter, pages-wiki, raw-vs-cache) with `paths:` frontmatter that lets Claude Code auto-load them when an agent works on a matching path. Pattern documented by Anthropic (Boris Cherny, 2026-03-24). Propagated by `/update-vault` to existing vaults.
- **`.claude/template-version`**: explicit template-version file (format `template-version: X.Y.Z` + `template-sha:` + `last-updated:`). Single source of truth for the `/update-vault` migration machine. Created at bootstrap (BOOTSTRAP 5.10), updated at every successful `/update-vault`.
- **`scripts/migrations/`**: new folder for breaking migrations between template versions. Pattern `v<X.Y.Z>-<description>.md` (interactive Claude Code slash-commands). First example: `v1.0.2-claude-md-slim.md`. Invoked by `/update-vault` in the chain between local and target version.
- **`/create-issue [bug|enhancement|docs|question]`** ([#4](https://github.com/tetra-plg/boiling-brain/issues/4)): new slash-command to file an issue against the upstream template repo from the current session context, with **automatic sanitization** of vault-specific data (wikilinks, domain slugs, private paths `raw/notes/<date>-*`, emails, wiki entity names). Mandatory user validation via `AskUserQuestion` before `gh issue create`. Rules formalized in `.claude/rules/sanitization-issues.md` (auto-loaded via `paths:`). Proactive workflow: when the radar contains an entry concerning the template environment, the main context proposes `/create-issue` to the user (no silent creation).
- **`scripts/test-scan-raw.sh`**: test fixture reproducing the 3 cases of the `scan-raw.sh` fix (apostrophe, parentheses, multiple spaces) + a combined case. Asserts that every case reports `SKIP` on scan. Exit code 1 on regression.

### Changed

- **`CLAUDE.md.tpl` reduced to 112 lines** (from 268, −58%), per the Anthropic recommendation "< 200 lines" to preserve instruction adherence. The verbose Workflows sections (~143 lines) are replaced by a compact table pointing to `.claude/commands/*.md`. The Conventions section (22 lines) becomes a pointer to `.claude/rules/`. Instance-specific sections (Domains, Expert agents, Architecture) stay unchanged.
- **`/update-vault` refactored as a versioned migration machine**: reads `.claude/template-version` (with backwards-compat fallback to `.template-bootstrap-sha` for v1.0.1 and to the `v1.0.0` tag for v1.0.0), compares with the upstream target version, propagates new files (including `.claude/rules/**` and `scripts/migrations/**`), runs the chain of applicable migrations, bumps `.claude/template-version` at the end if every migration was accepted.
- **`BOOTSTRAP.md` section 5.10**: enriches `.claude/template-version` with the SHA and the bootstrap date (in addition to the historical `.template-bootstrap-sha`, kept for backwards compat).

### Fixed

- **Convention propagation gap to existing vaults** ([#5](https://github.com/tetra-plg/boiling-brain/issues/5)): before v1.0.2, any convention evolution (frontmatter, `raw/` immutability, etc.) lived in `CLAUDE.md.tpl` consumed at bootstrap, with no propagation mechanism. Concrete case: 18 pages of the reference vault had `source_sha256` filled with a placeholder by expert agents (2026-04-29 batch) — not fixable without per-vault manual patch. With v1.0.2, the rule "`source_sha256` always via `shasum -a 256`" lives in `.claude/rules/frontmatter.md` and is propagated automatically by `/update-vault`.
- **`scripts/scan-raw.sh`: 3 parsing bugs causing false `NEW` entries** ([#3](https://github.com/tetra-plg/boiling-brain/issues/3)):
  - **Bug 1 (apostrophes eaten)**: `tr -d '"'"'` on lines 79, 106, 126 removed both YAML quotes and path apostrophes. Any `source_path` containing an apostrophe (e.g. `2026-01-30-claude-code-obsidian-cpr.md` mentioning `BotFather to 'Hello'`) was mis-indexed. Replaced by `sed 's/^"//; s/"$//'` which only touches leading/trailing quotes.
  - **Bug 2 (parentheses break bash assoc array keys)**: a `source_path` or `covered_paths` containing `()` or other shell special chars (`*`, `[`, `?`) broke indexing. Neutralized via a `_safe_key` function that encodes keys with `printf '%q'` on write **and** lookup, in `path_to_slug`, `dir_to_slug` and `meta_to_slug`. Eliminates the entire class of bash quoting bugs without external dependency.
  - **Bug 3 (multiple spaces)**: covered by the same `printf '%q'` — spaces are now preserved exactly.
  - Parallel array `indexed_paths` added to allow iterating on the original paths (the encoded keys of `path_to_slug` are not reversible).

### Removed

- **`RELEASE_NOTES.md`**: file removed. It duplicated `CHANGELOG.md` and the GitHub release body, which created drift at every release. The single source for release notes is now `CHANGELOG.md`. The GitHub body is written directly via `gh release create --notes-file <(extract from CHANGELOG)` or edited in the UI.

### Migration from v1.0.x

Migration to v1.0.2 is **handled by `/update-vault`**:

```bash
# In your bootstrapped vault:
/update-vault
```

`/update-vault` automatically detects the local version (via `.claude/template-version`, or via backwards-compat fallback on `.template-bootstrap-sha` for v1.0.1, or tag `v1.0.0` for v1.0.0), propagates the new files (`.claude/rules/`, `scripts/migrations/`, `.claude/template-version`), then invokes the `v1.0.2-claude-md-slim` migration which:

1. Reads the current `CLAUDE.md`.
2. Identifies sections to compact (duplicated detailed Workflows, verbose Conventions).
3. **Preserves user customizations** (sections added outside the template).
4. Proposes a diff via `AskUserQuestion` (3 options: apply / edit manually / skip).
5. If applied: dedicated commit `chore: migrate CLAUDE.md to v1.0.2 slim structure`.

`CLAUDE.md` is never silently rewritten — it's user-owned.

If you prefer to migrate manually, read [scripts/migrations/v1.0.2-claude-md-slim.md](scripts/migrations/v1.0.2-claude-md-slim.md) which describes exactly what to change.

## [v1.0.1] — hotfix

### Fixed

- **`/update-vault` unusable after bootstrap**: bootstrap resets the git history (`rm -rf .git/ && git init`), leaving the vault with no common ancestor with the template. `git log HEAD..template-upstream/main` then returned the entire template history, and `git cherry-pick` failed on `.tpl` files consumed at bootstrap.

- **`BOOTSTRAP.md` section 5.10**: now records the template SHA into `.template-bootstrap-sha` before deleting the `.git/`. This file serves as the baseline for future updates via `/update-vault`.

- **`/update-vault`**: replaces `cherry-pick` with a per-file approach (`git show template-upstream/main:<file> > <file>`), independent of git history. Automatically excludes files consumed at bootstrap (`*.tpl`, `BOOTSTRAP.md`, `PLACEHOLDERS.md`, etc.).

### Changed

- **`BOOTSTRAP.md` language-adaptive**: bootstrap is no longer hardcoded to French. Automatic language detection via the user's first messages, generation of every file (`CLAUDE.md`, `wiki/index.md`, `wiki/log.md`, agents, hubs…) in the detected language.

### Removed

- **`wiki/decisions/tiered-loading-wiki.md`**: the decision was replaced by direct implementation in `query.md` and the `summary_l0` / `summary_l1` frontmatter. The decision no longer needed to exist as a separate document.

### Documentation

- **README — Prerequisites section**: Claude Code, Obsidian (with link to graph view), gh CLI listed explicitly.
- **README — Web Clipper FAQ**: Obsidian Web Clipper → `raw/clippings/` → `/ingest` workflow documented.
- **README — usage guidelines**: clarifications on how the repo is meant to be used (template, not a project to clone).

### Migration from v1.0.0

**Option A — automatic (recommended):**

```bash
git remote add template-upstream https://github.com/tetra-plg/boiling-brain.git 2>/dev/null; true
git fetch template-upstream --tags
git show template-upstream/main:.claude/commands/update-vault.md \
  > .claude/commands/update-vault.md
git add .claude/commands/update-vault.md
git commit -m "fix: update-vault retrocompat v1.0.0"
```

Then run `/update-vault` — the fallback detects the absence of `.template-bootstrap-sha` and uses the `v1.0.0` tag as baseline automatically.

**Option B — manual:**

```bash
git fetch template-upstream --tags
git rev-list -n 1 v1.0.0 > .template-bootstrap-sha
git add .template-bootstrap-sha
git commit -m "fix: add template bootstrap sha (retrocompat v1.0.0)"
```

## [v1.0.0] — 2026-04-30 (first public release)

### Repository

- Renamed from `tetra-plg/llm-wiki-template` to `tetra-plg/boiling-brain` and made public.
- All references in `BOOTSTRAP.md`, `README.md`, `CONTRIBUTING.md`, and `/update-vault` updated.
- All examples in `BOOTSTRAP.md` anonymized (Maria Dupont / Carlos Silva / Acme Corp / `data-science, ml-ops, devops, leadership, ecriture`).

### Added

- README section "How does this differ from Karpathy's LLM Wiki?" — comparative table covering source-of-truth, agent topology, idempotence, multimodal, queries, external code, self-improvement, decisions.
- `RELEASE_NOTES.md` — body for `gh release create` plus maintainer instructions.

### Bundled from prior phases (now first-shipped publicly)

Everything from the v0.2.0 phase below is part of v1.0.0. Listed for clarity.

## [v0.2.0] — 2026-04-30 (Phase 5c — real feedback, internal)

### Added

- `raw/` directory structure pre-created via `.gitkeep` files (`raw/notes/`, `raw/transcripts/`, `raw/videos-meta/`, `raw/frames/`). Visible immediately after clone.
- `BOOTSTRAP.md` Section 5.8 creates conditional `raw/` subdirectories (`pdfs/`, `articles/`, `docs/`) based on Q5 source types, plus the matching `cache/` substructure.
- `BOOTSTRAP.md` Section 4.1 — color picker per domain (4 preset colors with pre-computed RGB values). Section 5.9 generates `.obsidian/graph.json` with the standard filter (`-path:"raw" path:"wiki"`) and `colorGroups` per domain, plus a minimal `.obsidian/app.json`.
- `/update-vault` slash-command — configures `template-upstream` remote, lists available commits, lets the user cherry-pick selectively. Documented in README.
- Exception `!raw/**/.gitkeep` in `.gitignore` so the structure ships with the template while user vaults still ignore `raw/` content.

### Changed

- Q4 (current projects) format replaced. The pipe-separated `slug | description` is gone — users now write natural prose, the LLM extracts the slug automatically.
- README.md — added `/update-vault` to the slash-commands table.

## [v0.1.0] — 2026-04-30 (Phase 4 — initial template)

### Added

- Initial scaffolding for the LLM Wiki bootstrap template.
- `BOOTSTRAP.md` portable prompt (~600 lines, language-adaptive) — 7-question interview, 6-heuristic deduction, per-domain validation, scaffolding, optional GitHub remote, onboarding recap.
- `*.tpl` files with 28 documented placeholders (see `PLACEHOLDERS.md`): `CLAUDE.md.tpl`, `wiki/index.md.tpl`, `wiki/log.md.tpl`, `wiki/overview.md.tpl`, `wiki/radar.md.tpl`, `wiki/domains/domain.md.tpl`, `.claude/agents/domain-expert.md.tpl`, `.claude/agent-memory/domain-memory.md.tpl`, `tracked-repos.config.json.tpl`.
- Generic slash-commands: `/ingest`, `/ingest-video`, `/query`, `/save`, `/lint`, `/evolve-agent`, optional `/sync-repos`.
- Generic scripts: `scan-raw.sh`, `transcribe.sh`, `sample-frames.sh`, `extract-frames.sh`, `diff-frames.py`, `backfill-summaries.py`, `enrich-hub.py`, optional `sync-repos.sh`.
- Architectural decisions in `wiki/decisions/`: `tracked-repos-immutable-snapshots.md`, `extraction-frames-induction-runbook.md`, `ingest-video-modes-a-b-generalisation.md`.
- README.md with usage flow + FAQ.
- MIT LICENSE.
