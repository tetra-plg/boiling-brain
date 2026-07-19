#!/usr/bin/env bash
# scan-raw.sh — Détecte l'état de chaque fichier raw vis-à-vis du wiki
#
# Usage:
#   scripts/wiki-maint/scan-raw.sh                   → scanne tout raw/
#   scripts/wiki-maint/scan-raw.sh raw/notes/foo.md  → fichier unique
#   scripts/wiki-maint/scan-raw.sh raw/tracked-repos/ → sous-arbre
#
# Sortie par ligne :
#   NEW      <rel-path>
#   SKIP     <rel-path>   (covered-by: <wiki-source-slug>)
#   MODIFIED <rel-path>   (covered-by: <wiki-source-slug>, sha-changed)
#
# Codes de sortie : 0 = succès, 1 = erreur

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VAULT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WIKI_SOURCES="$VAULT_ROOT/wiki/sources"

# --- Résolution portable de l'interpréteur Python ---
# Sur Windows, l'installeur officiel ne fournit que python.exe (pas
# python3.exe), et le nom nu "python3" peut résoudre vers le stub Microsoft
# Store (présent sur le PATH, mais non fonctionnel). command -v seul ne
# détecte pas ce cas — un auto-test fonctionnel est nécessaire. Ceci doit
# s'exécuter avant toute boucle : un échec de python3 dans _normalize_path()
# est invisible à `set -e` une fois imbriqué dans une substitution de
# commande (path_to_slug["$(_safe_key "$(_normalize_path ...)")"]=...), donc
# c'est le seul point où un abort explicite est fiable.
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  fi
fi
if [ -z "$PYTHON_BIN" ] || ! "$PYTHON_BIN" -c "import unicodedata" >/dev/null 2>&1; then
  echo "ERROR: no functional Python interpreter found (python3/python missing or unusable — Windows Store stub?)." >&2
  echo "       scan-raw.sh depends on it for NFC path normalization. Install Python 3, or set \$PYTHON_BIN." >&2
  exit 1
fi

# All scanning logic lives in scan-raw.py (single process — #70). This wrapper
# only guarantees a working interpreter (Windows-Store-stub safe, #64) then
# hands off. VAULT_ROOT is exported so the engine resolves the vault the same
# way regardless of cwd.
export VAULT_ROOT
exec "$PYTHON_BIN" "$SCRIPT_DIR/scan-raw.py" "$@"
