#!/bin/bash
# purge-pending-ingest.sh — remove the given paths from cache/.pending-ingest.
# Usage: purge-pending-ingest.sh <path1> [path2 ...]
#
# Used by /ingest step 4c to remove processed (NEW+MODIFIED) and stale SKIP
# entries after a run. No-op (exit 0) if there's nothing to purge or the
# pending file doesn't exist. Extracted from an inline multi-line snippet
# into its own script so it can be allowlisted by a single fixed command
# prefix in scripts/mcp/ingest-headless-guard.sh, instead of an
# unsafe-to-match inline heredoc-style command.
#
# Manifest format: one entry per line, `<path>` or `<path><TAB><domain-hint>`
# (the hint is optional, written by drop_to_raw / drop_file_to_raw — #154).
# An entry is removed when its path field equals one of the arguments.
set -euo pipefail

PENDING="cache/.pending-ingest"
[ -f "$PENDING" ] || exit 0
[ "$#" -eq 0 ] && exit 0

printf '%s\n' "$@" \
  | awk -F '\t' 'NR == FNR { drop[$0] = 1; next } !($1 in drop)' - "$PENDING" \
  > "$PENDING.tmp"
mv "$PENDING.tmp" "$PENDING"
[ -s "$PENDING" ] || rm -f "$PENDING"
