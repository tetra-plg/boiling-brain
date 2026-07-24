# Changelog

All notable changes to this template are documented here. Format inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Versions are milestones, not strict semver. Breaking changes to `BOOTSTRAP.md` or `*.tpl` are flagged in the release notes.

---

## [v1.2.1] — unreleased

### Changed

- **MCP documentation synced to the 14-tool surface**: `list_domains()` and `ingest()` (both shipped in v1.1.1, #62) were missing from the user-facing docs, which still described "12 tools". `README.md` and `docs/mcp-tiered-loading.md` now list all 14 tools and start the recommended tiered pattern with `list_domains` (domains evolve via `/domain`, so slugs are never guessed). `scripts/mcp/setup-mcp.sh` now injects a `list_domains`-first `CLAUDE.md` block and recognises the older 12-tool block (without `list_domains`) as outdated, replacing it in place. Documentation/setup only — no runtime tool change. (#91)

### Fixed

- **`.prettierignore` + `scripts/wiki-maint/format-md.py`**: a bare Prettier run on `wiki/` (`npx prettier --write`, or an editor "format on save") reflowed GFM tables and silently destroyed the pipes inside `[[wikilink|alias]]` and code spans. The Obsidian-safe wrapper masks those pipes, but nothing forced callers through it. `wiki/` is now in `.prettierignore` so bare Prettier skips it; the wrapper opts out of that ignore via `--ignore-path` (an empty file) to keep formatting `wiki/` in both `--write` and `--check`, and `do_check` no longer copies `.prettierignore` into its temp tree — which would otherwise make `--check` skip the `wiki/` copies and report unformatted pages as clean (silent false negatives). `.claude/rules/pages-wiki.md` documents the hazard and the escaped-pipe (`\|`) alternative. (#89)

## [v1.2.0] — 2026-07-19

### Added

- **Read-side delegation to domain experts (`#79`)**: selective, opt-in delegation of the read-side workflows to the per-domain experts (system prompt + `agent-memory/<domain>/` + Domain orientation, #71). New `.claude/commands/radar.md` (`/radar`) shows the radar and delegates per-domain triage above a threshold (≥ 3 open entries with an expert, or explicit `/radar <domain>`), partition → aggregate. `.claude/commands/lint.md` now splits an explicit deterministic **structural pass** (orphans, missing raw sources, broken wikilinks, `revisit_after` — main/script) from a **semantic pass** delegable per domain (contradictions, stale claims, missing concepts/cross-refs, data gaps). `.claude/commands/query.md` documents a selective rule: delegate only a mono-domain judgment/memory question; fact retrieval and cross-domain stay in the main context. Return contracts formalised in `.claude/agent-output-contract.md` (`## Triage recommendations` / `## Semantic findings` / `## Query answer`, read-only on `wiki/`) and in the expert prompt (`.claude/agents/domain-expert.md.tpl`). Existing vaults get the agent + `CLAUDE.md` changes via `scripts/migrations/v1.2.0.md` (Part E); the command files reach them by file propagation. (#79)
- **`scripts/mcp/wiki-cli.sh`**: portable wrapper over `wiki-cli.py` (resolves `python3`/`python` like `scan-raw.sh`, Windows-safe against the Microsoft Store `python3` stub). The single invocation string `bash scripts/mcp/wiki-cli.sh <cmd>` is shared by the agent template, `/ingest`, the allowlist, and the headless guard.
- **`.claude/agents/domain-expert.md.tpl`**: new **Domain orientation** section — each expert self-orients in its domain via the tiered-loading CLI (`scan-domain → drill-down → preview/read`) instead of depending on a main-injected page-title list, with a `Glob`/`Grep` fallback. Idempotence step 0, cross-refs, and `[[wikilink]]` checks now resolve through the CLI rather than guessing.
- **`scripts/migrations/v1.2.0.md`**: single interactive, idempotent `/update-vault` migration for v1.2.0 — Part B inserts the Domain orientation section into existing `<domain>-expert.md` agents and adds the `wiki-cli.sh` allowlist rule to the vault's `.claude/settings.json`; Part A coordinates the scan-raw rewrite propagation and runs a health check (see Fixed).
- **`scripts/wiki-maint/scan-raw.py`**: new flags on the detection engine — `--format=json` (machine contract: `files`/`orphans`/`warnings`/`pending`/`counts`, versioned), `--force` (deterministic SKIP→MODIFIED, `reason: forced`), `--orphans` (list source pages whose raw vanished), `--pending` (read-only oracle over `cache/.pending-ingest`, surfaces `purgeable`/`stale` buckets for the purge step). Index lint on stderr (`duplicate-claim`, `missing-sha`) plus a `N new · M modified · K skipped` summary. Canonical `source_sha256_composite` formula (documented in `.claude/rules/frontmatter.md`) with `composite-mismatch` detection (WARN only this pass — no MODIFIED verdict). `/ingest` step 1 now consumes the JSON contract, delegates `--force` to the script, drives phase-4c purge from `--pending`, and fills the phase-5 orphans list from `--orphans`; the headless guard allowlists the new flags. (#70)
- **`scripts/wiki-maint/archive-radar.py`** + **`/lint` final step**: the lint workflow now auto-archives the radar. Every `- [x]` (handled) entry in `wiki/radar.md` is moved to `wiki/radar-archive.md` under its original thematic section (created if absent; generic `## Handled` fallback for section-less entries), preserving each entry's resolution text verbatim. The archive file is created on first use with a valid frontmatter; both files get their `updated:` date bumped; the lint report states how many entries were archived. Idempotent (no `[x]` → no writes), covered by `scripts/wiki-maint/test_archive_radar.py`. Retires the manual radar-cleanup chore. Existing vaults get a non-blocking heads-up via `scripts/migrations/v1.2.0.md` (Part D). (#80)

### Changed

- **`.claude/commands/ingest.md`**: the spawn prompt injects a fresh `scan-domain` snapshot (counts + centrality + summaries) per spawn instead of a flat page-title list; the main context no longer builds that list.
- **`scripts/mcp/ingest-headless-guard.sh`**: allowlists the charset-safe `wiki-cli.sh` subset (`scan-domain`, `scan-<type>` without `--query`, `list-domains`, `preview`, `read`) so headless ingest also gets the snapshot; `--query`/`search` stay denied (fall back to `Glob`/`Grep`). Guard tests extended (+10 allow/deny cases).

### Fixed

- **`scripts/wiki-maint/scan-raw.sh` → `scan-raw.py`**: rewrote the state-detection engine in Python (single process) — the old bash spawned one `python3` per indexed path plus a `grep|sed` pipeline per frontmatter line, so on a mature vault (several hundred source pages, several thousand raw files) even a single-file scan blew past the 120s timeout and `/ingest` step 1 was unusable. `scan-raw.sh` is now a thin wrapper that keeps the portable `PYTHON_BIN` resolution (#61) and execs `scan-raw.py`. Default stdout is byte-for-byte identical (golden-tested against the pre-rewrite bash); stderr messages moved to English (template EN policy). One deliberate default-verdict change: `source_path`/`covered_paths` motifs are now recognised only inside the leading `---` frontmatter block, killing phantom `SKIP`s from body text. Existing vaults upgrade via `scripts/migrations/v1.2.0.md` (Part A). (#70)
- **`scripts/mcp/setup-mcp.sh`**: forced UTF-8 on the script's Python subprocess stdio (`export PYTHONIOENCODING=utf-8`), fixing a hard `UnicodeEncodeError` crash on Windows consoles (cp1252, `PYTHONUTF8` unset) when the `python -c` / heredoc blocks print status emoji (`✅`, U+2705). Same root cause as #60 (`format-md.py`), extended here to `setup-mcp.sh`. The crash aborted the force-rerun `v1.1.0` migration invoked by `/update-vault` on Windows vaults; macOS/Linux are unaffected (emoji still render). (#69)
- **`scripts/wiki-maint/validate-wiki.py`**: closed two silent blind spots surfaced by a `/lint` full-sweep. (1) A `[[raw/…]]` wikilink is now flagged as a convention violation (the wiki must never link into `raw/`) instead of being unconditionally skipped — an autocomplete scoria could previously pass CI as a dead link. (2) Frontmatter is now validated with `yaml.safe_load`, catching syntactically invalid YAML that the hand-rolled line parser accepted while the real consumers (MCP `wiki_core`, indexing) silently dropped the page's `type`/summaries (a central page becoming invisible to tiered loading, with no error). PyYAML is optional — the syntax check is skipped with a stderr note when absent (like the consumers); the CI `wiki-integrity` job installs it so the check runs there. Existing vaults get a non-blocking heads-up + health check via `scripts/migrations/v1.2.0.md` (Part C). (#77)
- **`scripts/mcp/mcp-wiki.py`**: the MCP `ingest()` tool now resolves the `claude` CLI with `shutil.which` before spawning it, instead of passing the bare name `"claude"` to `subprocess.run(shell=False)`. On Windows the CLI ships as a `claude.CMD` shim and `CreateProcess` does not consult `PATHEXT`, so a bare `"claude"` raised `FileNotFoundError` (reported as "CLI `claude` introuvable") even when it was on `PATH` — every MCP-triggered ingest failed. `shutil.which` honours `PATHEXT` (and is correct on POSIX); `shell=False` is preserved, so no command-injection surface is reintroduced. Same Windows subprocess-resolution family as #60/#61. (#84)

## [v1.1.1] — 2026-07-03

### Added

- **`scripts/mcp/wiki-cli.py`**: headless CLI front over the wiki, for scriptable / containerised consumers without an MCP client. Exposes the 12 read tools as subcommands (`list-domains`, `scan-domain`, `scan-concepts`, `scan-entities`, `scan-decisions`, `scan-syntheses`, `scan-cheatsheets`, `scan-diagrams`, `scan-sources`, `preview`, `read`, `search`). Markdown by default; `--json` emits a stable, machine-readable shape (the `path` fields are vault-relative and reinjectable into `preview` / `read`). Exit code `0` on success or a legitimate empty result, `2` (message on stderr) on a lookup error (page not found, empty domain, path traversal, `scan-sources` without a query). Targets a vault via `WIKI_PATH` or `--wiki-path`. No `fastmcp` dependency. (#57, #62)
- **`scripts/mcp/wiki_core.py`**: dependency-free query layer shared by the MCP server and the CLI. Each read tool is split into `<tool>_data()` (structured, JSON-able — the source of truth) and `<tool>_md()` (human-readable markdown). PyYAML stays optional (frontmatter features degrade gracefully when it is absent). (#57)
- **`scripts/mcp/test_wiki_core.py` + `scripts/mcp/test_wiki_cli.py`**: `unittest` suites covering MCP↔core parity (fastmcp-gated, self-skips without fastmcp), CLI↔core markdown parity, exit codes, and JSON shape. (#57)
- **`docs/mcp-tiered-loading.md`**: new "CLI mode (no MCP client)" section documenting the headless entry point, the subcommand surface, and the JSON contract. (#57)
- **`scripts/mcp/mcp-wiki.py`** / **`scripts/mcp/wiki_core.py`**: two new MCP tools closing the "drop → ingest" loop for third-party callers. `list_domains()` lists declared domain slugs, their summary, and whether each has a matching `.claude/agents/<slug>-expert.md`, so a caller can validate a `domain_hint` instead of hardcoding slugs — exposed both by the MCP server and by the `wiki-cli.py` CLI (`list-domains` subcommand, for read-tool parity). `ingest(path, domain_hint="")` triggers headless ingestion of an already-dropped `raw/` file by spawning `claude -p "/ingest --headless"`, blocking until completion; domain-expert resolution is deterministic (valid hint → single high-confidence candidate → otherwise deferred to `needs-human-triage`, never guessed). Unattended writes (`wiki/log.md`, `wiki/radar.md`, `wiki/index.md`, final format step) require an explicit, durable opt-in (`MCP_INGEST_PERMISSION_MODE`, e.g. `auto`) instead of a silent permission escalation. (#62)
- **`scripts/mcp/ingest-headless-guard.sh`**: `PreToolUse` hook, scoped via `--settings` to the `claude -p` session spawned by `ingest()` (confirmed to apply to the main context and any spawned subagent, and to merge with — not replace — the vault's own persistent hooks). Allowlists exactly the Write/Bash operations the headless `/ingest` workflow performs and default-denies everything else, including tools uncovered by the base ruleset (`NotebookEdit`/`WebFetch`/`WebSearch`). Bash allowlisting anchors each allowed command to a safe charset rather than denylisting metacharacters — closing, across 6 rounds of adversarial review, command chaining, process substitution (`<(...)`/`>(...)`), path traversal via `..`, redirection, and an unanchored `scan-raw.sh` invocation. An optional vault-local `.claude/ingest-bash-allowlist.local.txt` extends the Bash allowlist with custom prefixes. (#62)
- **`scripts/wiki-maint/purge-pending-ingest.sh`**: extracted from `/ingest` step 4c's inline snippet into its own script, so it can be allowlisted by the guard above via a single fixed command prefix instead of an unsafe-to-match inline heredoc. (#62)
- **`scripts/mcp/test_wiki_core.py`**: extended with coverage for `list_domains()`, `ingest()` (happy path, deferral, path/domain_hint validation, subprocess failure modes), and 33 dedicated tests for `ingest-headless-guard.sh` covering every bypass found in adversarial review. (#62)

### Changed

- **`scripts/mcp/mcp-wiki.py`**: refactored (550 → 153 lines) into a thin FastMCP wrapper that delegates to `wiki_core`. **No behaviour change** — the 12 tool descriptions and signatures are byte-identical (MCP schema unchanged) and every tool's markdown output is byte-identical to v1.1.0 (guaranteed by the parity tests and the `smoke_test.py` token gates). (#57)
- **`.github/workflows/lint.yml`**: bumped the CI actions off the deprecated Node 20 runtime to Node 24 — `actions/checkout@v4 → @v6`, `actions/setup-python@v5 → @v6`, `DavidAnson/markdownlint-cli2-action@v16 → @v23` (bundles markdownlint-cli2 0.22.x; verified to introduce no new rule failures on this repo). Job logic unchanged. The workflow is template-tracked, so the fix reaches vaults via `/update-vault` file propagation — no migration needed. (#56)
- **`/ingest`**: new `--headless` and `--domain-hint=<slug>` flags (set automatically by `ingest()`, not intended for manual interactive use) — non-interactive mode for a single-file run. Replaces every `AskUserQuestion` point with a deterministic rule (see the tool bullet above), annotates undated frame requests instead of asking for extraction, and always ends the report with a machine-parseable `## Pages` block (`- <path> (<type>, new|updated)` per line, empty if deferred) so an external consumer can trace which pages a source fed. (#62)

### Fixed

- **`scripts/wiki-maint/format-md.py`**: fixed a crash on Windows where `subprocess.run(["npx", ...], shell=False)` failed to resolve `npx.cmd`/`.ps1` via `PATHEXT` (`FileNotFoundError: [WinError 2]`), and a follow-up `UnicodeEncodeError` on the Windows console (cp1252) once npx was reachable. `npx` is now resolved via `shutil.which()` (raises a clear error if missing); `stdout`/`stderr` are forced to UTF-8 at startup. (#60)
- **`scripts/wiki-maint/scan-raw.sh`**: fixed silently degraded ingest-state detection on Windows, where the bare `python3` invocation in `_normalize_path()` could resolve to the non-functional Windows Store stub — and, since it's nested inside a command substitution, its failure was swallowed by `set -e`, producing false `covered-by` verdicts. The Python interpreter is now resolved once at startup (`PYTHON_BIN` env override, then `python3`, then `python`) and functionally self-tested; if none works, the script now fails loudly before scanning instead of degrading silently. (#61)

## [v1.1.0] — 2026-05-25

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

### Added (CI revamp for living vaults)

- **CI recalibrated for content vaults** — `.github/workflows/lint.yml` no longer blocks on inevitable noise. Three blocking jobs on push/PR: `format-check` (Prettier `--check`), `markdownlint` (semantic rules only), and `wiki-integrity` (new); plus a weekly **non-blocking** `link-check-report` for external links (lychee, `fail: false`) instead of failing every push on dead third-party URLs. Rationale: the remote vault is a read-only artifact (`raw/` and the LLM are local-only), so CI does deterministic validation only — it blocks on what is repairable and meaningful, never on inevitable noise (rotting web links, cosmetic style of generated content).
- **Prettier as the markdown formatter** — new `.prettierrc` (`proseWrap: preserve`) and `.prettierignore` (excludes `raw/`, `node_modules/`, `.claude/worktrees/`). Markdown is clean and consistent by construction. `.markdownlint.jsonc` recalibrated to **semantic rules only** (MD056 table-column-count, MD042 empty-links, MD051 link-fragments, MD024) and disables the cosmetic rules now owned by Prettier — including **MD060** pre-emptively (invisible on the action's markdownlint v0.34 but explodes on upgrade).
- **`scripts/wiki-maint/validate-wiki.py`** (+ `test_validate_wiki.py`, 18 stdlib `unittest` tests) — deterministic integrity checker for broken `[[wikilinks]]`, broken internal relative links/anchors, and per-type frontmatter conformance (required fields present, `domains` non-empty, `summary_l0` ≤140 mono-line, `summary_l1` present — both required for tiered loading). Vocabulary is **open** (no closed `type`/`status` list — judging vocabulary is the semantic `/lint`'s job). Skips `raw/` targets (local-only) and understands Obsidian table-alias escapes (`[[target\|alias]]`).
- **`/format`** — new command running `prettier --write` on demand and for the one-shot normalisation of a pre-formatter vault.
- **Generation commands format their output** — `/ingest`, `/save`, `/evolve-agent`, `/compress-bb` run `prettier --write` on the markdown they produce, keeping the CI `format-check` job green.
- **`/lint`** — now also verifies that the `raw/` source files cited in each page's `sources:` exist on disk (the local counterpart of the CI, which cannot see `raw/`).

### Fixed (alpha feedback)

- **`BOOTSTRAP.md` — silent language miscapture for multilingual users** ([#53](https://github.com/tetra-plg/boiling-brain/issues/53)): language detection relied on two doubt-gated guardrails ("If unsure…", "Confirm… if you have any doubt"), so a confident-but-wrong inference (e.g. a French user writing their first messages in clean English) captured `{{vault_language}} = English` silently and propagated it to `CLAUDE.md` and every domain agent. Fix: a new unconditional `Q0 — Vault language` step (`AskUserQuestion`, inference seeds the default, user choice is authoritative); the two directives are de-gated; the language is re-displayed in the Final recap before scaffolding.
- **`/compress-bb`**: document "When NOT to use" to avoid redundancy with substantive `raw/notes/` (#22).
- **`scripts/wiki-maint/scan-raw.sh`**: avoid silent kill under `set -euo pipefail` when `source_sha256` absent on composite pages (#23).
- **`/update-vault`**: track applied migrations individually via `applied-migrations:` field in `.claude/template-version` — fixes silent skip of migrations added retroactively (after a version bump). Vaults pre-v1.1.0 auto-populate the field at first run post-upgrade. (#31)
- **`scripts/mcp/setup-mcp.sh`**: quote heredoc delimiter and pass shell vars via `os.environ` — vault paths containing `"` or `\` no longer corrupt the Python hook registration silently (review finding A).
- **`scripts/mcp/setup-mcp.sh`**: surface pipx install errors instead of swallowing stderr — real cause visible when fastmcp installation fails (review finding C).
- **`scripts/mcp/mcp-wiki.py`**: `scan_domain` now accepts an optional `limit` parameter (default `0` = no limit) and surfaces capping in the output (`X / Y pages`) — large domains no longer lose pages silently (#36, review finding D).
- **`scripts/mcp/setup-mcp.sh`**: export `CLAUDE_MD` to the inline python3 subshell that replaces the outdated `~/.claude/CLAUDE.md` block — fixes `KeyError: 'CLAUDE_MD'` that silently swallowed the self-healing on pre-#47 vaults attempting to refresh their block (the script reported `✅ Hook Stop déjà enregistré.` then crashed; the migration was marked applied while the block stayed outdated). Reported by user E2E test on a real vault.
- **`scripts/wiki-maint/scan-raw.sh` — false `MODIFIED` on quoted `source_sha256`** ([#39](https://github.com/tetra-plg/boiling-brain/issues/39) part 1): the parsing sed stripped `source_sha256:` prefix but left the surrounding double quotes (convention is `source_sha256: "<hex>"`), then compared the quoted string to the unquoted `sha256sum` output. Every page following the quoted-sha convention was falsely reported `MODIFIED` on every `/ingest` sweep (~51 false reports measured on a reference vault). Fix: sed now also strips leading/trailing quotes (same pattern as `source_path`).
- **`scripts/wiki-maint/scan-raw.sh` — false `NEW` on Unicode-apostrophe paths** ([#39](https://github.com/tetra-plg/boiling-brain/issues/39) part 2): a raw file with `'` (U+2019) in its name and a wiki page with `source_path: "...'..."` (U+0027, silently normalised by the ingesting agent) failed the byte-exact match → file reported `NEW` instead of `SKIP`, risk of duplicate source page. Fix: new `_normalize_path()` helper (NFC + fold U+2019 → U+0027) applied symmetrically at all 10 `_safe_key` callsites involving a path.
- **`scripts/wiki-maint/scan-raw.sh` — `VAULT_ROOT` regression after script move**: when the script moved from `scripts/scan-raw.sh` to `scripts/wiki-maint/scan-raw.sh` (Phase 1 of v1.1.0), `VAULT_ROOT="$(dirname "$SCRIPT_DIR")"` started resolving to `scripts/` instead of the vault root, breaking every path lookup. Fix: `dirname` adjusted (one extra level) to compensate for the deeper script location.
- **`.claude/rules/frontmatter.md` — `source_path` round-trip rule**: explicit rule that `source_path` MUST round-trip byte-for-byte to the on-disk filename — agents must NOT normalise typographic characters (apostrophes, quotes, dashes) when emitting `source_path`. Pairs with the Unicode-apostrophe fix above: `scan-raw.sh` does the normalisation symmetrically at match time, but the rule prevents the upstream cause from recurring.
- **`/compress-bb` — blocked by `protect-raw.sh`** ([#40](https://github.com/tetra-plg/boiling-brain/issues/40)): `/compress-bb` tried to write the session journal directly into `raw/notes/sessions/` via the `Write` tool, denied by the default `protect-raw.sh` `PreToolUse:Write|Edit` hook. The command was non-functional on the default template configuration. Fix: rewrite step 3 of `/compress-bb` to call the MCP `drop_to_raw(subfolder, filename, content)` tool — the file is written server-side (the hook doesn't fire because it's not an agent `Write`), and `cache/.pending-ingest` is auto-updated. Documented manual-paste fallback for sessions without the MCP server connected. The hook remains strict (no allowlist hole).
- **`scripts/mcp/mcp-wiki.py` — `search_wiki` token budget**: post-#47 smoke test revealed `search_wiki` returned ~2600 tokens (cap 800) with `limit=20` + `wikilinks=10`. Defaults lowered to `limit=10` + `wikilinks=3` (per result), bringing the gate to ~670 tokens. 10 results × 3 wikilinks per result remain sufficient for typical natural-language queries; the centrality ranking keeps the most-pertinent pages at the top.
- **`scripts/video/transcribe.sh` + `scripts/wiki-maint/scan-domain-refs.sh` — `VAULT_ROOT` one level too shallow** ([#51](https://github.com/tetra-plg/boiling-brain/issues/51)): same class of regression as the `scan-raw.sh` fix in #45. After the `scripts/` reorg moved these scripts one directory deeper (`scripts/<feature>/<script>`), the `$(dirname "$0")/..` computation resolved to `scripts/` instead of the vault root, breaking every relative path (cache/, raw/, wiki/) and creating stray `scripts/cache/`, `scripts/raw/` dirs. Fix: `dirname/..` → `dirname/../..` (one extra level).
- **`scripts/wiki-maint/backfill-summaries.py` + `scripts/wiki-maint/enrich-hub.py` + `scripts/mcp/mcp-wiki.py` — Python `Path(__file__).parent.parent` one level too shallow**: same class of regression as #51 but on the Python scripts. `Path(__file__).resolve().parent.parent` from `scripts/wiki-maint/<script>.py` resolves to `scripts/` instead of the vault root, so `ROOT/cache` and `ROOT/wiki` accesses fail. For `mcp-wiki.py`, the env-var `WIKI_PATH` set by `setup-mcp.sh` masked the buggy fallback at runtime, but the fallback would crash if anyone ran the server without env. Fix: `.parent.parent` → `.parent.parent.parent`. Discovered during the full audit triggered by #51 — the issue mentioned video siblings only, but the audit also caught the Python ones.
- **`scripts/mcp/setup-mcp.sh` — `VAULT_PATH` default one level too shallow**: same `dirname/..` bug class as #51 on the `VAULT_PATH` fallback when the script is invoked without `--vault-path`. Post-#42 the script lives in `scripts/mcp/`, so the default needs `cd "$SCRIPT_DIR/../.."` (was `dirname "$SCRIPT_DIR"` = `scripts/`). Masked in normal usage because the migration v1.1.0.md and the documented re-run command both pass `--vault-path` explicitly, but bare `bash setup-mcp.sh` would have configured the wrong path.
- **`scripts/mcp/mcp-wiki.py` — module docstring + tool descriptions cleanup** (deep-audit pre-tag): the module docstring still listed 5 tools (pre-#47) instead of the 12 organised by tier; the `search_wiki` description claimed "up to 10 outgoing wikilinks" while the code uses `limit=3` (lowered when search_wiki defaults were tightened); the `scan_domain` description hard-coded the BoilingBrain domain slugs in a template that is meant to be domain-agnostic ("e.g. one of the slugs listed in `wiki/domains/`" now). Dead module-level constants (`MAX_OUTPUT_TOKENS_APPROX`, `_TYPES_FOR_SCAN_TOOLS`) removed.

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
- **Breaking — template-owned ADRs moved from `wiki/decisions/` to `docs/`**: the 3 ADRs documenting template-internal decisions (`extraction-frames-induction-runbook`, `tracked-repos-immutable-snapshots`, `ingest-video-modes-a-b-generalisation`) leave `wiki/` (now reserved for user-owned ADRs — each vault enriches `wiki/decisions/` with its own decisions). `wiki/decisions/decision.md.tpl` (the ADR template for the user) stays. Migration v1.1.0 Part C removes the 3 stale files from existing vaults' `wiki/decisions/` (the `docs/` versions are propagated by `/update-vault` step 5). Refs from propagated files (`.claude/agents/`, `wiki/domains/`, `.claude/commands/`, `.claude/rules/`, `scripts/`) now point to the GitHub URL of the template upstream. `docs/` format unified: H1 + `> **TL;DR:**` blockquote, no YAML frontmatter (wiki-style frontmatter had no use outside the indexer).
- **Migration v1.1.0 Part D — patch stale references in user-owned files**: `/update-vault` step 5 only propagates tracked-by-template files. User-owned files (`.claude/agents/<domain>-expert.md`, `.claude/agent-memory/*.md`, `.claude/settings.json`, `.claude/settings.local.json`, the vault's `CLAUDE.md`) accumulate hard-coded references (e.g. `bash scripts/scan-raw.sh ...` in an agent's runbook, `Bash(scripts/transcribe.sh)` in the permissions allowlist, `[[decisions/extraction-frames-induction-runbook]]` in an agent's Visual frames section). After Parts A/B/C, those references stay stale because Part B's `git rm` only removes the old script files, not the references pointing at them. Part D adds an in-place rewrite of the 11 script paths + 3 wikilink ADRs in user-owned files, with diff-preview + `AskUserQuestion` before commit. Idempotent (negative lookbehind blocks double-substitution). Discovered via real-vault E2E test that surfaced ~40 dead links across 10 user-owned files in a heavily-customised vault.

### Migration from v1.0.x

Migration to v1.1.0 is **handled by `/update-vault`**:

```bash
# In your bootstrapped vault:
/update-vault
```

`/update-vault` detects the local version (1.0.x) → target 1.1.0, **3-way merges** the propagated files into the vault (local edits on tracked-by-template files are preserved when they don't collide with template changes — see "3-way merge on file propagation" above), then invokes the `v1.1.0` migration which:

1. Announces the additions and what it will mutate (`~/.claude/settings.json`, `~/.claude/CLAUDE.md`, `<vault>/CLAUDE.md`).
2. Proposes 3 options via `AskUserQuestion`: **Enable** (full setup) / **Patch vault CLAUDE.md only** (skip global mutations) / **Skip**.
3. **Part A** (if **Enable**): runs `bash scripts/mcp/setup-mcp.sh --vault-path <vault>` (idempotent + self-healing: installs `fastmcp` via pipx, resolves the right Python interpreter for PEP 668 systems, registers MCP via `claude mcp add -s user`, adds the Stop hook, writes/refreshes the 12-tool LLM instructions block in `~/.claude/CLAUDE.md`). Patches the vault's `CLAUDE.md` to insert the `## Session start` section.
4. **Part B**: detects and removes the pre-v1.1.0 flat-layout scripts (`scripts/extract-frames.sh`, `scripts/scan-raw.sh`, etc.) — they live under `scripts/{video,wiki-maint,mcp,hooks}/` now (propagated by step 5). Cleans the stale Stop hook entry pointing at the old `scripts/check-session-activity.sh` path before `setup-mcp.sh` re-registers the new one.
5. **Part C** (v1.1.0 final): removes the 3 template-owned ADRs (`extraction-frames-induction-runbook`, `tracked-repos-immutable-snapshots`, `ingest-video-modes-a-b-generalisation`) from `wiki/decisions/` — they live in `docs/` now (propagated by step 5). `wiki/decisions/` is reserved for the user's own ADRs going forward.
6. **Part D** (v1.1.0 final): patches stale references in user-owned files (`.claude/agents/`, `.claude/agent-memory/`, `.claude/settings.json`, `.claude/settings.local.json`, `CLAUDE.md`) that hard-coded the pre-v1.1.0 script paths or wikilinked the moved ADRs. Idempotent rewrite (negative lookbehind), with diff preview + `AskUserQuestion` before commit.
7. Dedicated commits per part, then bumps `.claude/template-version` to 1.1.0 with the slug list in `applied-migrations`.

The migration is marked `force-rerun: true`: it re-evaluates at every `/update-vault` to catch content fixes shipped after the initial application (e.g. a vault migrated pre-#47 will refresh its `~/.claude/CLAUDE.md` block on the next update). All steps are idempotent — no-op when the target state is already reached.

Neither `~/.claude/settings.json`, `~/.claude/CLAUDE.md`, nor `<vault>/CLAUDE.md` is ever rewritten as a whole — only specific content blocks are added, merged or refreshed.

If you prefer to migrate manually, read [scripts/migrations/v1.1.0.md](scripts/migrations/v1.1.0.md) which describes exactly what to change.

**Post-update actions** (one-time, after `/update-vault` completes):

- **Restart Claude Code** to reload the MCP server subprocess with the updated `scripts/mcp/mcp-wiki.py` (otherwise `scan_domain` still runs with the previously loaded code).
- **Verify** with `/mcp` inside Claude Code — `boiling-brain-wiki` should appear as `Connected` and expose the 12 tools (5 originals + 7 new `scan_<type>`). See [docs/mcp-tiered-loading.md](docs/mcp-tiered-loading.md) for the recommended usage pattern.

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

- **Source language vs vault language decoupling.** Before this fix, `CLAUDE.md.tpl` had `Français` hardcoded in its writing principles, and `domain-expert.md.tpl` had "titres en français". Consequence: an EN user bootstrapped a vault and every page produced by `/ingest` came out in French regardless of the source. The new `{{vault_language}}` placeholder + the explicit directive (_"Source language has no incidence on output language; quote sources verbatim, write commentary in the vault language"_) close that loop.
- **`/ingest-video` visual-mention detection was FR-only.** The `visual_mentions` counter relied on a regex of FR phrases (`regardez`, `voilà`, `cette grille`…), so on EN transcripts the counter silently stayed at 0 and Mode B (cross-induction) was never recommended. The pattern list is now bilingual EN+FR (extensible to other languages), restoring the recommendation logic for non-FR transcripts.

### Repo-level (post-merge, not in code)

These actions happen at release time outside the PR diff but are part of the v1.0.3 launch readiness:

- **Default branch** switched from `develop` to `main` (the v1.0.3 commit is the cutover point).
- **GitHub description** updated to _"Opinionated implementation of Karpathy's LLM Wiki pattern — maintained by domain-expert agents (Claude Code)."_ (mentions Karpathy for post-thread discoverability).
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
