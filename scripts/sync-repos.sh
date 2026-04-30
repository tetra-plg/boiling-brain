#!/usr/bin/env bash
# Usage:
#   scripts/sync-repos.sh                 # toutes les sources du manifest
#   scripts/sync-repos.sh name1 name2     # seulement ces sources
#
# Pour chaque source :
#   - récupère le SHA du HEAD de la branche via `gh api`
#   - si <dest>/<shortsha>/ existe déjà → SKIPPED
#   - sinon → clone --depth=1, copie les paths listés, écrit .sync-meta.json
#
# Sortie stdout (consommée par le slash command /sync-repos) :
#   CREATED <abs-path>
#   SKIPPED <name> (sha <shortsha> already snapshotted)
#   ERROR <name> <message>

set -euo pipefail

VAULT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$VAULT_ROOT"

MANIFEST="$VAULT_ROOT/tracked-repos.config.json"
[[ -f "$MANIFEST" ]] || { echo "ERROR _manifest tracked-repos.config.json introuvable" >&2; exit 1; }
command -v jq >/dev/null || { echo "ERROR _prereq jq non installé (brew install jq)" >&2; exit 1; }
command -v gh >/dev/null || { echo "ERROR _prereq gh CLI non installé" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "ERROR _prereq gh non authentifié (gh auth login)" >&2; exit 1; }

# --- Parse args ---
NAMES=()
for arg in "$@"; do
  case "$arg" in
    --*)      echo "ERROR _args flag inconnu: $arg" >&2; exit 1 ;;
    *)        NAMES+=("$arg") ;;
  esac
done

# --- Résolution des sources à traiter ---
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
    [[ -z "$line" ]] && { echo "ERROR $name introuvable dans le manifest" >&2; exit 1; }
    FILTERED+="$line"$'\n'
  done
  SOURCES="${FILTERED%$'\n'}"
fi

[[ -z "$SOURCES" ]] && { echo "ERROR _selection aucune source sélectionnée" >&2; exit 1; }

mkdir -p "$VAULT_ROOT/cache/sync-repos"

# --- Traitement ---
SYNCED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

while IFS=$'\t' read -r name repo branch dest paths_json excludes_json; do
  [[ -z "$name" ]] && continue

  sha="$(gh api "repos/$repo/commits/$branch" --jq '.sha' 2>/dev/null)" || {
    echo "ERROR $name échec gh api (repo inaccessible ?)"
    continue
  }
  shortsha="${sha:0:7}"
  snapshot_dir="$VAULT_ROOT/$dest/$shortsha"

  if [[ -d "$snapshot_dir" ]]; then
    echo "SKIPPED $name (sha $shortsha already snapshotted)"
    continue
  fi

  clone_dir="$VAULT_ROOT/cache/sync-repos/$name"
  rm -rf "$clone_dir"

  if ! gh repo clone "$repo" "$clone_dir" -- --depth=1 --branch "$branch" --quiet 2>/dev/null; then
    echo "ERROR $name échec clone"
    continue
  fi

  mkdir -p "$snapshot_dir"

  # Copier chaque path listé (préserve l'arborescence relative)
  copied_any=0
  while IFS= read -r p; do
    [[ -z "$p" ]] && continue
    src="$clone_dir/$p"
    if [[ -e "$src" ]]; then
      # strip trailing slash, recréer le parent côté snapshot
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
    echo "ERROR $name aucun des paths listés n'existe dans le repo"
    continue
  fi

  # Exclusions : supprimer du snapshot chaque chemin listé dans exclude_paths (relatif au repo)
  while IFS= read -r ex; do
    [[ -z "$ex" ]] && continue
    ex_clean="${ex%/}"
    # garde-fou : refuser chemins absolus ou remontée par ..
    [[ "$ex_clean" = /* || "$ex_clean" == *..* ]] && { echo "ERROR $name exclude_path invalide: $ex" >&2; continue; }
    rm -rf "$snapshot_dir/$ex_clean"
  done < <(echo "$excludes_json" | jq -r '.[]')

  # Metadata du snapshot
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
  echo "CREATED $dest/$shortsha"
done <<< "$SOURCES"

# Cleanup cache dir si vide
rmdir "$VAULT_ROOT/cache/sync-repos" 2>/dev/null || true
