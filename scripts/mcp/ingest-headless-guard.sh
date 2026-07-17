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
trap 'echo "BLOQUÉ (ingest headless guard) : payload JSON invalide ou erreur interne du hook" >&2; exit 2' ERR

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

    if [[ "$command" == *".."* ]]; then
      deny "commande Bash contenant « .. » (traversal potentiel) : $command"
    fi

    has_shell_metachars() {
      case "$1" in
        *';'*|*'&'*|*'|'*|*'`'*|*'$('*|*$'\n'*|*'<'*|*'>'*) return 0 ;;
        *) return 1 ;;
      esac
    }

    # Base commands: the ENTIRE command must match a pattern where any
    # variable part is restricted to a safe charset (alnum, /, ., -, _) —
    # an allowlist of safe characters, not a denylist of dangerous
    # constructs. A metachar denylist alone is provably incomplete: bash
    # process substitution (<(...)/>(...)) executes a command as a side
    # effect of argument parsing without needing any of ; & | ` $( — a
    # security review found this exact bypass. A charset-anchored regex
    # closes this whole class of bypass by construction instead of
    # enumerating dangerous syntax forms one at a time.
    SAFE_ARG='[A-Za-z0-9_./-]+'
    SCAN_FLAG='(--force|--orphans|--pending|--format=json)'
    if [[ "$command" =~ ^bash\ scripts/wiki-maint/scan-raw\.sh(\ $SCAN_FLAG)*(\ raw(/$SAFE_ARG)?)?$ ]]; then
      exit 0
    fi
    if [[ "$command" =~ ^shasum\ -a\ 256\ raw/$SAFE_ARG$ ]]; then
      exit 0
    fi
    if [[ "$command" =~ ^bash\ scripts/wiki-maint/purge-pending-ingest\.sh(\ $SAFE_ARG)*$ ]]; then
      exit 0
    fi
    if [ "$command" = 'python3 scripts/wiki-maint/format-md.py --write "wiki/**/*.md"' ]; then
      exit 0
    fi

    # Vault-local extension: kept as prefix + metachar-denylist rather than
    # a charset-anchored regex, since the vault owner controls both the
    # prefix list and the trust boundary here (analogous to how they
    # already author their own custom domain-expert agents) — a stricter
    # scheme would need to know each custom command's legitimate argument
    # shape, which this script can't know in advance.
    if [ -f "$LOCAL_ALLOWLIST" ]; then
      while IFS= read -r prefix || [ -n "$prefix" ]; do
        [ -z "$prefix" ] && continue
        case "$command" in
          "$prefix"*)
            if has_shell_metachars "$command"; then
              deny "commande Bash avec métacaractères suspects après un préfixe local autorisé : $command"
            fi
            exit 0
            ;;
        esac
      done < "$LOCAL_ALLOWLIST"
    fi
    deny "commande Bash hors allowlist : $command"
    ;;
  Read|Glob|Grep|Task|TodoWrite)
    exit 0
    ;;
  *)
    deny "outil non explicitement autorisé pendant un run headless : $tool_name"
    ;;
esac
