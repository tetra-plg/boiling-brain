#!/usr/bin/env bash
# Usage:
#   scripts/sample-frames.sh <video_path> <output_dir> [cadence_seconds]
#
# Produit:
#   <output_dir>/sample-NNNN.png  (1280×720, échantillonnés toutes [cadence] secondes)
#   <output_dir>/.cadence         (mémorise la cadence utilisée pour diff-frames.py)
#
# Étape 1 du runbook wiki/decisions/extraction-frames-induction-runbook.md.
# Pour pointer vers un cache vidéo externe, exporter $LLMWIKI_VIDEO_CACHE avant l'appel.

set -euo pipefail

VIDEO="${1:?Usage: sample-frames.sh <video_path> <output_dir> [cadence_seconds]}"
OUTPUT_DIR="${2:?Usage: sample-frames.sh <video_path> <output_dir> [cadence_seconds]}"
CADENCE="${3:-20}"

[[ -f "$VIDEO" ]] || { echo "❌ Vidéo introuvable: $VIDEO"; exit 1; }

mkdir -p "$OUTPUT_DIR"

DURATION_S="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$VIDEO" | awk '{printf "%d", $1}')"
DURATION_FMT="$(printf '%dm%02ds' $((DURATION_S/60)) $((DURATION_S%60)))"

echo "→ Vidéo: $VIDEO"
echo "→ Durée: $DURATION_FMT (${DURATION_S}s)"
echo "→ Cadence: 1 sample / ${CADENCE}s"
echo "→ Output: $OUTPUT_DIR"

ffmpeg -nostdin -loglevel error -y -i "$VIDEO" \
  -vf "fps=1/${CADENCE},scale=1280:-1" \
  "$OUTPUT_DIR/sample-%04d.png"

NB_SAMPLES="$(find "$OUTPUT_DIR" -maxdepth 1 -name 'sample-*.png' | wc -l | tr -d ' ')"
echo "$CADENCE" > "$OUTPUT_DIR/.cadence"

echo "✓ $NB_SAMPLES samples produits"
echo "✓ Cadence mémorisée dans $OUTPUT_DIR/.cadence"
