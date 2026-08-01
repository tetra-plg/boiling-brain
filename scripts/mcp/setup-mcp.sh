#!/usr/bin/env bash
# setup-mcp.sh — Configure the boiling-brain-wiki MCP server and the Claude Code hooks.
#   - Registers the MCP server via `claude mcp add -s user` (user scope, visible cross-project)
#   - Adds the Stop hook (check-session-activity.sh) to ~/.claude/settings.json
#   - Adds the invocation instructions to ~/.claude/CLAUDE.md
#
# Usage: bash scripts/mcp/setup-mcp.sh [--vault-path /path/to/vault]
#
# By default, the vault is this script's parent directory (the vault root).
# Requirements:
#   - Claude Code CLI (`claude`)
#   - Python 3.9+
#   - fastmcp (installed automatically via pipx if available, otherwise pip --user)
#   - For headless / scriptable access without an MCP client, use wiki-cli.py
#     (same query layer via wiki_core, no fastmcp dependency):
#       python3 scripts/mcp/wiki-cli.py search "<query>" --json

set -euo pipefail

# Force UTF-8 on this script's Python subprocesses' stdio: several `python -c` / heredoc
# blocks below print status emoji (✅). On a Windows console (cp1252) with PYTHONUTF8
# unset, Python would encode stdout with the locale code page and crash with
# UnicodeEncodeError. Setting PYTHONIOENCODING here is inherited by every python child and
# overrides the console code page. Same root cause as #60 (format-md.py). (#69)
export PYTHONIOENCODING=utf-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Post-#42 layout: this script lives in scripts/mcp/. The vault root is
# therefore 2 levels up (../..), not just 1 as before #42.
VAULT_PATH="${VAULT_PATH:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

# --- Parse args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --vault-path) VAULT_PATH="$2"; shift 2 ;;
    *) echo "Usage: $0 [--vault-path /path/to/vault]" >&2; exit 1 ;;
  esac
done

MCP_SCRIPT="$VAULT_PATH/scripts/mcp/mcp-wiki.py"
CLAUDE_SETTINGS="$HOME/.claude/settings.json"
CLAUDE_MD="$HOME/.claude/CLAUDE.md"
SERVER_NAME="boiling-brain-wiki"

echo "=== Setup MCP $SERVER_NAME ==="
echo "Vault: $VAULT_PATH"
echo "MCP script: $MCP_SCRIPT"

# --- Check Python ---
if ! command -v python3 &>/dev/null; then
  echo "❌ python3 not found. Install Python 3.9+." >&2
  exit 1
fi

# --- Check Claude Code CLI ---
if ! command -v claude &>/dev/null; then
  echo "❌ \`claude\` command not found. Install the Claude Code CLI." >&2
  exit 1
fi

# --- Install fastmcp + resolve the Python interpreter that can load it ---
# Priority: pipx (isolated, clean on macOS/Debian PEP 668) → pip --user (less polluting) → error.
# Important: pipx isolates fastmcp in its own venv; you must therefore use that venv's
# python (not the system python3) to invoke mcp-wiki.py, otherwise import fastmcp fails.

MCP_PYTHON=""

if python3 -c "import fastmcp" 2>/dev/null; then
  # fastmcp already importable from the system python3 (prior pip install, managed env, etc.)
  MCP_PYTHON="$(command -v python3)"
  echo "✅ fastmcp already available for the system python3."
elif command -v pipx &>/dev/null; then
  echo "📦 Installing fastmcp via pipx…"
  pipx install fastmcp || pipx upgrade fastmcp || true
  PIPX_VENVS="$(pipx environment --value PIPX_LOCAL_VENVS 2>/dev/null || echo "$HOME/.local/pipx/venvs")"
  CANDIDATE="$PIPX_VENVS/fastmcp/bin/python"
  if [[ -x "$CANDIDATE" ]] && "$CANDIDATE" -c "import fastmcp" 2>/dev/null; then
    MCP_PYTHON="$CANDIDATE"
  else
    echo "❌ pipx installed fastmcp but the venv python ($CANDIDATE) is not usable." >&2
    exit 1
  fi
else
  echo "📦 pipx not found, falling back to pip install --user…"
  if python3 -m pip install --user "fastmcp>=2.14" 2>/dev/null; then
    MCP_PYTHON="$(command -v python3)"
  else
    echo "❌ Cannot install fastmcp (pip --user blocked by PEP 668, pipx missing)." >&2
    echo "   Install pipx (\`brew install pipx\` or \`apt install pipx\`) then re-run." >&2
    exit 1
  fi
fi

"$MCP_PYTHON" -c "import fastmcp; print(f'✅ fastmcp {fastmcp.__version__} OK (interpreter: $MCP_PYTHON)')"

# --- Register the MCP server via claude mcp add (user scope) ---
mkdir -p "$HOME/.claude"

if claude mcp get "$SERVER_NAME" >/dev/null 2>&1; then
  echo "✅ MCP server '$SERVER_NAME' already registered."
else
  claude mcp add -s user "$SERVER_NAME" \
    -e "WIKI_PATH=$VAULT_PATH" \
    -- "$MCP_PYTHON" "$MCP_SCRIPT"
  echo "✅ MCP server '$SERVER_NAME' registered (user scope, interpreter $MCP_PYTHON)."
fi

# --- Stop hook in ~/.claude/settings.json ---
CLAUDE_SETTINGS="$CLAUDE_SETTINGS" VAULT_PATH="$VAULT_PATH" python3 - <<'PYEOF'
import json
import os
from pathlib import Path

