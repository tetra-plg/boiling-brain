---
description: Cherry-pick improvements from the upstream template into this vault, with versioned migrations
argument-hint: [target-branch]
---

# /update-vault

Updates this vault from the upstream `tetra-plg/boiling-brain` template. Since v1.0.2, `/update-vault` is a **versioned migration machine**: it detects the vault's version (via `.claude/template-version`), compares it to the target version, propagates new files, and runs the breaking migrations between the two versions when needed.

Use this workflow to pull new scripts, slash-commands, rules or architectural decisions published in the template after your bootstrap.

## Arguments

`$ARGUMENTS` — optional target branch ref on `template-upstream` (default: `main`). Use this to test a pre-release feat branch before its release, e.g. `/update-vault feat/v1.2.0`.

## Steps

### 1. Configure the `template-upstream` remote (one-time)

```bash
git remote add template-upstream https://github.com/tetra-plg/boiling-brain.git 2>/dev/null \
  && echo "remote template-upstream added" \
  || echo "remote template-upstream already configured"
git fetch template-upstream --tags
```

### 2. Detect the local version (with v1.0.0 and v1.0.1 backwards compatibility)

```bash
LOCAL_VERSION=""
LOCAL_SHA=""

if [ -f .claude/template-version ]; then
  # Standard case: v1.0.2+
  LOCAL_VERSION=$(grep '^template-version:' .claude/template-version | awk '{print $2}')
  LOCAL_SHA=$(grep '^template-sha:' .claude/template-version | awk '{print $2}')
  # applied-migrations field (introduced v1.1.0+) — list of migration slugs applied locally
  APPLIED_MIGRATIONS=$(awk '
    /^applied-migrations:/{flag=1; next}
    /^[a-z]/{flag=0}
    flag && /^[[:space:]]*-/{gsub(/^[[:space:]]*-[[:space:]]*/, ""); print}
  ' .claude/template-version)
elif [ -f .template-bootstrap-sha ]; then
  # v1.0.1 backwards compat: has .template-bootstrap-sha but no .claude/template-version
  LOCAL_VERSION="1.0.1"
  LOCAL_SHA=$(cat .template-bootstrap-sha)
  echo "Vault detected at v1.0.1 (legacy). .claude/template-version will be created during this update."
else
  # v1.0.0 backwards compat: neither file. Use tag v1.0.0 as baseline.
  LOCAL_SHA=$(git -C . show template-upstream/main 2>/dev/null && git rev-list -n 1 v1.0.0 2>/dev/null || echo "")
  if [ -n "$LOCAL_SHA" ]; then
    LOCAL_VERSION="1.0.0"
    echo "Vault detected at v1.0.0 (legacy, no .template-bootstrap-sha). Baseline = tag v1.0.0."
  else
    echo "BASELINE_MISSING"
    echo "No baseline found (.claude/template-version, .template-bootstrap-sha, and tag v1.0.0 all missing)."
    echo "Create the file manually (see Notes at the bottom) then re-run /update-vault."
    exit 1
  fi
fi

echo "Local version: $LOCAL_VERSION (SHA $LOCAL_SHA)"
```

**Back-compat `applied-migrations`** : if the field is absent (vault bumped pre-v1.1.0), populate it from version baseline. Because the previous mechanism blocked any version bump when a migration was skipped, `template-version: X.Y.Z` certifies that all migrations with `version <= X.Y.Z` were applied.

```bash
if [ -z "$APPLIED_MIGRATIONS" ] && [ -f .claude/template-version ]; then
  APPLIED_MIGRATIONS=$(git ls-tree -r "template-upstream/${TARGET_BRANCH:-main}" --name-only \
    | grep '^scripts/migrations/v[0-9]' \
    | while IFS= read -r f; do
        slug=$(basename "$f" .md)
        version=$(echo "$slug" | sed 's/^v//' | awk -F'-' '{print $1}')
        if printf '%s\n%s\n' "$version" "$LOCAL_VERSION" | sort -CV; then
          echo "$slug"
        fi
      done)
  echo "applied-migrations field was missing — populated from version baseline (${LOCAL_VERSION})."
fi
```

### 3. Detect the target version (from the remote)

