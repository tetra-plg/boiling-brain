# Bringing evolving docs into an immutable `raw/`

> **TL;DR:** we want to bring into the wiki the docs of GitHub repos that change with every merge, while keeping `raw/` immutable. Solution: `/sync-repos` creates immutable snapshots named by the short SHA of each repo's HEAD, driven by a `tracked-repos.config.json` manifest. Every merge produces a new snapshot without overwriting the previous ones; hash-based idempotence and version history remain usable. Reusable pattern for any repo whose docs evolve (frameworks, living specs, in-progress projects).

## The problem

The LLM Wiki rests on a strong Karpathy principle: **`raw/` is immutable**. One source = one hashed snapshot, never modified, referenced by `wiki/sources/` via `source_path` + `source_sha256`. The idempotence of `/ingest` depends on it, and the wiki layer is always derivable from `raw/`.

But we often want to make queryable content that is **alive**:

- Technical docs of components or frameworks we follow (release notes, README, docs/).
- Standards specs that evolve (MCP, Agent Skills, etc.).
- Project docs of repos under active development.

Each merge into `main` upstream = new doc version. Reproducing that in `raw/` by overwriting would break the founding principle.

## Discarded options

**Option A — `raw/` live, overwritten at every sync.**
Simple, but loses history and breaks immutability. Contradictions between versions become unusable — they vanish.

**Option B — Live docs outside `raw/` (e.g. `docs-live/`), only releases snapshotted into `raw/`.**
Two regimes coexist, increased complexity for `/ingest` and `/lint`. And above all: it opens a breach in the "nothing mutable in the vault" rule.

**Option C — Snapshot per sync keyed by date.**
`raw/tracked-repos/<repo>/2026-04-19/`. Creates a snapshot even if content is identical → noise. The natural unit isn't the date but the **event** (merge into main).

## Retained decision

**Snapshot by short SHA for everything**, via a single `/sync-repos` slash command driven by a manifest.

### Mechanics

