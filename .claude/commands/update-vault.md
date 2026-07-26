---
description: Cherry-pick improvements from the upstream template into this vault, with versioned migrations
argument-hint: [target-branch]
---

# /update-vault

Updates this vault from the upstream `tetra-plg/boiling-brain` template. Detects the vault's version, propagates new files via 3-way merge that preserves local edits, runs breaking migrations between the two versions.

## Arguments

`$ARGUMENTS` — optional `template-upstream` branch (default: `main`). Use to test pre-release feat branches: `/update-vault feat/v1.2.0`.

## Steps

### 1. Fetch the upstream template

```bash
git remote add template-upstream https://github.com/tetra-plg/boiling-brain.git 2>/dev/null || true
git fetch template-upstream --tags
```

### 2. Detect the local version

```bash
TARGET_BRANCH="${ARGUMENTS:-main}"
eval "$(bash scripts/wiki-maint/detect-vault-version.sh "$TARGET_BRANCH")"
```

This populates `LOCAL_VERSION`, `LOCAL_SHA`, and the `APPLIED_MIGRATIONS` array. The script handles v1.0.0/v1.0.1/v1.0.2+ vaults and back-fills `applied-migrations` for vaults bumped pre-v1.1.0. If it exits non-zero (`BASELINE_MISSING`), stop and surface the error.

### 3. Detect the target version

```bash
TARGET_VERSION=$(git show "template-upstream/${TARGET_BRANCH}:.claude/template-version" 2>/dev/null \
  | grep '^template-version:' | awk '{print $2}')
TARGET_SHA=$(git rev-parse "template-upstream/${TARGET_BRANCH}")
[ -z "$TARGET_VERSION" ] && TARGET_VERSION="$TARGET_SHA"
echo "Target: ${TARGET_BRANCH} → ${TARGET_VERSION} (${TARGET_SHA:0:12}…)"
```

### 4. Compute the migration chain to apply

A migration enters `MIGRATIONS_TO_APPLY` if either:

- Its slug is NOT in `APPLIED_MIGRATIONS` (the normal "new migration" path), OR
- Its slug IS in `APPLIED_MIGRATIONS` BUT its frontmatter contains `force-rerun: true` (the "re-evaluate on every update" path, used when a previously-applied migration ships a fix or extension that needs to re-execute on already-migrated vaults).

```bash
ALL_MIGRATIONS=$(git ls-tree -r "template-upstream/${TARGET_BRANCH}" --name-only \
  | grep '^scripts/migrations/v[0-9]' | sort -V)
MIGRATIONS_TO_APPLY=$(for f in $ALL_MIGRATIONS; do
  slug=$(basename "$f" .md)
  # Always include if not yet applied
  if ! printf '%s\n' "${APPLIED_MIGRATIONS[@]}" | grep -qFx "$slug"; then
    echo "$slug"
    continue
  fi
  # Already applied — check the force-rerun flag in the migration frontmatter
  force=$(git show "template-upstream/${TARGET_BRANCH}:$f" 2>/dev/null \
    | awk 'BEGIN{fm=0} /^---$/{fm++; next} fm==1 && /^force-rerun:/{print $2}' \
    | tr -d ' "')
  if [ "$force" = "true" ]; then
    echo "$slug"
  fi
done)
```

