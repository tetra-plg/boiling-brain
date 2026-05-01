#!/usr/bin/env bash
# scan-raw.sh — Détecte l'état de chaque fichier raw vis-à-vis du wiki
#
# Usage:
#   scripts/scan-raw.sh                   → scanne tout raw/
#   scripts/scan-raw.sh raw/notes/foo.md  → fichier unique
#   scripts/scan-raw.sh raw/tracked-repos/ → sous-arbre
#
# Sortie par ligne :
#   NEW      <rel-path>
#   SKIP     <rel-path>   (covered-by: <wiki-source-slug>)
#   MODIFIED <rel-path>   (covered-by: <wiki-source-slug>, sha-changed)
#
# Codes de sortie : 0 = succès, 1 = erreur

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VAULT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WIKI_SOURCES="$VAULT_ROOT/wiki/sources"

# --- Collecte des fichiers à analyser ---

args=("$@")
files=()

_scan_find() {
  find "$1" -type f \
    | grep -v "\.sync-meta\.json$" \
    | grep -vE "\.(png|jpg|jpeg|gif|m4a|mp4|wav|webp|pdf)$" \
    | sed 's|//|/|g' \
    | sort
}

if [ ${#args[@]} -eq 0 ]; then
  mapfile -t files < <(_scan_find "$VAULT_ROOT/raw")
else
  for arg in "${args[@]}"; do
    abs="$VAULT_ROOT/$arg"
    # Accepte aussi un chemin absolu passé directement
    [[ "$arg" = /* ]] && abs="$arg"
    # Normalise les slashes multiples et le slash final
    abs=$(echo "$abs" | tr -s '/' | sed 's|/$||')
    if [ -f "$abs" ]; then
      files+=("$abs")
    elif [ -d "$abs" ]; then
      mapfile -t found < <(_scan_find "$abs")
      files+=("${found[@]}")
    else
      echo "WARN: chemin introuvable : $arg" >&2
    fi
  done
fi

if [ ${#files[@]} -eq 0 ]; then
  echo "Aucun fichier à analyser." >&2
  exit 0
fi

# --- Encodage des clés d'array associatif ---
# Les arrays associatifs bash mishandlent les caractères spéciaux dans les clés
# (parenthèses, globs, espaces multiples, etc.). printf %q neutralise toute
# la classe de bugs de quoting en encodant la clé une fois pour toutes.
_safe_key() {
  printf '%q' "$1"
}

# --- Construction de l'index : raw_path → (slug, sha256) ---
# Charge une fois tous les wiki/sources pour éviter O(N×M) grep

declare -A path_to_slug   # safe_key(raw_path) → slug
declare -A path_to_sha    # safe_key(raw_path) → source_sha256 stocké dans la page
declare -a indexed_paths  # paths originaux (pour itération — les clés encodées de path_to_slug ne le permettent pas)

while IFS= read -r source_file; do
  slug=$(basename "$source_file" .md)

  # Lecture des champs source_path et covered_paths avec gestion des deux formats :
  #   - Scalaire : source_path: raw/foo.md
  #   - Liste YAML : source_path:\n  - raw/foo.md\n  - raw/bar.md
  # Les items de source_path (liste) ET de covered_paths sont tous indexés.
  in_sp=0
  in_covered=0
  first_sp=""
  while IFS= read -r line; do
    # Début source_path
    if echo "$line" | grep -q "^source_path:"; then
      val=$(echo "$line" | sed 's/^source_path:[[:space:]]*//' | sed 's/^"//; s/"$//')
      if [ -n "$val" ]; then
        # Scalaire
        path_to_slug["$(_safe_key "$val")"]="$slug"
        indexed_paths+=("$val")
        [ -z "$first_sp" ] && first_sp="$val"
        in_sp=0
      else
        # Liste à venir
        in_sp=1
      fi
      in_covered=0
      continue
    fi
    # Début covered_paths
    if echo "$line" | grep -q "^covered_paths:"; then
      in_sp=0
      in_covered=1
      continue
    fi
    # Items de liste (source_path ou covered_paths)
    if [ $in_sp -eq 1 ] || [ $in_covered -eq 1 ]; then
      if echo "$line" | grep -qE "^[^[:space:]-]"; then
        # Fin de bloc
        in_sp=0
        in_covered=0
        continue
      fi
      item=$(echo "$line" | sed 's/^[[:space:]]*-[[:space:]]*//' | sed 's/^"//; s/"$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
      if [ -n "$item" ]; then
        path_to_slug["$(_safe_key "$item")"]="$slug"
        indexed_paths+=("$item")
        [ $in_sp -eq 1 ] && [ -z "$first_sp" ] && first_sp="$item"
      fi
    fi
  done < "$source_file"

  # sources: — champ legacy, traité comme covered_paths supplémentaires
  in_sources=0
  while IFS= read -r line; do
    if echo "$line" | grep -q "^sources:"; then
      in_sources=1
      continue
    fi
    if [ $in_sources -eq 1 ]; then
      if echo "$line" | grep -qE "^[^[:space:]-]"; then
        in_sources=0
        continue
      fi
      item=$(echo "$line" | sed 's/^[[:space:]]*-[[:space:]]*//' | sed 's/^"//; s/"$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
      if [ -n "$item" ]; then
        path_to_slug["$(_safe_key "$item")"]="$slug"
        indexed_paths+=("$item")
      fi
    fi
  done < "$source_file"

  # SHA stocké (uniquement pour le premier source_path scalaire)
  if [ -n "$first_sp" ]; then
    sha_line=$(grep "^source_sha256:" "$source_file" 2>/dev/null | head -1 | sed 's/^source_sha256:[[:space:]]*//')
    # Ignore si c'est aussi une liste YAML (commence par vide → valeur vide)
    if [ -n "$sha_line" ] && [[ "$sha_line" != -* ]]; then
      path_to_sha["$(_safe_key "$first_sp")"]="$sha_line"
    fi
  fi

done < <(find "$WIKI_SOURCES" -name "*.md" -type f)

# --- Index secondaire : répertoires couverts implicitement ---
# Pour chaque source_path indexé, on note son répertoire parent → slug
# Cela permet de SKIP un fichier si un autre fichier du même dossier est déjà couvert.

declare -A dir_to_slug   # safe_key(raw/foo/bar/) → slug (premier slug rencontré pour ce dossier)
declare -A meta_to_slug  # safe_key(raw/videos-meta/SLUG.meta.md) → slug via transcript

for indexed_path in "${indexed_paths[@]}"; do
  [ -z "$indexed_path" ] && continue
  ip_key=$(_safe_key "$indexed_path")

  # Index des répertoires implicites (≥4 niveaux de profondeur requis)
  idir="${indexed_path%/*}/"
  idir_key=$(_safe_key "$idir")
  depth=$(printf '%s' "$idir" | tr -cd '/' | wc -c | tr -d ' ')
  if [ "$depth" -ge 4 ] && [ -z "${dir_to_slug[$idir_key]+_}" ]; then
    dir_to_slug["$idir_key"]="${path_to_slug[$ip_key]}"
  fi

  # Index videos-meta → transcript
  if [[ "$indexed_path" == raw/transcripts/* ]]; then
    filename="${indexed_path##*/}"
    filename="${filename%.md}"
    meta_path="raw/videos-meta/${filename}.meta.md"
    meta_key=$(_safe_key "$meta_path")
    [ -z "${meta_to_slug[$meta_key]+_}" ] && meta_to_slug["$meta_key"]="${path_to_slug[$ip_key]}"
  fi
done

# --- Analyse de chaque fichier ---

for abs_path in "${files[@]}"; do
  # Chemin relatif depuis la racine du vault
  rel="${abs_path#$VAULT_ROOT/}"
  rel_key=$(_safe_key "$rel")

  # 1. Match exact sur source_path ou covered_paths
  if [ -n "${path_to_slug[$rel_key]+_}" ]; then
    slug="${path_to_slug[$rel_key]}"
    stored_sha="${path_to_sha[$rel_key]:-}"
    if [ -n "$stored_sha" ]; then
      current_sha=$(sha256sum "$abs_path" 2>/dev/null | cut -d' ' -f1)
      if [ "$current_sha" != "$stored_sha" ]; then
        echo "MODIFIED $rel  (covered-by: $slug, sha-changed)"
        continue
      fi
    fi
    echo "SKIP     $rel  (covered-by: $slug)"
    continue
  fi

  # 2. Match sur un répertoire parent (covered_paths avec trailing slash explicite)
  parent="$rel"
  covered=""
  while true; do
    parent=$(dirname "$parent")
    [ "$parent" = "." ] || [ "$parent" = "raw" ] || [ "$parent" = "" ] && break
    parent_slash="${parent}/"
    parent_key=$(_safe_key "$parent_slash")
    if [ -n "${path_to_slug[$parent_key]+_}" ]; then
      covered="${path_to_slug[$parent_key]}"
      break
    fi
  done

  if [ -n "$covered" ]; then
    echo "SKIP     $rel  (covered-by-dir: $covered)"
    continue
  fi

  # 3. Match implicite : même répertoire qu'un fichier déjà indexé (≥4 niveaux de profondeur)
  rel_dir="$(dirname "$rel")/"
  rel_dir_key=$(_safe_key "$rel_dir")
  if [ -n "${dir_to_slug[$rel_dir_key]+_}" ]; then
    echo "SKIP     $rel  (covered-by-dir-implicit: ${dir_to_slug[$rel_dir_key]})"
    continue
  fi

  # 4. Correspondance videos-meta → transcript déjà ingéré
  if [ -n "${meta_to_slug[$rel_key]+_}" ]; then
    echo "SKIP     $rel  (covered-by-transcript: ${meta_to_slug[$rel_key]})"
    continue
  fi

  echo "NEW      $rel"
done
