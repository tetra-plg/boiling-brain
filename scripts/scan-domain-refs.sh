#!/usr/bin/env bash
# scan-domain-refs.sh — Catégorise chaque référence à un slug de domaine dans le vault
#
# Usage:
#   scripts/scan-domain-refs.sh <slug>
#
# Sortie par ligne (tagué bucket, parseable trivialement par awk/grep) :
#
#   CANONICAL   <path>:<line>   <snippet>                  → 5 déclarations canoniques
#   FRONTMATTER <path>:<line>   <snippet>                  → champ `domains:` dans n'importe quel wiki/**/*.md
#   WIKILINK    <path>:<line>   <snippet>                  → [[domains/<slug>]] sans alias
#   ALIAS       <path>:<line>   <snippet>                  → [[domains/<slug>|Label]]
#   COMPOSED    <path>:<line>   <snippet>                  → slug imbriqué dans un autre slug (foo-<slug>, <slug>-bar)
#   PROSE       <path>:<line>   <snippet>                  → mot dans le corps d'un fichier actif (hors frontmatter/code/wikilink)
#   LOGTAG      <path>:<line>   <snippet>                  → patterns de tagging dans wiki/log.md
#   HIST        <path>:<line>   <snippet>                  → idem WIKILINK/ALIAS/PROSE/LOGTAG mais dans wiki/log|decisions|syntheses|sources
#   DRIFT       <path>:<line>   <snippet>                  → compte numérique en prose ("N domaines", "N expert agents") — indépendant du slug
#
# Codes de sortie : 0 = succès (avec ou sans hits), 1 = erreur d'invocation.
#
# Le script s'exécute toujours dans un vault instancié (cwd = racine vault) ; il
# détermine VAULT_ROOT depuis sa propre localisation. Si lancé depuis un repo
# template (présence de .tpl à la racine), il refuse — le scan n'a de sens que
# sur des fichiers instanciés.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# VAULT_PATH override permet de cibler un autre vault (utile pour les tests
# depuis le repo template avant propagation). Défaut : parent du script
# (= racine vault dans l'usage normal post-/update-vault).
VAULT_ROOT="${VAULT_PATH:-$(cd "$SCRIPT_DIR/.." && pwd)}"

# --- Validation ---

