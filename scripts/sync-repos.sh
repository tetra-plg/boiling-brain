#!/usr/bin/env bash
# Usage:
#   scripts/sync-repos.sh                 # all sources from the manifest
#   scripts/sync-repos.sh name1 name2     # only these sources
#
# For each source:
#   - fetch the branch HEAD SHA via `gh api`
#   - if <dest>/<shortsha>/ already exists → SKIPPED, unless the perimeter changed → <shortsha>-rN
#   - otherwise → clone --depth=1, copy the listed paths, write .sync-meta.json
#
# stdout output (consumed by the /sync-repos slash command):
#   CREATED <abs-path>
#   SKIPPED <name> (sha <shortsha> already snapshotted)
#   ERROR <name> <message>

set -euo pipefail

VAULT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$VAULT_ROOT"

MANIFEST="$VAULT_ROOT/tracked-repos.config.json"
[[ -f "$MANIFEST" ]] || { echo "ERROR _manifest tracked-repos.config.json not found" >&2; exit 1; }
command -v jq >/dev/null || { echo "ERROR _prereq jq not installed (brew install jq)" >&2; exit 1; }
command -v gh >/dev/null || { echo "ERROR _prereq gh CLI not installed" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "ERROR _prereq gh not authenticated (gh auth login)" >&2; exit 1; }

# --- Parse args ---
NAMES=()
for arg in "$@"; do
  case "$arg" in
    --*)      echo "ERROR _args unknown flag: $arg" >&2; exit 1 ;;
    *)        NAMES+=("$arg") ;;
  esac
done

# --- Resolve the sources to process ---
DEFAULT_PATHS_JSON="$(jq -c '.default_paths // ["docs/","README.md","CHANGELOG.md"]' "$MANIFEST")"
DEFAULT_EXCLUDES_JSON="$(jq -c '.default_exclude_paths // []' "$MANIFEST")"

# Stream "name\trepo\tbranch\tdest\tpaths_json\texcludes_json"
SOURCES="$(
  jq -r --argjson defp "$DEFAULT_PATHS_JSON" --argjson defx "$DEFAULT_EXCLUDES_JSON" '
    .sources[]
    | [.name, .repo, .branch, .dest,
       ((.paths // $defp) | tostring),
       ((.exclude_paths // $defx) | tostring)]
    | @tsv
  ' "$MANIFEST"
)"

if [[ ${#NAMES[@]} -gt 0 ]]; then
  FILTERED=""
  for name in "${NAMES[@]}"; do
    line="$(echo "$SOURCES" | awk -F'\t' -v n="$name" '$1 == n')"
    [[ -z "$line" ]] && { echo "ERROR $name not found in the manifest" >&2; exit 1; }
    FILTERED+="$line"$'\n'
  done
  SOURCES="${FILTERED%$'\n'}"
fi

[[ -z "$SOURCES" ]] && { echo "ERROR _selection no source selected" >&2; exit 1; }

mkdir -p "$VAULT_ROOT/cache/sync-repos"

# --- Processing ---
SYNCED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

while IFS=$'\t' read -r name repo branch dest paths_json excludes_json; do
  [[ -z "$name" ]] && continue

  sha="$(gh api "repos/$repo/commits/$branch" --jq '.sha' 2>/dev/null)" || {
    echo "ERROR $name gh api failed (repo unreachable?)"
    continue
  }
  shortsha="${sha:0:7}"
  base_dir="$VAULT_ROOT/$dest/$shortsha"
  snapshot_dir="$base_dir"

  # Perimeter revisions (#106): when this SHA is already snapshotted, compare
  # the manifest perimeter (paths + exclude_paths, set-wise) with the latest
  # revision's .sync-meta.json; a change re-snapshots into <shortsha>-rN.
  if [[ -d "$base_dir" ]]; then
    latest_dir="$base_dir"
    latest_n=1
    for d in "$base_dir"-r*/; do
      [[ -d "$d" ]] || continue
      n="${d%/}"; n="${n##*-r}"
      [[ "$n" =~ ^[0-9]+$ ]] || continue
      if (( 10#$n > 10#$latest_n )); then latest_n="$n"; latest_dir="${d%/}"; fi
    done
    stored_perim="$(jq -c 'if (.paths // null) == null then null else [(.paths | sort), ((.exclude_paths // []) | sort)] end' \
      "$latest_dir/.sync-meta.json" 2>/dev/null || echo null)"
    wanted_perim="$(jq -cn --argjson p "$paths_json" --argjson x "$excludes_json" '[($p | sort), ($x | sort)]')"
    if [[ -z "$stored_perim" || "$stored_perim" == "null" ]]; then
      echo "SKIPPED $name (sha $shortsha already snapshotted)"
      echo "note: $name cannot compare perimeter (no paths in .sync-meta.json)" >&2
      continue
    fi
    if [[ "$stored_perim" == "$wanted_perim" ]]; then
      echo "SKIPPED $name (sha $shortsha already snapshotted)"
      continue
    fi
    rev=$((10#$latest_n + 1))
    snapshot_dir="$base_dir-r$rev"
    echo "note: $name perimeter changed since $shortsha → revision r$rev" >&2
  fi

  clone_dir="$VAULT_ROOT/cache/sync-repos/$name"
  rm -rf "$clone_dir"

  if ! gh repo clone "$repo" "$clone_dir" -- --depth=1 --branch "$branch" --quiet 2>/dev/null; then
    echo "ERROR $name clone failed"
    continue
  fi

  mkdir -p "$snapshot_dir"

  # Copy each listed path (preserves the relative tree)
  copied_any=0
  while IFS= read -r p; do
    [[ -z "$p" ]] && continue
    src="$clone_dir/$p"
    if [[ -e "$src" ]]; then
      # strip trailing slash, recreate the parent on the snapshot side
      p_clean="${p%/}"
      parent_dir="$snapshot_dir/$(dirname "$p_clean")"
      mkdir -p "$parent_dir"
      cp -R "$src" "$snapshot_dir/$p_clean"
      copied_any=1
    fi
  done < <(echo "$paths_json" | jq -r '.[]')

  if [[ "$copied_any" -eq 0 ]]; then
    rm -rf "$snapshot_dir"
    rm -rf "$clone_dir"
    echo "ERROR $name none of the listed paths exist in the repo"
    continue
  fi

  # Exclusions: remove from the snapshot every path listed in exclude_paths (repo-relative)
  while IFS= read -r ex; do
    [[ -z "$ex" ]] && continue
    ex_clean="${ex%/}"
    # guardrail: reject absolute paths or .. traversal
    [[ "$ex_clean" = /* || "$ex_clean" == *..* ]] && { echo "ERROR $name invalid exclude_path: $ex" >&2; continue; }
    rm -rf "$snapshot_dir/$ex_clean"
  done < <(echo "$excludes_json" | jq -r '.[]')

  # Snapshot metadata
  cat > "$snapshot_dir/.sync-meta.json" <<EOF
{
  "name": "$name",
  "repo": "$repo",
  "branch": "$branch",
  "sha": "$sha",
  "shortsha": "$shortsha",
  "synced_at": "$SYNCED_AT",
  "paths": $paths_json,
  "exclude_paths": $excludes_json
}
EOF

  rm -rf "$clone_dir"
  echo "CREATED $dest/$(basename "$snapshot_dir")"
done <<< "$SOURCES"

# Clean up cache dir if empty
rmdir "$VAULT_ROOT/cache/sync-repos" 2>/dev/null || true