```bash
TARGET_BRANCH="${ARGUMENTS:-main}"
TARGET_VERSION=$(git show "template-upstream/${TARGET_BRANCH}:.claude/template-version" 2>/dev/null \
  | grep '^template-version:' | awk '{print $2}')
TARGET_SHA=$(git rev-parse "template-upstream/${TARGET_BRANCH}")

if [ -z "$TARGET_VERSION" ]; then
  echo "Upstream template has no .claude/template-version (probably < v1.0.2). Falling back to SHA."
  TARGET_VERSION="$TARGET_SHA"
fi

echo "Target branch: ${TARGET_BRANCH} — version: $TARGET_VERSION (SHA $TARGET_SHA)"
```

### 4. Compute the migration chain to apply

List all migrations on the target branch and keep those **not present in `APPLIED_MIGRATIONS`**. This per-migration tracking handles retroactive migrations (added upstream after a version bump) — a version-range filter would silently skip them forever.

```bash
ALL_MIGRATIONS=$(git ls-tree -r "template-upstream/${TARGET_BRANCH}" --name-only \
  | grep '^scripts/migrations/v[0-9]' \
  | sort -V)

MIGRATIONS_TO_APPLY=$(for f in $ALL_MIGRATIONS; do
  slug=$(basename "$f" .md)
  echo "$APPLIED_MIGRATIONS" | grep -qFx "$slug" || echo "$slug"
done)
```

If `MIGRATIONS_TO_APPLY` is empty and local version == target: "Your vault is up to date."

If `MIGRATIONS_TO_APPLY` is empty but local version < target: only propagate the files (step 5).

### 5. Identify and propagate the changed files

List the files changed between `LOCAL_SHA` and `TARGET_SHA`, excluding files consumed at bootstrap:

```bash
git diff --name-only ${LOCAL_SHA} "template-upstream/${TARGET_BRANCH}" \
  | grep -v '\.tpl$' \
  | grep -v '^BOOTSTRAP\.md$' \
  | grep -v '^PLACEHOLDERS\.md$' \
  | grep -v '^CONTRIBUTING\.md$' \
  | grep -v '^CLAUDE\.md$'
```

Notes:

- **`.claude/rules/**`** is included naturally (not in exclusions).
- **`scripts/migrations/**`** is also included: migrations are propagated into the vault to be consumable at the next `/update-vault`.
- **`CLAUDE.md`** is excluded: it's user-owned. Its migration is handled by the interactive `scripts/migrations/v<X>-*.md` slash-commands, never via overwrite.