1. Manifest [`tracked-repos.config.json`](../../tracked-repos.config.json) at the vault root — list of tracked repos, their `branch`, `paths` (doc files/folders to extract), `exclude_paths` (paths removed from the snapshot after copy), `dest` (target path — typically `raw/tracked-repos/<slug>`, but free).
2. `scripts/sync-repos.sh`: for each source, `gh api repos/<repo>/commits/<branch>` → HEAD SHA. If `<dest>/<shortsha>/` exists → **skip** (the source is identical to a known snapshot; unless the perimeter changed — see [Perimeter revisions](#perimeter-revisions) below). Otherwise `gh repo clone --depth=1`, copy listed `paths`, write `.sync-meta.json`, purge the clone in `cache/sync-repos/`.
3. `.claude/commands/sync-repos.md`: resolves `$ARGUMENTS` (explicit names or interactive multiSelect if empty), invokes the script, then chains `/ingest <snapshot>` on each `CREATED`.

### Why this setup is faithful to Karpathy

- **Immutability preserved, zero exception.** Each snapshot is a new folder. Old ones are never modified or deleted.
- **The event, not the date.** The shortsha is the natural unit: one merge = one snapshot, no noise if nothing moved.
- **History becomes signal.** Contradictions between successive versions (v1 said X, v2 says Y) become capturable by `/lint` — exactly what Karpathy calls _knowledge compilation_.
- **Hash-based idempotence keeps working.** `/ingest` detects via `source_sha256` that a snapshot's doc is identical to a previous one and skips.

### User interface

| Invocation                    | Effect                                                             |
| ----------------------------- | ------------------------------------------------------------------ |
| `/sync-repos`                 | interactive multiSelect (avoids the unintended big run on N repos) |
| `/sync-repos <name1> <name2>` | those sources only                                                 |

### Manifest schema

```json
{
  "default_paths": ["docs/", "README.md", "CHANGELOG.md"],
  "default_exclude_paths": [],
  "sources": [
    {
      "name": "your-repo",
      "repo": "your-org/your-repo",
      "branch": "main",
      "dest": "raw/tracked-repos/your-repo",
      "paths": ["docs/", "README.md"],
      "exclude_paths": []
    }
  ]
}
```

Each source declares its own `dest`. If you track several categories of repos (e.g. core components vs derivative projects), feel free to organize: `raw/tracked-repos/core/<name>/` vs `raw/tracked-repos/projects/<name>/`, or any other layout. The script assumes nothing.

### Generic examples

- `vercel/next.js` — track a web framework's evolution.
- `nf-core/sarek` — bioinfo pipeline whose docs evolve.
- `modelcontextprotocol/specification` — moving MCP spec.
- `your-org/internal-cli` — internal tool whose docs you follow release after release.

## What this unlocks

- **Working with the current state of components.** When a repo evolves, you can re-sync, the wiki reflects the new version, the old ones stay consultable.
- **Querying evolution.** `/query how did the component X docs evolve between the last two versions?` becomes naturally possible (two snapshots, two source pages, cross-ref).
- **Generic frame.** The same pattern applies to any external repo (docs of a framework you want to follow, spec of an evolving standard).

## Open questions

- **Long-term volume.** If N repos each merge M times per year, that's N×M snapshots/year. To watch — a future `/lint` could suggest consolidating old snapshots of the same component if they're no longer referenced by any live wiki page.
- **`paths` granularity.** Default for now is `["docs/", "README.md", "CHANGELOG.md"]`. If a repo has its docs elsewhere (e.g. `docs-site/content/`), tune per-source in the manifest.

## Idempotent re-snapshots (content coverage)

A tracked repo's HEAD SHA advances on **every** commit, so `/sync-repos` creates a new `<dest>/<shortsha>/` even when the documented `paths:` did not change. `scan-raw` covers those files **by content** (sha256), scoped to the same `(dest, relative-path)` lineage via each snapshot's `.sync-meta.json`. Consequence: a full `/ingest` sweep after a no-op or partial re-snapshot reports `NEW` only for files whose **content** actually changed — realising the "no noise if nothing moved" principle above. Hashes are cached (`cache/.hash-cache.json`, keyed by mtime+size) so immutable snapshots are hashed once. Disk duplication of identical snapshots remains (a future purge could consolidate them); it no longer costs anything at scan time.

A `0 NEW` default run does **not** mean every snapshot file was declared: a single declared file also covers all its siblings through implicit directory inheritance (`dir-implicit`), by design — without it, every snapshot would flood `/ingest` with `NEW` lines. To see the real coverage deficit, run the opt-in audit `bash scripts/wiki-maint/scan-raw.sh --strict-coverage`: it appends `UNDECLARED <path>  (dir-covered-by: <slug>)` lines (and an `undeclared[]` array under `--format=json`) for snapshot files granted coverage only by directory inheritance — never declared via `source_path`/`covered_paths` and never read as byte-identical content under a covered lineage version. Default output is unchanged; the audit rejects `--force` and `--pending`.

### Perimeter revisions

Widening (or otherwise editing) a source's `paths:`/`exclude_paths:` used to have no effect until the upstream repo received an unrelated commit — the SHA had not moved, so the sync answered `SKIPPED` (#106). Every snapshot records its capture perimeter in `.sync-meta.json` (`paths`, `exclude_paths`); `/sync-repos` now compares the manifest against the **latest revision** of the current SHA (set-wise, order-insensitive) and, on any difference, captures a **perimeter revision** into `<dest>/<shortsha>-rN/` (N ≥ 2; the base snapshot is r1). The previous snapshot is never modified — immutability holds per directory. `/ingest` needs no special handling: files byte-identical to a **declared** file of an earlier revision are content-covered (`SKIP (content)`) — dir-implicit-only files are not in the content index and may resurface as `NEW`. Snapshots predating `.sync-meta.json` perimeters (hand-made) are never auto-revisioned: the sync keeps `SKIPPED` and prints a `note:` on stderr.

## Files shipped

- [`tracked-repos.config.json`](../../tracked-repos.config.json) — manifest (empty by default at bootstrap, populate as you go).
- [`scripts/sync-repos.sh`](../../scripts/sync-repos.sh) — bash orchestration (gh + jq).
- [`.claude/commands/sync-repos.md`](../../.claude/commands/sync-repos.md) — slash command.
- [`CLAUDE.md`](../../CLAUDE.md) — workflow documentation (SYNC-REPOS section).
