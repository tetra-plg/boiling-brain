#!/bin/bash
# ingest-headless-guard.sh — PreToolUse hook, scoped via --settings to a
# single headless ingest() MCP tool call (see scripts/mcp/mcp-wiki.py).
# Allowlists exactly the Write/Bash operations the headless /ingest workflow
# performs, so an unattended session (no human to approve tool calls) can't
# be steered outside its intended lane even if manipulated by adversarial
# raw/ content. Applies to both the main context and any spawned subagent
# (Task-tool tool calls share the same hook configuration).
#
# Exit 0 = allow. Exit 2 + message on stderr = deny (same convention as
# .claude/hooks/protect-raw.sh).
#
# VAULT_PATH env var overrides vault-root detection (used by tests); falls
# back to `git rev-parse --show-toplevel`, then cwd — same override
# convention as scripts/hooks/check-session-activity.sh.
#
# Vault-specific extension: an optional
# $VAULT_PATH/.claude/ingest-bash-allowlist.local.txt (one command prefix per
# line, blank lines ignored) adds Bash prefixes beyond this script's
# built-in base set — for a custom domain-expert agent whose Bash needs go
# beyond `shasum`.
set -euo pipefail

VAULT_PATH="${VAULT_PATH:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
LOCAL_ALLOWLIST="$VAULT_PATH/.claude/ingest-bash-allowlist.local.txt"

input=$(cat)

deny() {
  echo "BLOQUÉ (ingest headless guard) : $1" >&2
  exit 2
}

tool_name=$(printf '%s' "$input" | python3 -c "import sys, json; print(json.load(sys.stdin).get('tool_name', ''))")

case "$tool_name" in
  Write|Edit)
    file_path=$(printf '%s' "$input" | python3 -c "import sys, json; print(json.load(sys.stdin).get('tool_input', {}).get('file_path', ''))")
    rel=$(python3 -c "
import os, sys
vault, path = sys.argv[1], sys.argv[2]
try:
    print(os.path.relpath(path, vault))
except Exception:
    print(path)
" "$VAULT_PATH" "$file_path")
    case "$rel" in
      wiki/*.md)
        exit 0 ;;
      .claude/agents/*-expert.suggestions.md)
        exit 0 ;;
      *)
        deny "écriture hors périmètre autorisé : $rel" ;;
    esac
    ;;
  Bash)
    command=$(printf '%s' "$input" | python3 -c "import sys, json; print(json.load(sys.stdin).get('tool_input', {}).get('command', ''))")
    for prefix in \
      'bash scripts/wiki-maint/scan-raw.sh' \
      'shasum -a 256 raw/' \
      'python3 scripts/wiki-maint/format-md.py --write' \
      'PENDING="cache/.pending-ingest"' \
      ; do
      case "$command" in
        "$prefix"*) exit 0 ;;
      esac
    done
    if [ -f "$LOCAL_ALLOWLIST" ]; then
      while IFS= read -r prefix; do
        [ -z "$prefix" ] && continue
        case "$command" in
          "$prefix"*) exit 0 ;;
        esac
      done < "$LOCAL_ALLOWLIST"
    fi
    deny "commande Bash hors allowlist : $command"
    ;;
  *)
    exit 0
    ;;
esac
