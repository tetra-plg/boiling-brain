#!/usr/bin/env bash
# setup-mcp.sh — Configure le serveur MCP boiling-brain-wiki et les hooks Claude Code.
#   - Enregistre le serveur MCP via `claude mcp add -s user` (scope user, visible cross-projets)
#   - Ajoute le hook Stop (check-session-activity.sh) dans ~/.claude/settings.json
#   - Ajoute les instructions d'invocation dans ~/.claude/CLAUDE.md
#
# Usage : bash scripts/mcp/setup-mcp.sh [--vault-path /chemin/vers/vault]
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

MCP_SCRIPT="$VAULT_PATH/scripts/mcp/mcp-wiki.py"
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

# --- Installer fastmcp + résoudre l'interpréteur Python qui peut le charger ---
# Priorité : pipx (isolé, propre macOS/Debian PEP 668) → pip --user (pollue moins) → erreur.
# Important : pipx isole fastmcp dans son propre venv ; il faut donc utiliser le python
# de ce venv (pas python3 système) pour invoquer mcp-wiki.py, sinon import fastmcp échoue.

MCP_PYTHON=""

if python3 -c "import fastmcp" 2>/dev/null; then
  # fastmcp déjà importable depuis python3 système (pip install antérieur, environnement géré, etc.)
  MCP_PYTHON="$(command -v python3)"
  echo "✅ fastmcp déjà disponible pour python3 système."
elif command -v pipx &>/dev/null; then
  echo "📦 Installation de fastmcp via pipx…"
  pipx install fastmcp || pipx upgrade fastmcp || true
  PIPX_VENVS="$(pipx environment --value PIPX_LOCAL_VENVS 2>/dev/null || echo "$HOME/.local/pipx/venvs")"
  CANDIDATE="$PIPX_VENVS/fastmcp/bin/python"
  if [[ -x "$CANDIDATE" ]] && "$CANDIDATE" -c "import fastmcp" 2>/dev/null; then
    MCP_PYTHON="$CANDIDATE"
  else
    echo "❌ pipx a installé fastmcp mais le python du venv ($CANDIDATE) n'est pas exploitable." >&2
    exit 1
  fi
else
  echo "📦 pipx introuvable, fallback pip install --user…"
  if python3 -m pip install --user "fastmcp>=2.14" 2>/dev/null; then
    MCP_PYTHON="$(command -v python3)"
  else
    echo "❌ Impossible d'installer fastmcp (pip --user bloqué par PEP 668, pipx absent)." >&2
    echo "   Installe pipx (\`brew install pipx\` ou \`apt install pipx\`) puis relance." >&2
    exit 1
  fi
fi

"$MCP_PYTHON" -c "import fastmcp; print(f'✅ fastmcp {fastmcp.__version__} OK (interpréteur : $MCP_PYTHON)')"

# --- Enregistrer le serveur MCP via claude mcp add (scope user) ---
mkdir -p "$HOME/.claude"

if claude mcp get "$SERVER_NAME" >/dev/null 2>&1; then
  echo "✅ MCP server '$SERVER_NAME' déjà enregistré."
else
  claude mcp add -s user "$SERVER_NAME" \
    -e "WIKI_PATH=$VAULT_PATH" \
    -- "$MCP_PYTHON" "$MCP_SCRIPT"
  echo "✅ MCP server '$SERVER_NAME' enregistré (scope user, interpréteur $MCP_PYTHON)."
fi

# --- Hook Stop dans ~/.claude/settings.json ---
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

chmod +x "$VAULT_PATH/scripts/hooks/check-session-activity.sh"

echo ""
echo "=== Configuration terminée ==="
echo "Redémarre Claude Code pour charger le serveur MCP et les hooks."
echo "Teste avec : /mcp"
