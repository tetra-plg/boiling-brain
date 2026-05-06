---
description: Sync the docs of GitHub repos declared in tracked-repos.config.json to raw/ as SHA-keyed snapshots, then chain /ingest
arguments-hint: [source-names — empty = interactive multiSelect]
---

Run the SYNC-REPOS workflow from CLAUDE.md on: $ARGUMENTS

The `tracked-repos.config.json` manifest (at the vault root) lists the repos to follow (`sources[]` field: `name`, `repo`, `branch`, `dest`, `paths`, `exclude_paths`). Each source declares its own `dest` — typically `raw/tracked-repos/<slug>`, but nothing prevents a different layout.

**Immutability principle.** Each sync creates a **new snapshot** under `<dest>/<shortsha>/` (shortsha = first 7 chars of the HEAD SHA of `branch`). If the snapshot already exists → skip. No existing file in `raw/` is ever modified.

### 1. Pre-requisites

1. `gh auth status` — if not authenticated: stop, ask the user to run `gh auth login`.
2. `tracked-repos.config.json` exists — otherwise: stop and signal.
3. `jq` installed — otherwise: suggest `brew install jq`.

### 2. Target resolution

From the **main context**, determine which sources to sync based on `$ARGUMENTS`:

- **One or more names** → sync those sources.
- **Empty** → read `tracked-repos.config.json`, display for each source: `name · repo · last shortsha snapshotted in dest/` (or `(never synced)`), then `AskUserQuestion` in **multiSelect** with:
  - one option per source (label: `<name>`)
  - `all` (everything)

Avoids an unintended "sync all" (N repos = N clones).

### 3. Script invocation

Call `scripts/sync-repos.sh` with the final list of names:
```bash
scripts/sync-repos.sh <name1> <name2>
```

The script writes to stdout lines of three forms:
- `CREATED <vault-relative-path>` — a new snapshot.
- `SKIPPED <name> (sha <shortsha> already snapshotted)` — no upstream merge since the last sync.
- `ERROR <name> <message>` — failure (clone, missing paths, repo unreachable).

### 4. Chaining /ingest

For each `CREATED <path>` line: chain `/ingest <path>`. The `/ingest` dispatch will propose the expert agent fitting the tracked repo's docs.

If multiple snapshots are created in the same run: ingest them **sequentially** (one by one), not in parallel — the expert agent must be able to cross-reference each snapshot with the wiki pages already present (including those created during the same run).

### 5. Final report

```
N snapshots created · K sources unchanged · E errors

Created:
- <dest>/<shortsha>  →  ingested via <agent>-expert
- ...

Unchanged:
- <name> (sha <shortsha> already snapshotted)

Errors:
- <name>: clone failure
```

Append to `wiki/log.md`:
```
## [YYYY-MM-DD] sync-repos | N snapshots created
<list of created and ingested snapshots>
```

### Notes

- No size limit: if a listed `paths[]` is bulky, the snapshot will be bulky. Adjust `paths` in the manifest as needed.
- For a new repo: edit the manifest, re-run `/sync-repos <new-name>`.
- A private repo requires `gh` to be authenticated with an account that has access.