Per-migration tracking (vs version-range filter) handles retroactive migrations added upstream after a version bump. The `force-rerun` flag handles the case where a previously-applied migration receives a content fix that must re-execute on already-migrated vaults (idempotency is the migration author's responsibility — a `force-rerun: true` migration must be safe to re-apply).

- If `MIGRATIONS_TO_APPLY` is empty AND `LOCAL_VERSION == TARGET_VERSION`: "Your vault is up to date." → stop.
- If empty but version differs: skip to step 5 (only file propagation needed).

### 5. Propagate the changed files

Compute the list of files that changed between baseline and target, excluding bootstrap-consumed files:

```bash
CHANGED_FILES=$(git diff --name-only "${LOCAL_SHA}" "template-upstream/${TARGET_BRANCH}" \
  | grep -vE '\.tpl$|^BOOTSTRAP\.md$|^PLACEHOLDERS\.md$|^CONTRIBUTING\.md$|^CLAUDE\.md$')
```

Show the list to the user via `AskUserQuestion` (multiSelect). Pre-check all newly added files and everything under `.claude/rules/`.

Run the propagation on the selected files:

```bash
RESULTS=$(printf '%s\n' "$SELECTED_FILES" \
  | bash scripts/wiki-maint/propagate-templates.sh "$LOCAL_SHA" "$TARGET_BRANCH")
```

The script emits one line per file: `PROPAGATED <f>`, `FAST_FORWARD <f>`, `AUTO_MERGED <f>`, or `CONFLICT <f>`. AUTO_MERGED means local edits were preserved alongside template changes (3-way merge). CONFLICT means overlapping edits — the file on disk now contains conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`).

For each `CONFLICT <f>`, ask the user how to resolve:

```json
{
  "questions": [
    {
      "question": "<f> has overlapping edits between your local version and the template update. How do you want to resolve it?",
      "header": "Conflict: <basename>",
      "multiSelect": false,
      "options": [
        {
          "label": "Keep merged version with markers",
          "description": "File contains <<<<<<< / ======= / >>>>>>> showing both sides. Edit it manually after this command, then re-stage."
        },
        {
          "label": "Use template version (discard local edits)",
          "description": "Overwrite with the upstream template. Your local customisations on this file are lost."
        },
        {
          "label": "Use vault version (discard template update)",
          "description": "Restore your local version. The file diverges from template until you re-run /update-vault and resolve."
        },
        {
          "label": "Skip this file",
          "description": "Do not stage. The file stays in its current marker-annotated state until you handle it manually."
        }
      ]
    }
  ]
}
```

Apply the choice (per-file):

```bash
case "$CHOICE" in
  "Keep merged version with markers")              : ;;  # already on disk
  "Use template version (discard local edits)")    git show "template-upstream/${TARGET_BRANCH}:$f" > "$f" ;;
  "Use vault version (discard template update)")   git show "HEAD:$f" > "$f" 2>/dev/null || rm -f "$f" ;;
  "Skip this file")                                UNSTAGE+=("$f") ;;
esac
```

Stage everything except `UNSTAGE` and commit:

```bash
git add <propagated files not in UNSTAGE>
git commit -m "chore: propagate template files (${LOCAL_VERSION} → ${TARGET_VERSION})

Auto-merged: <case-D clean files>
Resolved: <conflict files with user choice>
Skipped: <files in UNSTAGE>
"
```

Record which MCP-stack files were **actually staged** (propagated minus `UNSTAGE`) — this drives step 7:

```bash
# STAGED = the exact list passed to `git add` above
MCP_SERVER_CHANGED=$(printf '%s\n' "${STAGED[@]}" \
  | grep -cE '^scripts/mcp/(mcp-wiki\.py|wiki_core\.py)$' || true)
MCP_SETUP_CHANGED=$(printf '%s\n' "${STAGED[@]}" \
  | grep -cE '^scripts/mcp/setup-mcp\.sh$' || true)