settings_path = Path(os.environ["CLAUDE_SETTINGS"])
vault_path = os.environ["VAULT_PATH"]

if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text())
    except json.JSONDecodeError:
        settings = {}
else:
    settings = {}

hook_script = f"bash {vault_path}/scripts/hooks/check-session-activity.sh"
settings.setdefault("hooks", {})
settings["hooks"].setdefault("Stop", [])

existing_stop = settings["hooks"]["Stop"]
already_registered = any(
    (isinstance(h, dict) and hook_script in str(h.get("command", "")))
    or any(
        isinstance(sub, dict) and hook_script in str(sub.get("command", ""))
        for sub in (h.get("hooks", []) if isinstance(h, dict) else [])
    )
    or (isinstance(h, str) and hook_script in h)
    for h in existing_stop
)
if not already_registered:
    existing_stop.append({
        "matcher": "",
        "hooks": [{"type": "command", "command": hook_script}]
    })
    print("✅ Stop hook registered.")
else:
    print("✅ Stop hook already registered.")

settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
print(f"✅ {settings_path} updated (Stop hook).")
PYEOF

# --- Append ~/.claude/CLAUDE.md (idempotent via marker; replace if outdated) ---
MARKER="<!-- boiling-brain-wiki-mcp -->"
CLAUDE_MD_BLOCK="$MARKER
## Personal wiki (boiling-brain-wiki MCP)

The \`boiling-brain-wiki\` MCP exposes the user's personal knowledge wiki (concepts, decisions, syntheses, cheatsheets, sources… organised by domain).

**Trigger**: whenever a question may touch the user's personal knowledge, projects or decisions (not just the current repo's code), consult the wiki BEFORE answering from memory. Mandatory first call: \`list_domains()\` — it tells you which domains exist; never guess them.

**Tiered pattern — always in this order, never a full domain dump:**
1. \`list_domains()\` → existing domains.
2. \`scan_domain(domain)\` → hierarchical overview (~1k tokens).
3. \`scan_<type>(domain, query=\"\", top=20)\` → per-type drill-down: \`scan_concepts\`, \`scan_entities\`, \`scan_decisions\`, \`scan_syntheses\`, \`scan_cheatsheets\`, \`scan_diagrams\`, \`scan_sources\` (this last one REQUIRES a query). Without a query: top N by centrality.
4. \`preview_page(page_path)\` (summary, ~300 tokens) before \`read_page(page_path)\` (full body).

**Cross-domain**: \`search_wiki(query, limit=10)\` — full-text cross-type/cross-domain, when you don't know which domain to look in.

**Writing**: \`drop_to_raw(subfolder, filename, content)\` — drops a text file into raw/ for ingest (clean bypass of the protect-raw.sh hook). \`drop_file_to_raw(source_path, subfolder)\` — same, for a binary already on disk (PDF, image, docx/pptx, audio/video): the server copies it server-side. Source must sit under an allowed root (\$HOME by default, LLMWIKI_DROP_SOURCE_ROOTS to override).

**Async ingestion**: \`ingest_start(path, domain_hint=\"\")\` → job id (non-blocking — survives MCP client tool-call timeouts), then \`ingest_status(job_id)\` to poll (returns the final ingest report), \`ingest_cancel(job_id)\` to abort. One job at a time; the sync \`ingest(path)\` remains for short runs.
$MARKER"

if [[ -f "$CLAUDE_MD" ]] && grep -qF "$MARKER" "$CLAUDE_MD"; then
  # Marker present — check if the existing block is the current version by
  # looking for a distinctive string of the *newest* content. The probe must
  # move with every content revision: probing for an older marker string
  # (e.g. "list_domains" since v1.2.1, "drop_file_to_raw" since v1.3.0)
  # makes every already-updated vault look current and silently freezes the
  # block. (#112)
  if grep -qF "ingest_start" "$CLAUDE_MD"; then
    echo "✅ $CLAUDE_MD already configured (marker present, content up to date)."
  else
    # Outdated block (pre-#47 5-tool version, 12-tool version without
    # list_domains-first, 14-tool version without drop_file_to_raw, or
    # 15-tool version without the async ingestion tools).
    # Replace in place.
    CLAUDE_MD="$CLAUDE_MD" python3 - <<PYEOF
import os, re, pathlib
p = pathlib.Path(os.environ["CLAUDE_MD"])
content = p.read_text(encoding="utf-8")
marker = "<!-- boiling-brain-wiki-mcp -->"
new_block = """$CLAUDE_MD_BLOCK"""
# Replace everything between (and including) the two markers, on first match.
pattern = re.compile(re.escape(marker) + r".*?" + re.escape(marker), re.DOTALL)
new_content, n = pattern.subn(lambda m: new_block, content, count=1)
if n == 0:
    # Shouldn't happen (grep above confirmed marker presence) but fallback safely.
    new_content = content.rstrip() + "\n\n" + new_block + "\n"
p.write_text(new_content, encoding="utf-8")
print(f"✅ {p} updated (outdated block replaced with the list_domains-first + tiered-loading version).")
PYEOF
  fi
else
  echo "" >> "$CLAUDE_MD"
  echo "$CLAUDE_MD_BLOCK" >> "$CLAUDE_MD"
  echo "✅ $CLAUDE_MD updated."
fi

chmod +x "$VAULT_PATH/scripts/hooks/check-session-activity.sh"

echo ""
echo "=== Configuration complete ==="
echo "Restart Claude Code to load the MCP server and hooks."
echo "Test with: /mcp"
