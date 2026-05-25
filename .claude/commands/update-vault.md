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

```bash
ALL_MIGRATIONS=$(git ls-tree -r "template-upstream/${TARGET_BRANCH}" --name-only \
  | grep '^scripts/migrations/v[0-9]' | sort -V)
MIGRATIONS_TO_APPLY=$(for f in $ALL_MIGRATIONS; do
  slug=$(basename "$f" .md)
  printf '%s\n' "${APPLIED_MIGRATIONS[@]}" | grep -qFx "$slug" || echo "$slug"
done)
```

Per-migration tracking (vs version-range filter) handles retroactive migrations added upstream after a version bump.

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
  "questions": [{
    "question": "<f> has overlapping edits between your local version and the template update. How do you want to resolve it?",
    "header": "Conflict: <basename>",
    "multiSelect": false,
    "options": [
      {"label": "Keep merged version with markers", "description": "File contains <<<<<<< / ======= / >>>>>>> showing both sides. Edit it manually after this command, then re-stage."},
      {"label": "Use template version (discard local edits)", "description": "Overwrite with the upstream template. Your local customisations on this file are lost."},
      {"label": "Use vault version (discard template update)", "description": "Restore your local version. The file diverges from template until you re-run /update-vault and resolve."},
      {"label": "Skip this file", "description": "Do not stage. The file stays in its current marker-annotated state until you handle it manually."}
    ]
  }]
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

### 6. Run the migration chain

For each migration in `MIGRATIONS_TO_APPLY` (ascending version order), invoke it as a sub-workflow. Migration files live under `scripts/migrations/v<X>-*.md` — read the file and execute its steps (AskUserQuestion, edits, commit).

Each migration returns one of three verdicts:
- **Applied**: file updated, dedicated commit by the migration. Append its slug to `APPLIED_MIGRATIONS`.
- **Manual edit / Skipped**: do NOT append. The migration is re-proposed at the next `/update-vault`.

### 7. Bump `.claude/template-version`

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

### 8. Legacy vault edge case

If `.claude/template-version` did not exist at session start (step 2 detected v1.0.0 or v1.0.1), step 7 creates it for the first time — even if not all migrations were accepted, with version set to the last fully-applied baseline. This pins the versioning mechanism going forward.

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
