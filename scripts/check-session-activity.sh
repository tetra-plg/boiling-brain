#!/usr/bin/env bash
# check-session-activity.sh — Hook Stop : détecte l'activité de la session.
#
# Si la session a produit des commits ou des fichiers modifiés dans raw/ ou wiki/,
# écrit cache/.session-pending pour que le hook SessionStart propose un /compress-bb.
#
# Usage (dans ~/.claude/settings.json hooks.Stop) :
#   bash /chemin/vers/vault/scripts/check-session-activity.sh
#
# Variables d'environnement :
#   VAULT_PATH — chemin du vault (défaut : répertoire parent de ce script)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_PATH="${VAULT_PATH:-$(dirname "$SCRIPT_DIR")}"
CACHE_DIR="$VAULT_PATH/cache"

mkdir -p "$CACHE_DIR"

HAS_ACTIVITY=0

# Commits depuis le début de session (au moins 1 commit dans les 12 dernières heures)
if git -C "$VAULT_PATH" log --since="12 hours ago" --oneline 2>/dev/null | grep -q .; then
  HAS_ACTIVITY=1
fi

# Fichiers modifiés dans raw/ ou wiki/ (non commités)
if git -C "$VAULT_PATH" status --short 2>/dev/null | grep -qE "^.M (raw|wiki)/"; then
  HAS_ACTIVITY=1
fi

if [ "$HAS_ACTIVITY" -eq 1 ]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$CACHE_DIR/.session-pending"
fi

exit 0
