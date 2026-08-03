#!/usr/bin/env bash
# convert-doc.sh — produce a markdown twin of an office document sitting in raw/.
#
# Usage:
#   bash scripts/convert-doc.sh raw/<subfolder>/<file>.docx
#   bash scripts/convert-doc.sh raw/<subfolder>/<file>.pptx
#
# Writes the twin next to the original, keeping the original extension in the
# name (raw/notes/brief.docx -> raw/notes/brief.docx.md). The original stays in
# raw/, hash-indexed: it remains the archived source of truth, the twin is only
# what the ingestion agent can actually read. This is the same pattern as video
# transcripts, applied to formats no LLM reads natively.
#
# The twin is NEVER overwritten (raw/ is immutable). Re-running on an already
# converted document is a no-op that still prints the twin's path, so /ingest
# can chain on it unconditionally.
#
# Stdout: the vault-relative path of the twin (the only thing on stdout).
# Exit codes:
#   0  twin available (freshly converted, or already present)
#   1  usage error: bad argument, missing file, unsupported extension
#   2  pandoc missing, or too old for the requested format
#   3  conversion failed
#
# Requires pandoc (https://pandoc.org). pptx input needs pandoc >= 3.0; docx
# input works on any 2.x/3.x. VAULT_PATH overrides vault-root detection (same
# convention as scripts/mcp/ingest-headless-guard.sh).
set -euo pipefail

VAULT_PATH="${VAULT_PATH:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

die() { printf '%s\n' "$1" >&2; exit "$2"; }

[ "$#" -eq 1 ] || die "Usage: bash scripts/convert-doc.sh raw/<subfolder>/<file>.docx|.pptx" 1

rel="$1"
case "$rel" in
  raw/*) ;;
  *) die "convert-doc: path must be inside raw/ (got: $rel)" 1 ;;
esac
case "$rel" in
  *..*) die "convert-doc: path must not contain \"..\" (got: $rel)" 1 ;;
esac

src="$VAULT_PATH/$rel"
[ -f "$src" ] || die "convert-doc: file not found: $rel" 1

ext="${rel##*.}"
ext=$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')
case "$ext" in
  docx|pptx) ;;
  *) die "convert-doc: unsupported extension \".$ext\" — expected .docx or .pptx" 1 ;;
esac

twin="${rel}.md"
if [ -e "$VAULT_PATH/$twin" ]; then
  printf 'convert-doc: twin already present, left untouched (raw/ is immutable)\n' >&2
  printf '%s\n' "$twin"
  exit 0
fi

command -v pandoc >/dev/null 2>&1 || die \
  "convert-doc: pandoc not found. Install it once on this machine (macOS: brew install pandoc; Debian/Ubuntu: apt install pandoc; https://pandoc.org/installing.html), then re-run /ingest." 2

# `pandoc --version` prints "pandoc X.Y.Z" on its first line. awk (not head) so
# `set -o pipefail` doesn't trip on the SIGPIPE head would send.
pandoc_major=$(pandoc --version | awk 'NR==1 {split($2, v, "."); print v[1]; exit}')
if [ "$ext" = "pptx" ] && [ "${pandoc_major:-0}" -lt 3 ]; then
  die "convert-doc: pptx input requires pandoc >= 3.0 (found $(pandoc --version | awk 'NR==1 {print $2; exit}')). docx conversion still works; upgrade pandoc for pptx." 2
fi

# --wrap=none keeps one source paragraph on one line (diff-friendly, and the
# ingestion agent quotes cleanly). Embedded media are not extracted: the twin
# exists to carry the *text* to the agent, and the visual pipeline already has
# its own path (frame requests). Image references in the twin may therefore
# point at media that were never written out.
if ! pandoc --from="$ext" --to=gfm --wrap=none -o "$VAULT_PATH/$twin" "$src" 2>/dev/null; then
  rm -f "$VAULT_PATH/$twin"
  die "convert-doc: pandoc failed to convert $rel" 3
fi

printf '%s\n' "$twin"
