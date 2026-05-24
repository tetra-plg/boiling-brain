#!/usr/bin/env bash
# check-session-activity.sh — Stop hook: detects session activity.
#
# If the session produced commits or modified files in raw/ or wiki/,
# writes cache/.session-pending so the SessionStart hook can propose /compress-bb.
#
# Usage (in ~/.claude/settings.json hooks.Stop):
#   bash /path/to/vault/scripts/check-session-activity.sh
#
# Environment variables:
#   VAULT_PATH — vault directory (default: parent of this script)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_PATH="${VAULT_PATH:-$(dirname "$SCRIPT_DIR")}"
CACHE_DIR="$VAULT_PATH/cache"

mkdir -p "$CACHE_DIR"

HAS_ACTIVITY=0

# Commits within the session window (at least 1 commit in the last 12 hours)
if git -C "$VAULT_PATH" log --since="12 hours ago" --oneline 2>/dev/null | grep -q .; then
  HAS_ACTIVITY=1
fi

# Uncommitted modified files in raw/ or wiki/
if git -C "$VAULT_PATH" status --short 2>/dev/null | grep -qE "^.M (raw|wiki)/"; then
  HAS_ACTIVITY=1
fi

if [ "$HAS_ACTIVITY" -eq 1 ]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$CACHE_DIR/.session-pending"
fi

exit 0
