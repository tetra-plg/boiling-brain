#!/usr/bin/env bash
# setup-mcp.sh — Configure le serveur MCP boiling-brain-wiki et les hooks Claude Code.
#   - Merge l'entrée MCP dans ~/.claude/settings.json
#   - Ajoute le hook Stop (check-session-activity.sh) dans settings.json
#   - Ajoute les instructions d'invocation dans ~/.claude/CLAUDE.md
#
# Usage : bash scripts/setup-mcp.sh [--vault-path /chemin/vers/vault]
#
# Par défaut, le vault est le répertoire parent de ce script (racine du vault).
# Pré-requis : Python 3 + fastmcp (pip install "fastmcp>=2.14,<3")

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_PATH="${VAULT_PATH:-$(dirname "$SCRIPT_DIR")}"

# --- Parse args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --vault-path) VAULT_PATH="$2"; shift 2 ;;
    *) echo "Usage: $0 [--vault-path /chemin/vers/vault]" >&2; exit 1 ;;
  esac
done

MCP_SCRIPT="$VAULT_PATH/scripts/mcp-wiki.py"
CLAUDE_SETTINGS="$HOME/.claude/settings.json"
CLAUDE_MD="$HOME/.claude/CLAUDE.md"

echo "=== Setup MCP boiling-brain-wiki ==="
echo "Vault : $VAULT_PATH"
echo "Script MCP : $MCP_SCRIPT"

# --- Vérifier Python et fastmcp ---
if ! command -v python3 &>/dev/null; then
  echo "❌ python3 introuvable. Installe Python 3.9+." >&2
  exit 1
fi

if ! python3 -c "import fastmcp" 2>/dev/null; then
  echo "📦 fastmcp non trouvé. Installation en cours…"
  python3 -m pip install --user "fastmcp>=2.14,<3"
fi

python3 -c "import fastmcp; print(f'✅ fastmcp {fastmcp.__version__} OK')"

# --- Merge ~/.claude/settings.json ---
mkdir -p "$HOME/.claude"

python3 - <<PYEOF
import json, sys
from pathlib import Path

settings_path = Path("$CLAUDE_SETTINGS")
vault_path = "$VAULT_PATH"
mcp_script = "$MCP_SCRIPT"

if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text())
    except json.JSONDecodeError:
        settings = {}
else:
    settings = {}

settings.setdefault("mcpServers", {})

settings["mcpServers"]["boiling-brain-wiki"] = {
    "command": "python3",
    "args": [mcp_script],
    "env": {
        "WIKI_PATH": vault_path
    },
    "scope": "user"
}

# Hook Stop : détecte l'activité de session
hook_script = f"bash {vault_path}/scripts/check-session-activity.sh"
settings.setdefault("hooks", {})
settings["hooks"].setdefault("Stop", [])

# Idempotent : n'ajoute pas si déjà présent
existing_stop = settings["hooks"]["Stop"]
already_registered = any(
    (isinstance(h, dict) and hook_script in str(h.get("command", ""))) or
    (isinstance(h, str) and hook_script in h)
    for h in existing_stop
)
if not already_registered:
    existing_stop.append({
        "matcher": "",
        "hooks": [{"type": "command", "command": hook_script}]
    })
    print("✅ Hook Stop enregistré.")
else:
    print("✅ Hook Stop déjà enregistré.")

settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
print(f"✅ {settings_path} mis à jour.")
PYEOF

# --- Append ~/.claude/CLAUDE.md (idempotent via marqueur) ---
MARKER="<!-- boiling-brain-wiki-mcp -->"
CLAUDE_MD_BLOCK="$MARKER
## Wiki personnel (boiling-brain-wiki MCP)

Tu as accès à un serveur MCP \`boiling-brain-wiki\` qui expose le wiki personnel de l'utilisateur.

**Règle d'invocation :** avant de répondre à toute question portant sur les domaines de connaissance de l'utilisateur (poker, ia, factory, metier, tech, astro), appelle **toujours** \`scan_domain\` en premier pour vérifier ce que le wiki contient.

Outils disponibles :
- \`scan_domain(domain)\` — index L0 d'un domaine (à appeler en premier)
- \`preview_page(page_path)\` — frontmatter + summary_l1 d'une page
- \`read_page(page_path)\` — corps complet d'une page
- \`search_wiki(query)\` — recherche full-text dans wiki/
- \`drop_to_raw(subfolder, filename, content)\` — dépose un fichier dans raw/ pour ingest

Domaines disponibles : poker, ia, factory, metier, tech, astro
$MARKER"

if [[ -f "$CLAUDE_MD" ]] && grep -qF "$MARKER" "$CLAUDE_MD"; then
  echo "✅ $CLAUDE_MD déjà configuré (marqueur présent)."
else
  echo "" >> "$CLAUDE_MD"
  echo "$CLAUDE_MD_BLOCK" >> "$CLAUDE_MD"
  echo "✅ $CLAUDE_MD mis à jour."
fi

chmod +x "$VAULT_PATH/scripts/check-session-activity.sh"

echo ""
echo "=== Configuration terminée ==="
echo "Redémarre Claude Code pour charger le serveur MCP et les hooks."
echo "Teste avec : /mcp"
