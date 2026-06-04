#!/usr/bin/env bash
# detect-vault-version.sh — detect a vault's current template version.
#
# Usage:
#   bash scripts/wiki-maint/detect-vault-version.sh [TARGET_BRANCH]
#   eval "$(bash scripts/wiki-maint/detect-vault-version.sh main)"
#
# Outputs (on stdout, eval-friendly):
#   LOCAL_VERSION="1.0.3"
#   LOCAL_SHA="abc1234..."
#   APPLIED_MIGRATIONS=("v1.0.2-claude-md-slim" "v1.0.3-vault-language")
#
# Side-channel (stderr): human-readable status messages.
# Exit code: 0 on success, 1 if no baseline can be detected (vault < v1.0.0 or
# .template-bootstrap-sha and v1.0.0 tag both missing).
#
# Detection logic, in order:
#   1. `.claude/template-version` present → v1.0.2+ standard case; reads
#      `template-version`, `template-sha`, `applied-migrations`.
#   2. `.template-bootstrap-sha` present (no template-version) → v1.0.1 legacy.
#   3. v1.0.0 tag reachable on template-upstream → v1.0.0 legacy.
#   4. Otherwise → BASELINE_MISSING, exit 1.
#
# Back-compat `applied-migrations`:
# If `.claude/template-version` exists without the field (vault was bumped before
# v1.1.0 introduced per-migration tracking), populate it from the version
# baseline: every migration with version <= LOCAL_VERSION is assumed applied
# (because the previous mechanism blocked any version bump when a migration was
# skipped). TARGET_BRANCH (arg 1, default "main") is the branch on
# template-upstream where migration files are listed.

set -euo pipefail

TARGET_BRANCH="${1:-main}"

emit() { printf '%s\n' "$*"; }                          # stdout: eval-friendly
log()  { printf '%s\n' "$*" >&2; }                      # stderr: human messages

LOCAL_VERSION=""
LOCAL_SHA=""
APPLIED_MIGRATIONS=()

if [ -f .claude/template-version ]; then
  LOCAL_VERSION=$(grep '^template-version:' .claude/template-version 2>/dev/null | awk '{print $2}' || true)
  LOCAL_SHA=$(grep '^template-sha:' .claude/template-version 2>/dev/null | awk '{print $2}' || true)

  # Parse YAML applied-migrations list (a sequence of `  - <slug>` lines under
  # the `applied-migrations:` key).
  while IFS= read -r slug; do
    [ -n "$slug" ] && APPLIED_MIGRATIONS+=("$slug")
  done < <(awk '
    /^applied-migrations:/{flag=1; next}
    /^[^[:space:]]/{flag=0}
    flag && /^[[:space:]]*-/{gsub(/^[[:space:]]*-[[:space:]]*/, ""); print}
  ' .claude/template-version)

  # Back-compat: field absent for vaults bumped pre-v1.1.0.
  if [ "${#APPLIED_MIGRATIONS[@]}" -eq 0 ]; then
    log "applied-migrations field absent — populating from version baseline (${LOCAL_VERSION})."
    while IFS= read -r f; do
      slug=$(basename "$f" .md)
      version=$(printf '%s' "$slug" | sed 's/^v//' | awk -F'-' '{print $1}')
      if printf '%s\n%s\n' "$version" "$LOCAL_VERSION" | sort -CV; then
        APPLIED_MIGRATIONS+=("$slug")
      fi
    done < <(git ls-tree -r "template-upstream/${TARGET_BRANCH}" --name-only 2>/dev/null \
             | grep '^scripts/migrations/v[0-9]' || true)
  fi

elif [ -f .template-bootstrap-sha ]; then
  LOCAL_VERSION="1.0.1"
  LOCAL_SHA=$(cat .template-bootstrap-sha)
  log "Vault detected at v1.0.1 (legacy). .claude/template-version will be created during this update."

else
  # Try v1.0.0 tag on template-upstream as last-resort baseline.
  if LOCAL_SHA=$(git rev-list -n 1 v1.0.0 2>/dev/null) && [ -n "$LOCAL_SHA" ]; then
    LOCAL_VERSION="1.0.0"
    log "Vault detected at v1.0.0 (legacy, no .template-bootstrap-sha). Baseline = tag v1.0.0."
  else
    log "BASELINE_MISSING: no .claude/template-version, no .template-bootstrap-sha, no v1.0.0 tag."
    log "Create the baseline manually (see /update-vault Notes) then re-run."
    exit 1
  fi
fi

# Emit eval-friendly output. Quoting handles slugs with spaces (none expected,
# but defensive). Array syntax is bash 3.2+ compatible.
emit "LOCAL_VERSION=\"${LOCAL_VERSION}\""
emit "LOCAL_SHA=\"${LOCAL_SHA}\""
if [ "${#APPLIED_MIGRATIONS[@]}" -gt 0 ]; then
  printf 'APPLIED_MIGRATIONS=('
  for slug in "${APPLIED_MIGRATIONS[@]}"; do printf '"%s" ' "$slug"; done
  printf ')\n'
else
  emit "APPLIED_MIGRATIONS=()"
fi

log "Local version: ${LOCAL_VERSION} (SHA ${LOCAL_SHA:0:12}…) — ${#APPLIED_MIGRATIONS[@]} migration(s) applied."
