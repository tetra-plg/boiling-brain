#!/usr/bin/env bash
# setup-mcp.sh — Configure le serveur MCP boiling-brain-wiki et les hooks Claude Code.
#   - Enregistre le serveur MCP via `claude mcp add -s user` (scope user, visible cross-projets)
#   - Ajoute le hook Stop (check-session-activity.sh) dans ~/.claude/settings.json
#   - Ajoute les instructions d'invocation dans ~/.claude/CLAUDE.md
#
# Usage : bash scripts/setup-mcp.sh [--vault-path /chemin/vers/vault]
#
# Par défaut, le vault est le répertoire parent de ce script (racine du vault).
# Pré-requis :
#   - Claude Code CLI (`claude`)
#   - Python 3.9+
#   - fastmcp (installé automatiquement via pipx si dispo, sinon pip --user)

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
SERVER_NAME="boiling-brain-wiki"

echo "=== Setup MCP $SERVER_NAME ==="
echo "Vault : $VAULT_PATH"
echo "Script MCP : $MCP_SCRIPT"

# --- Vérifier Python ---
if ! command -v python3 &>/dev/null; then
  echo "❌ python3 introuvable. Installe Python 3.9+." >&2
  exit 1
fi

# --- Vérifier Claude Code CLI ---
if ! command -v claude &>/dev/null; then
  echo "❌ Commande \`claude\` introuvable. Installe Claude Code CLI." >&2
  exit 1
fi

# --- Installer fastmcp (pipx prioritaire, pip --user fallback) ---
if ! python3 -c "import fastmcp" 2>/dev/null; then
  echo "📦 fastmcp non trouvé. Installation…"
  if command -v pipx &>/dev/null; then
    pipx install fastmcp || pipx upgrade fastmcp
  else
    if ! python3 -m pip install --user "fastmcp>=2.14" 2>/dev/null; then
      echo "❌ pip install --user a échoué (probablement PEP 668)." >&2
      echo "   Installe pipx (\`brew install pipx\` ou \`apt install pipx\`) puis relance." >&2
      exit 1
    fi
  fi
fi

python3 -c "import fastmcp; print(f'✅ fastmcp {fastmcp.__version__} OK')"

# --- Enregistrer le serveur MCP via claude mcp add (scope user) ---
mkdir -p "$HOME/.claude"

if claude mcp get "$SERVER_NAME" >/dev/null 2>&1; then
  echo "✅ MCP server '$SERVER_NAME' déjà enregistré."
else
  claude mcp add -s user "$SERVER_NAME" \
    -e "WIKI_PATH=$VAULT_PATH" \
    -- python3 "$MCP_SCRIPT"
  echo "✅ MCP server '$SERVER_NAME' enregistré (scope user)."
fi

# --- Hook Stop dans ~/.claude/settings.json ---
python3 - <<PYEOF
import json
from pathlib import Path

settings_path = Path("$CLAUDE_SETTINGS")
vault_path = "$VAULT_PATH"

if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text())
    except json.JSONDecodeError:
        settings = {}
else:
    settings = {}

hook_script = f"bash {vault_path}/scripts/check-session-activity.sh"
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
    print("✅ Hook Stop enregistré.")
else:
    print("✅ Hook Stop déjà enregistré.")

settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
print(f"✅ {settings_path} mis à jour (hook Stop).")
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