For files newly added in the template (which don't exist yet in the vault — e.g. `.claude/template-version`, `.claude/rules/*`, `scripts/migrations/*`), don't filter by `[ -e "$f" ]`: they must be created.

Show the list to the user via `AskUserQuestion` (multiSelect): which files do they want to update? Pre-check all newly added files and all `.claude/rules/` files.

For each selected file:

```bash
mkdir -p "$(dirname "$f")"
git show "template-upstream/${TARGET_BRANCH}:$f" > "$f"
```

> **Why `git show` rather than `cherry-pick`?**
> Bootstrap resets the git history. The vault has no common ancestor with the template — `cherry-pick` would fail. `git show` copies the target content, no history dependency.

Dedicated commit:

```bash
git add <updated files>
git commit -m "chore: propagate template files (${LOCAL_VERSION} → ${TARGET_VERSION})"
```

### 6. Run the migration chain

For each migration identified at step 4, in ascending version order, **invoke the corresponding slash-command**. Example for v1.0.2:

```
/v1.0.2-claude-md-slim
```

Note: migration files live under `scripts/migrations/` (not `.claude/commands/`), so they are not exposed as top-level slash-commands. `/update-vault` invokes them as a **sub-workflow**: you read the `scripts/migrations/v<X>-*.md` file and execute its workflow step-by-step, following the instructions it contains (read, detect, AskUserQuestion, write).

Each migration can pick its own verdict:

- **Applied**: the file is updated, dedicated commit by the migration itself. Append the migration slug to `APPLIED_MIGRATIONS` (the slug becomes a permanent record in `.claude/template-version`).
- **Manual edit requested by the user**: the migration touches nothing, the user takes over. **Do not append to `APPLIED_MIGRATIONS`** — it will be re-proposed at the next `/update-vault`.
- **Skipped**: same, do not append.

Track the state of each migration in a memory variable to decide on the final bump and the updated `applied-migrations` list.

### 7. Bump `.claude/template-version`

Write the updated file with the new `applied-migrations` list. Bump `template-version` to `TARGET_VERSION` **only if all applicable migrations were accepted**; otherwise keep the local version and let the next `/update-vault` re-propose the pending migrations.

```bash
TODAY=$(date +%Y-%m-%d)
ALL_APPLIED=$(all_migrations_accepted && echo "true" || echo "false")
NEW_VERSION="$LOCAL_VERSION"; NEW_SHA="$LOCAL_SHA"
if [ "$ALL_APPLIED" = "true" ]; then
  NEW_VERSION="$TARGET_VERSION"; NEW_SHA="$TARGET_SHA"
fi

{
  echo "template-version: ${NEW_VERSION}"
  echo "template-sha: ${NEW_SHA}"
  echo "last-updated: ${TODAY}"
  echo "applied-migrations:"
  for slug in $APPLIED_MIGRATIONS; do
    echo "  - $slug"
  done
} > .claude/template-version

git add .claude/template-version
if [ "$ALL_APPLIED" = "true" ]; then
  git commit -m "chore: bump template-version to ${NEW_VERSION}"
else
  git commit -m "chore: update applied-migrations (${LOCAL_VERSION} retained, pending migrations remain)"
fi
```

If a migration was skipped or manually edited:

> ⚠️ Some migrations were not applied. `.claude/template-version` stays at `${LOCAL_VERSION}` (with `applied-migrations` updated). Re-run `/update-vault` once you've finalized the manual migrations.

### 8. Edge case: legacy v1.0.0 or v1.0.1 vault (no `.claude/template-version`)

If `.claude/template-version` did not exist at session start (backwards compat detected at step 2), it must be **created** at the end of this first update, even if not all migrations were accepted. The initial creation pins the baseline.

Case A — all migrations accepted: `.claude/template-version` is created at step 7 with `template-version: ${TARGET_VERSION}` (standard case).

Case B — at least one migration skipped or under manual edit: create `.claude/template-version` with **the version from before the skipped migrations**:

```bash
LAST_APPLIED_VERSION="$LOCAL_VERSION"  # update if partial migrations applied
TODAY=$(date +%Y-%m-%d)
{
  echo "template-version: ${LAST_APPLIED_VERSION}"
  echo "template-sha: ${LOCAL_SHA}"
  echo "last-updated: ${TODAY}"
  echo "applied-migrations:"
  for slug in $APPLIED_MIGRATIONS; do
    echo "  - $slug"
  done
} > .claude/template-version
git add .claude/template-version
git commit -m "chore: initialize .claude/template-version (${LAST_APPLIED_VERSION})"
```

This way the legacy vault gains the new versioning mechanism even if migration is unfinished.

## Notes

**Files never updated automatically:**

- `*.tpl`, `BOOTSTRAP.md`, `PLACEHOLDERS.md`, `CONTRIBUTING.md` — consumed at bootstrap.
- `CLAUDE.md` — user-owned, migrated only through interactive `scripts/migrations/v<X>-*.md`.

**Files specific to your instance (never in the template):**

Your agents (`.claude/agents/<domain>-expert.md`), your hubs (`wiki/domains/*.md`), `wiki/overview.md`, `wiki/log.md`, `wiki/radar.md`, `wiki/index.md`, etc. have names distinct from template files — they will never be overwritten.

**`.claude/rules/`** is upstream-tracked: any addition or modification of a rule in the template will be propagated to the vault at every `/update-vault`.

**Missing baseline (hypothetical pre-v1.0.0 vault):**

If neither `.claude/template-version`, `.template-bootstrap-sha`, nor the `v1.0.0` tag is found, create the file manually:

```bash
git fetch template-upstream --tags
git rev-list -n 1 v1.0.0 > .template-bootstrap-sha
git add .template-bootstrap-sha
git commit -m "fix: add template bootstrap sha (retrocompat)"
```

Then re-run `/update-vault` — the v1.0.0 backwards compat will take over.