```

`wiki-cli.*`, `ingest-headless-guard.sh` and the MCP test files are deliberately excluded: they affect neither the running server process nor its registration, so they must not trigger a reconnect prompt. A file the user skipped must not trigger step 7 either — hence "staged", not "changed".

### 6. Run the migration chain

For each migration in `MIGRATIONS_TO_APPLY` (ascending version order), invoke it as a sub-workflow. Migration files live under `scripts/migrations/v<X>-*.md` — read the file and execute its steps (AskUserQuestion, edits, commit).

Each migration returns one of three verdicts:

- **Applied**: file updated, dedicated commit by the migration. Append its slug to `APPLIED_MIGRATIONS`.
- **Manual edit / Skipped**: do NOT append. The migration is re-proposed at the next `/update-vault`.

### 7. Refresh the MCP stack (conditional)

Run this step **only** if `MCP_SERVER_CHANGED` or `MCP_SETUP_CHANGED` (step 5) is non-zero. Otherwise skip it entirely — no prompt, no output.

Why it is needed: the MCP server is registered against a **fixed path**, so propagating new code leaves the registration valid but the **running process** stale — the harness started it at session boot and it still serves the previous `mcp-wiki.py`.

#### 7.1 Offer to re-run `setup-mcp.sh`

`setup-mcp.sh` mutates **user-global** state, so it is offered, never run silently:

```json
{
  "questions": [
    {
      "question": "The MCP stack changed (<changed MCP files>). Re-run setup-mcp.sh to refresh the registration and the global tool-instructions block?",
      "header": "MCP refresh",
      "multiSelect": false,
      "options": [
        {
          "label": "Yes, re-run setup-mcp.sh",
          "description": "Runs `bash scripts/mcp/setup-mcp.sh --vault-path \"$(pwd)\"`. Idempotent, but mutates ~/.claude/settings.json and ~/.claude/CLAUDE.md, and re-registers the server at user scope (visible from every project)."
        },
        {
          "label": "No, skip",
          "description": "Registration and global instructions block stay as they are. Re-run the command manually later if needed."
        }
      ]
    }
  ]
}
```

If accepted:

```bash
bash scripts/mcp/setup-mcp.sh --vault-path "$(pwd)"
```

Capture its stdout and show it to the user. If the script fails, report the failure and continue — the propagation commit is already done and must not be rolled back.

#### 7.2 Signal the reload when the server code changed

If `MCP_SERVER_CHANGED` is non-zero, print this block. Re-running `setup-mcp.sh` re-registers and refreshes the instructions block, but it does **not** reload the running process:

```
⚠️  MCP server code changed (mcp-wiki.py / wiki_core.py).
    This session is still running the PREVIOUS version.
    Restart Claude Code (or reconnect the boiling-brain-wiki MCP server)
    to load the new code. Until then, MCP tool results come from the old server.
```

#### 7.3 Report

Close the step with one line, to be included in the run summary:

```
MCP: <changed files> · setup-mcp.sh <run|skipped|failed> · reload <required|not required>
```

### 8. Bump `.claude/template-version`

```bash
TODAY=$(date +%Y-%m-%d)
ALL_APPLIED=$(all_migrations_accepted && echo true || echo false)
NEW_VERSION="$LOCAL_VERSION"; NEW_SHA="$LOCAL_SHA"
[ "$ALL_APPLIED" = "true" ] && { NEW_VERSION="$TARGET_VERSION"; NEW_SHA="$TARGET_SHA"; }

{
  echo "template-version: ${NEW_VERSION}"
  echo "template-sha: ${NEW_SHA}"
  echo "last-updated: ${TODAY}"
  echo "applied-migrations:"
  printf '  - %s\n' "${APPLIED_MIGRATIONS[@]}"
} > .claude/template-version

git add .claude/template-version
if [ "$ALL_APPLIED" = "true" ]; then
  git commit -m "chore: bump template-version to ${NEW_VERSION}"
else
  git commit -m "chore: update applied-migrations (${LOCAL_VERSION} retained, pending migrations remain)"
  echo "⚠️ Some migrations were not applied. Version stays at ${LOCAL_VERSION}. Re-run /update-vault after manual resolution."
fi
```

### 9. Legacy vault edge case

If `.claude/template-version` did not exist at session start (step 2 detected v1.0.0 or v1.0.1), step 8 creates it for the first time — even if not all migrations were accepted, with version set to the last fully-applied baseline. This pins the versioning mechanism going forward.

## Notes

Excluded from propagation (consumed at bootstrap or user-owned):

- `*.tpl`, `BOOTSTRAP.md`, `PLACEHOLDERS.md`, `CONTRIBUTING.md` — bootstrap-only.
- `CLAUDE.md` — user-owned; migrated only through `scripts/migrations/v<X>-*.md`.

Vault-specific files (never in template, never overwritten): `.claude/agents/<domain>-expert.md`, `wiki/domains/*.md`, `wiki/overview.md`, `wiki/log.md`, `wiki/radar.md`, `wiki/index.md`.

`.claude/rules/` is upstream-tracked: additions and modifications propagate at every `/update-vault`.

If no baseline exists (no `.claude/template-version`, no `.template-bootstrap-sha`, no `v1.0.0` tag), step 2 exits `BASELINE_MISSING`. Recover manually:

```bash
git fetch template-upstream --tags
git rev-list -n 1 v1.0.0 > .template-bootstrap-sha
git add .template-bootstrap-sha
git commit -m "fix: add template bootstrap sha (retrocompat)"
```
