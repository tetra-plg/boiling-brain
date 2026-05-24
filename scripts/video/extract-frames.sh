#!/usr/bin/env bash
# Usage : ./scripts/extract-frames.sh <video_path> <timestamp_HH:MM:SS> <output_path> [offset_seconds]
# offset_seconds : décalage en secondes ajouté au timestamp (défaut : +5)
# Pour pointer vers un cache vidéo externe, exporter $LLMWIKI_VIDEO_CACHE avant l'appel.
set -e

VIDEO="$1"
TIMESTAMP="$2"
OUTPUT="$3"
OFFSET="${4:-5}"

# Convertir HH:MM:SS en secondes, ajouter l'offset, reconvertir
TOTAL_SECONDS=$(echo "$TIMESTAMP" | awk -F: '{ print ($1 * 3600) + ($2 * 60) + $3 }')
ADJUSTED_SECONDS=$(( TOTAL_SECONDS + OFFSET ))
ADJUSTED_TS=$(printf "%02d:%02d:%02d" $((ADJUSTED_SECONDS / 3600)) $(( (ADJUSTED_SECONDS % 3600) / 60 )) $((ADJUSTED_SECONDS % 60)))

ffmpeg -ss "$ADJUSTED_TS" -i "$VIDEO" -vf scale=1280:-1 -frames:v 1 "$OUTPUT" -y
