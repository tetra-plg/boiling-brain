#!/usr/bin/env bash
# test-scan-raw.sh — Vérifie que scan-raw.sh gère correctement les caractères
# spéciaux dans les chemins (apostrophes, parenthèses, espaces multiples).
#
# Usage:
#   bash scripts/test-scan-raw.sh
#
# Codes de sortie : 0 = tous les cas SKIP, 1 = au moins un cas en NEW (régression).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCAN_RAW="$SCRIPT_DIR/scan-raw.sh"

# --- Préparation d'un vault temporaire avec fichiers raw piégés ---

TESTDIR=$(mktemp -d /tmp/test-scan-raw.XXXXXX)
trap 'rm -rf "$TESTDIR"' EXIT

mkdir -p "$TESTDIR/raw/notes" "$TESTDIR/wiki/sources"

# Fichier 1 : apostrophe dans le nom (cas réel BB : `2026-01-30-claude-code-obsidian-cpr.md`
# qui mentionnait `BotFather to 'Hello'` dans son source_path original)
APOSTROPHE_FILE="$TESTDIR/raw/notes/2026-01-30-claude's-note.md"
echo "Note avec apostrophe dans le nom" > "$APOSTROPHE_FILE"

# Fichier 2 : parenthèses dans le nom
PARENS_FILE="$TESTDIR/raw/notes/foo (bar).md"
echo "Note avec parenthèses dans le nom" > "$PARENS_FILE"

# Fichier 3 : espaces multiples dans le nom
SPACES_FILE="$TESTDIR/raw/notes/multi  space.md"
echo "Note avec doubles espaces dans le nom" > "$SPACES_FILE"

# Fichier 4 : caractères composés (parenthèses + apostrophe)
COMBO_FILE="$TESTDIR/raw/notes/it's (composite).md"
echo "Note combinant apostrophe et parenthèses" > "$COMBO_FILE"

# Calcul du sha256 de chaque fichier
APOSTROPHE_SHA=$(sha256sum "$APOSTROPHE_FILE" | cut -d' ' -f1)
PARENS_SHA=$(sha256sum "$PARENS_FILE" | cut -d' ' -f1)
SPACES_SHA=$(sha256sum "$SPACES_FILE" | cut -d' ' -f1)
COMBO_SHA=$(sha256sum "$COMBO_FILE" | cut -d' ' -f1)

# Page wiki qui couvre les 4 raw via source_path (scalaire) + covered_paths (liste)
cat > "$TESTDIR/wiki/sources/2026-05-01-trapped-paths.md" <<EOF
---
type: source
source_path: "raw/notes/2026-01-30-claude's-note.md"
source_sha256: $APOSTROPHE_SHA
covered_paths:
  - "raw/notes/foo (bar).md"
  - "raw/notes/multi  space.md"
  - "raw/notes/it's (composite).md"
created: 2026-05-01
updated: 2026-05-01
---

# Trapped paths — fixture pour test-scan-raw.sh
EOF

# --- Exécution du scan ---

# scan-raw.sh attend un layout vault avec wiki/sources et raw/ relatif au script.
# On copie le script dans le testdir et on l'exécute depuis là.
mkdir -p "$TESTDIR/scripts"
cp "$SCAN_RAW" "$TESTDIR/scripts/scan-raw.sh"

# Le script utilise SCRIPT_DIR/.. comme VAULT_ROOT.
output=$(bash "$TESTDIR/scripts/scan-raw.sh" 2>&1)

echo "=== Sortie du scan ==="
echo "$output"
echo ""

# --- Vérifications ---

errors=0

check_skip() {
  local pattern="$1"
  local label="$2"
  if echo "$output" | grep -qE "^SKIP\s+.*${pattern}"; then
    echo "✅ $label : SKIP"
  else
    echo "❌ $label : devrait être SKIP, vérifie la sortie"
    errors=$((errors + 1))
  fi
}

# Bug 1 — apostrophe (source_path scalaire)
check_skip "claude.s-note" "Bug 1 (apostrophe, source_path)"

# Bug 2 — parenthèses (covered_paths liste)
check_skip "foo \(bar\)" "Bug 2 (parenthèses, covered_paths)"

# Bug 3 — espaces multiples (covered_paths liste)
check_skip "multi  space" "Bug 3 (espaces multiples, covered_paths)"

# Cas combiné (apostrophe + parenthèses)
check_skip "it.s \(composite\)" "Cas combiné (apostrophe + parenthèses)"

# Vérification : aucun NEW dans la sortie
if echo "$output" | grep -qE "^NEW\s+raw/notes"; then
  echo "❌ Au moins un fichier reporté NEW alors qu'il devrait être SKIP :"
  echo "$output" | grep "^NEW"
  errors=$((errors + 1))
fi

if [ "$errors" -eq 0 ]; then
  echo ""
  echo "🎉 Tous les cas reportent correctement SKIP."
  exit 0
else
  echo ""
  echo "❌ $errors erreur(s) détectée(s)."
  exit 1
fi