if [ $# -ne 1 ] || [ -z "$1" ]; then
  echo "Usage: $0 <slug>" >&2
  exit 1
fi

SLUG="$1"

if [ -f "$VAULT_ROOT/CLAUDE.md.tpl" ]; then
  echo "ERREUR : ce script s'exécute dans un vault instancié, pas dans le repo template." >&2
  echo "Détecté CLAUDE.md.tpl à la racine de $VAULT_ROOT — abort." >&2
  exit 1
fi

if [ ! -d "$VAULT_ROOT/wiki" ] || [ ! -d "$VAULT_ROOT/.claude" ]; then
  echo "ERREUR : $VAULT_ROOT ne ressemble pas à un vault BoilingBrain (wiki/ ou .claude/ manquant)." >&2
  exit 1
fi

cd "$VAULT_ROOT"

# --- Helpers ---

# Échappe un slug pour usage sûr dans un motif grep -E.
_rx_escape() {
  printf '%s' "$1" | sed 's/[.[\*^$()+?{|]/\\&/g'
}

SLUG_RX="$(_rx_escape "$SLUG")"

# Liste des autres slugs de domaines présents dans le vault (pour disambiguer les composés).
_other_domain_slugs() {
  if [ -d wiki/domains ]; then
    find wiki/domains -maxdepth 1 -type f -name '*.md' -not -name '_*' \
      | while read -r f; do basename "$f" .md; done \
      | grep -vFx "$SLUG" || true
  fi
}

# Paths historiques (préservés par défaut, leur contenu n'est touché qu'avec --include-historical
# ou --purge côté /domain). Une référence trouvée dans un de ces paths est taguée HIST.
_is_historical_path() {
  case "$1" in
    wiki/log.md|wiki/decisions/*|wiki/syntheses/*|wiki/sources/*) return 0 ;;
    *) return 1 ;;
  esac
}

# Émet une ligne formatée : <BUCKET>\t<path>:<line>\t<snippet tronqué à 120 chars>
_emit() {
  local bucket="$1" path="$2" line="$3" snippet="$4"
  # Strip leading/trailing whitespace, normalise tabs.
  snippet="$(printf '%s' "$snippet" | tr '\t' ' ' | sed 's/^[[:space:]]\+//; s/[[:space:]]\+$//')"
  if [ ${#snippet} -gt 120 ]; then
    snippet="${snippet:0:117}..."
  fi
  printf '%-11s %s:%s\t%s\n' "$bucket" "$path" "$line" "$snippet"
}

# --- B1 — CANONICAL ---
# 5 fichiers de déclaration active dans un vault instancié.
# Note : .claude/commands/ingest.md est inclus mais le dispatch est dynamique
# par défaut (cf. confirmation issue #38) — la présence du slug n'y est sûre
# que si un mapping hardcodé existe. On émet quand même la ligne ; /domain
# vérifie ensuite la nature de l'occurrence.

CANONICAL_FILES=(
  "CLAUDE.md"
  "README.md"
  "wiki/index.md"
  "wiki/overview.md"
  ".claude/commands/ingest.md"
)

for f in "${CANONICAL_FILES[@]}"; do
  [ -f "$f" ] || continue
  while IFS=: read -r lineno content; do
    _emit "CANONICAL" "$f" "$lineno" "$content"
  done < <(grep -nE "\b${SLUG_RX}\b" "$f" 2>/dev/null || true)
done

# --- B2 — FRONTMATTER ---
# Scan tous les wiki/**/*.md (y compris historiques — frontmatter est métadonnée,
# pas narratif). Détecte le slug dans une ligne `domains:` ou dans un item de
# liste YAML appartenant à un bloc `domains:`.

_scan_frontmatter() {
  local file="$1"
  local in_fm=0
  local in_domains=0
  local lineno=0
  while IFS= read -r line; do
    lineno=$((lineno + 1))
    # Délimiteur frontmatter (---)
    if [ "$line" = "---" ]; then
      if [ $in_fm -eq 0 ]; then
        in_fm=1
      else
        in_fm=0
        in_domains=0
        return 0
      fi
      continue
    fi
    [ $in_fm -eq 1 ] || continue

    # Ligne `domains:` (scalaire inline, ou ouverture de liste)
    if echo "$line" | grep -qE "^domains:"; then
      in_domains=1
      # Scalaire inline : `domains: [foo, bar]` ou `domains: foo`
      if echo "$line" | grep -qE "\b${SLUG_RX}\b"; then
        _emit "FRONTMATTER" "$file" "$lineno" "$line"
      fi
      continue
    fi

    # À l'intérieur d'un bloc liste `domains:`
    if [ $in_domains -eq 1 ]; then
      # Fin du bloc : ligne non-indentée non-tiret
      if echo "$line" | grep -qE "^[^[:space:]-]"; then
        in_domains=0
        # On retombe sur cette même ligne en tant que clé YAML normale
      else
        # Item de liste
        if echo "$line" | grep -qE "^[[:space:]]*-[[:space:]]*\"?${SLUG_RX}\"?[[:space:]]*$"; then
          _emit "FRONTMATTER" "$file" "$lineno" "$line"
        fi
        continue
      fi
    fi
  done < "$file"
}

while IFS= read -r f; do
  [ -f "$f" ] || continue
  _scan_frontmatter "$f"
done < <(find wiki -type f -name '*.md' -not -path '*worktrees*' | sort)

# --- B3/B4 — WIKILINK et ALIAS ---
# [[domains/<slug>]]  → WIKILINK
# [[domains/<slug>|Label]] → ALIAS
# Historique → HIST

while IFS= read -r line; do
  [ -z "$line" ] && continue
  path="${line%%:*}"
  rest="${line#*:}"
  lineno="${rest%%:*}"
  snippet="${rest#*:}"

  # Détermine si alias (présence de | après le slug dans le wikilink)
  if echo "$snippet" | grep -qE "\[\[domains/${SLUG_RX}\|[^]]+\]\]"; then
    bucket="ALIAS"
  else
    bucket="WIKILINK"
  fi

  if _is_historical_path "$path"; then
    bucket="HIST"
  fi
  _emit "$bucket" "$path" "$lineno" "$snippet"
done < <(grep -rnE --exclude-dir=worktrees "\[\[domains/${SLUG_RX}(\|[^]]+)?\]\]" wiki .claude CLAUDE.md README.md 2>/dev/null || true)

# --- B5 — COMPOSED ---
# Slugs composés : slugs (filenames de pages, identifiants dans des wikilinks,
# chemins source_path raw/) contenant <slug> comme sous-partie hyphénée.
# Ex : equipe-agents-roles-metier, evolution-metier-via-internalisation-ia,
# metier-analysis-silvestre-build-vs-buy.
#
# **Pas** les mots composés en prose comme "non-tech", "dette-technique" — ces
# occurrences-là apparaissent en PROSE.
#
# Trois sources de slugs composés candidats :
#   1. Noms de fichiers wiki/**/*.md contenant <slug>
#   2. Wikilinks [[…<slug>…]] ou [[…<slug>…|…]] (hors [[domains/<slug>…]])
#   3. Valeurs YAML `source_path:` ou items de listes pointant sur raw/…<slug>…
#
# Filtre : si le composé matche exactement un autre domaine connu, skip (ce serait
# alors une occurrence canonique d'un autre domaine).

OTHER_SLUGS="$(_other_domain_slugs)"

_is_other_domain() {
  [ -z "$OTHER_SLUGS" ] && return 1
  printf '%s\n' "$OTHER_SLUGS" | grep -qFx "$1"
}

# Émettre s'il s'agit d'un vrai composé hyphéné du slug (pas du slug seul, pas un autre domaine).
_emit_composed_if_valid() {
  local cand="$1" path="$2" lineno="$3" context="$4"
  # Doit être en kebab-case (a-z0-9 + tirets), contenir le slug avec une frontière `-`.
  case "$cand" in
    "$SLUG") return ;;  # le slug seul n'est pas composé
  esac
  if ! printf '%s' "$cand" | grep -qE "^[a-z0-9][a-z0-9-]*$"; then
    return
  fi
  if ! printf '%s' "$cand" | grep -qE "(-${SLUG_RX}\$|-${SLUG_RX}-|^${SLUG_RX}-)"; then
    return
  fi
  if _is_other_domain "$cand"; then
    return
  fi
  _emit "COMPOSED" "$path" "$lineno" "$cand  in: $context"
}

declare -A composed_seen

# 1. Filenames
while IFS= read -r f; do
  bn="$(basename "$f" .md)"
  key="${f}::${bn}"
  [ -n "${composed_seen[$key]+_}" ] && continue
  composed_seen[$key]=1
  _emit_composed_if_valid "$bn" "$f" "1" "filename"
done < <(find wiki .claude -type f -name "*${SLUG}*.md" -not -path '*worktrees*' 2>/dev/null || true)

# 2. Wikilinks contenant le slug (en sous-partie d'un identifiant en kebab-case)
while IFS= read -r line; do
  [ -z "$line" ] && continue
  path="${line%%:*}"
  rest="${line#*:}"
  lineno="${rest%%:*}"
  snippet="${rest#*:}"
  # Extraire le slug à l'intérieur du wikilink ([[<id>]] ou [[<id>|<label>]])
  ids="$(printf '%s' "$snippet" \
    | grep -oE "\[\[[a-zA-Z0-9_/.-]+(\|[^]]+)?\]\]" \
    | sed -E 's/^\[\[//; s/(\|[^]]+)?\]\]$//' \
    | sed -E 's|^.*/||' \
    | grep -E "${SLUG_RX}" \
    | sort -u || true)"
  while IFS= read -r id; do
    [ -z "$id" ] && continue
    # Skip si c'est exactement le slug canonique (cas [[domains/<slug>]] déjà capturé en WIKILINK)
    [ "$id" = "$SLUG" ] && continue
    key="${path}::${id}"
    [ -n "${composed_seen[$key]+_}" ] && continue
    composed_seen[$key]=1
    _emit_composed_if_valid "$id" "$path" "$lineno" "$snippet"
  done <<< "$ids"
done < <(grep -rnE --exclude-dir=worktrees "\[\[[a-zA-Z0-9_/.-]*${SLUG_RX}[a-zA-Z0-9_/.-]*(\|[^]]+)?\]\]" wiki .claude 2>/dev/null || true)

# 3. source_path / covered_paths YAML pointant sur raw/…<slug>…
while IFS= read -r line; do
  [ -z "$line" ] && continue
  path="${line%%:*}"
  rest="${line#*:}"
  lineno="${rest%%:*}"
  snippet="${rest#*:}"
  # Extraire les chemins raw/… contenant le slug
  paths="$(printf '%s' "$snippet" | grep -oE "raw/[a-zA-Z0-9_/.-]*${SLUG_RX}[a-zA-Z0-9_/.-]*" | sort -u || true)"
  while IFS= read -r p; do
    [ -z "$p" ] && continue
    bn="$(basename "$p" .md)"
    [ "$bn" = "$SLUG" ] && continue
    key="${path}::${bn}"
    [ -n "${composed_seen[$key]+_}" ] && continue
    composed_seen[$key]=1
    _emit_composed_if_valid "$bn" "$path" "$lineno" "raw path: $p"
  done <<< "$paths"
done < <(grep -rnE --exclude-dir=worktrees "raw/[a-zA-Z0-9_/.-]*${SLUG_RX}[a-zA-Z0-9_/.-]*" wiki 2>/dev/null || true)

# --- B6 — PROSE et B7 — LOGTAG et B8 — HIST (corps de fichier) ---
# Pour chaque occurrence du slug dans un fichier (hors frontmatter, hors code-block),
# qui n'est ni un wikilink ni un composé, on tague :
#   - LOGTAG si le path est wiki/log.md ET le motif matche un des patterns connus
#   - HIST si le path est dans wiki/log.md|decisions|syntheses|sources
#   - PROSE sinon

LOGTAG_PATTERNS=(
  "\[${SLUG_RX}\]"
  ", ${SLUG_RX},"
  ", ${SLUG_RX})"
  ", ${SLUG_RX} \("
  "/ ${SLUG_RX} /"
  " ${SLUG_RX} /"
  "/ ${SLUG_RX} "
)

# Scan du corps (hors frontmatter, hors blocs de code) : on saute les lignes
# entre la 1re et la 2e ligne `---` rencontrées et les blocs ```.
# BSD awk (macOS) ne supporte pas \b : on émule la frontière de mot avec
# `(^|[^a-zA-Z0-9_-])SLUG([^a-zA-Z0-9_-]|$)`.
_scan_body() {
  local file="$1"
  awk -v slug="$SLUG" '
    BEGIN { in_fm=0; fm_count=0; in_code=0 }
    /^---$/ {
      if (fm_count == 0) { in_fm=1; fm_count=1; next }
      if (fm_count == 1) { in_fm=0; fm_count=2; next }
    }
    in_fm { next }
    /^```/ { in_code = !in_code; next }
    in_code { next }
    {
      rx = "(^|[^a-zA-Z0-9_-])" slug "([^a-zA-Z0-9_-]|$)"
      if (match($0, rx)) {
        print NR ":" $0
      }
    }
  ' "$file"
}

while IFS= read -r f; do
  [ -f "$f" ] || continue
  [ "$f" = ".claude/commands/ingest.md" ] && continue # déjà couvert par CANONICAL si pertinent
  while IFS=: read -r lineno content; do
    [ -z "$lineno" ] && continue

    # Skip si déjà capturé en WIKILINK/ALIAS (sur cette ligne)
    if echo "$content" | grep -qE "\[\[domains/${SLUG_RX}(\|[^]]+)?\]\]"; then
      # On retire les wikilinks de la ligne pour détecter s'il reste une autre occurrence
      stripped="$(echo "$content" | sed -E "s/\[\[domains\/${SLUG_RX}(\|[^]]+)?\]\]//g")"
      if ! echo "$stripped" | grep -qE "\b${SLUG_RX}\b"; then
        continue
      fi
    fi

    # Skip si toute la ligne est un composé déjà émis (heuristique : aucune occurrence du slug standalone)
    # → on cherche le slug entouré de non-`-` ou en début/fin de mot
    if ! echo "$content" | grep -qE "(^|[^a-z0-9-])${SLUG_RX}([^a-z0-9-]|$)"; then
      continue
    fi

    # Déterminer le bucket
    bucket=""
    # LOGTAG ?
    if [ "$f" = "wiki/log.md" ]; then
      for pat in "${LOGTAG_PATTERNS[@]}"; do
        if echo "$content" | grep -qE "$pat"; then
          bucket="LOGTAG"
          break
        fi
      done
    fi
    # HIST sinon, si path historique
    if [ -z "$bucket" ] && _is_historical_path "$f"; then
      bucket="HIST"
    fi
    # PROSE sinon
    [ -z "$bucket" ] && bucket="PROSE"

    _emit "$bucket" "$f" "$lineno" "$content"
  done < <(_scan_body "$f")
done < <(find wiki .claude -type f -name '*.md' -not -path '*worktrees*' 2>/dev/null | sort)

# --- B9 — DRIFT ---
# Compte numérique en prose : "N domaines", "N agents experts", "N domains", "N expert agents".
# Indépendant du slug. On scanne CLAUDE.md, README.md, wiki/index.md, wiki/overview.md.

DRIFT_TARGETS=(
  "CLAUDE.md"
  "README.md"
  "wiki/index.md"
  "wiki/overview.md"
)

for f in "${DRIFT_TARGETS[@]}"; do
  [ -f "$f" ] || continue
  while IFS=: read -r lineno content; do
    _emit "DRIFT" "$f" "$lineno" "$content"
  done < <(grep -nE "\b[0-9]+\s+(domaines|agents experts|domains|expert agents)\b" "$f" 2>/dev/null || true)
done
