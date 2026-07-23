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
# Post-#42 layout : ce script vit dans scripts/mcp/. La racine du vault est
# donc 2 niveaux au-dessus (../..), pas 1 seul comme avant #42.
VAULT_PATH="${VAULT_PATH:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

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

# --- Append ~/.claude/CLAUDE.md (idempotent via marqueur ; replace if outdated) ---
MARKER="<!-- boiling-brain-wiki-mcp -->"
CLAUDE_MD_BLOCK="$MARKER
## Wiki personnel (boiling-brain-wiki MCP)

Le MCP \`boiling-brain-wiki\` expose le wiki de connaissances personnel de l'utilisateur (concepts, décisions, synthèses, cheatsheets, sources… organisés par domaines).

**Déclencheur** : dès qu'une question peut toucher aux connaissances, projets ou décisions personnels de l'utilisateur (et pas seulement au code du repo courant), consulte le wiki AVANT de répondre de mémoire. Premier appel obligatoire : \`list_domains()\` — c'est lui qui te dit quels domaines existent, ne les devine pas.

**Pattern tiered — toujours dans cet ordre, jamais de dump de domaine :**
1. \`list_domains()\` → domaines existants.
2. \`scan_domain(domain)\` → overview hiérarchique (~1k tokens).
3. \`scan_<type>(domain, query=\"\", top=20)\` → drill-down par type : \`scan_concepts\`, \`scan_entities\`, \`scan_decisions\`, \`scan_syntheses\`, \`scan_cheatsheets\`, \`scan_diagrams\`, \`scan_sources\` (ce dernier REQUIERT une query). Sans query : top N par centralité.
4. \`preview_page(page_path)\` (résumé, ~300 tokens) avant \`read_page(page_path)\` (corps complet).

**Cross-domaine** : \`search_wiki(query, limit=10)\` — full-text cross-type/cross-domain, quand tu ne sais pas dans quel domaine chercher.

**Écriture** : \`drop_to_raw(subfolder, filename, content)\` — dépose un fichier dans raw/ pour ingest (bypass propre du hook protect-raw.sh).
$MARKER"

if [[ -f "$CLAUDE_MD" ]] && grep -qF "$MARKER" "$CLAUDE_MD"; then
  # Marker present — check if the existing block is the current (list_domains-first)
  # version by looking for a distinctive string of the new content.
  if grep -qF "list_domains" "$CLAUDE_MD"; then
    echo "✅ $CLAUDE_MD déjà configuré (marqueur présent, contenu à jour)."
  else
    # Outdated block (pre-#47 5-tool version, or 12-tool version without
    # list_domains-first). Replace in place.
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
print(f"✅ {p} mis à jour (bloc obsolète remplacé par la version list_domains-first + tiered loading).")
PYEOF
  fi
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
