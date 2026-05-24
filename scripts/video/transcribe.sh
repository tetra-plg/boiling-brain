#!/usr/bin/env bash
# Usage:
#   scripts/transcribe.sh <chemin-fichier-local>
#   scripts/transcribe.sh <url-youtube>
#
# Produit :
#   raw/transcripts/YYYY-MM-DD-<slug>.md
#   raw/videos-meta/YYYY-MM-DD-<slug>.meta.md
#   Purge cache/audio/<slug>.* après succès.

set -euo pipefail

INPUT="${1:?Usage: transcribe.sh <chemin-ou-url>}"
VAULT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$VAULT_ROOT"

MODEL="${WHISPER_MODEL:-$HOME/.local/share/whisper-models/ggml-large-v3-turbo.bin}"
LANG="${WHISPER_LANG:-fr}"
DATE="$(date +%Y-%m-%d)"

# Cache vidéo : surchargeable via $LLMWIKI_VIDEO_CACHE (disque externe par exemple),
# fallback transparent vers cache/videos/ si l'override pointe vers un emplacement absent.
VIDEO_CACHE="${LLMWIKI_VIDEO_CACHE:-cache/videos}"
if [[ "$VIDEO_CACHE" != cache/* ]] && [[ ! -d "$(dirname "$VIDEO_CACHE")" ]]; then
  echo "⚠️  LLMWIKI_VIDEO_CACHE=$VIDEO_CACHE introuvable — fallback vers cache/videos/"
  VIDEO_CACHE="cache/videos"
fi
mkdir -p "$VIDEO_CACHE"

# Slug & kind detection
if [[ "$INPUT" =~ ^https?:// ]]; then
  KIND="youtube"
  TITLE="$(yt-dlp --get-title --no-warnings "$INPUT" 2>/dev/null || echo "video")"
  DURATION="$(yt-dlp --get-duration --no-warnings "$INPUT" 2>/dev/null || echo "?")"
  URL="$INPUT"
else
  KIND="local"
  [[ -f "$INPUT" ]] || { echo "❌ Fichier introuvable: $INPUT"; exit 1; }
  TITLE="$(basename "${INPUT%.*}")"
  DURATION="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$INPUT" | awk '{printf "%d:%02d", $1/60, $1%60}')"
  URL="file://$(realpath "$INPUT")"
fi

SLUG="$(echo "$TITLE" | iconv -f utf-8 -t ascii//TRANSLIT 2>/dev/null | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g' | cut -c1-60)" || true
[[ -z "$SLUG" ]] && SLUG="video-$(date +%s)"

AUDIO="cache/audio/${SLUG}.wav"
TRANSCRIPT="raw/transcripts/${DATE}-${SLUG}.md"
META="raw/videos-meta/${DATE}-${SLUG}.meta.md"

mkdir -p cache/audio "$VIDEO_CACHE" raw/transcripts raw/videos-meta

echo "→ Slug: $SLUG"
echo "→ Source: $INPUT ($KIND, durée $DURATION)"

# 1. Extract audio (16kHz mono WAV, format requis par whisper.cpp)
if [[ "$KIND" == "youtube" ]]; then
  echo "→ yt-dlp: téléchargement audio…"
  yt-dlp -x --audio-format wav --postprocessor-args "-ar 16000 -ac 1" \
    -o "cache/audio/${SLUG}.%(ext)s" --no-warnings "$INPUT"
else
  echo "→ ffmpeg: extraction audio 16kHz mono…"
  ffmpeg -nostdin -loglevel error -y -i "$INPUT" -ar 16000 -ac 1 -c:a pcm_s16le "$AUDIO"
fi

# 2. Transcription
echo "→ whisper-cli: transcription ($LANG)…"
whisper-cli -m "$MODEL" -f "$AUDIO" -l "$LANG" -otxt -ovtt -of "cache/audio/${SLUG}" --no-prints 2>&1 | tail -3

# 3. Build markdown transcript with timestamps from VTT
VTT="cache/audio/${SLUG}.vtt"
{
  echo "---"
  echo "type: source-raw"
  echo "kind: transcript"
  echo "video_kind: $KIND"
  echo "source_url: $URL"
  echo "title: $TITLE"
  echo "duration: $DURATION"
  echo "language: $LANG"
  echo "transcribed: $DATE"
  echo "---"
  echo
  echo "# $TITLE"
  echo
  echo "> Transcript automatique (whisper large-v3-turbo). Source: <$URL>"
  echo
  awk '
    /-->/ {
      split($1, a, ".")
      ts = a[1]
      getline line
      printf "[%s] ", ts
      while (line != "") { printf "%s ", line; if ((getline line) <= 0) break }
      printf "\n\n"
    }
  ' "$VTT"
} > "$TRANSCRIPT"

# 4. Metadata file
HASH="$(shasum -a 256 "$AUDIO" | cut -d' ' -f1)"
{
  echo "---"
  echo "type: source-meta"
  echo "kind: $KIND"
  echo "source_url: $URL"
  echo "title: $TITLE"
  echo "duration: $DURATION"
  echo "audio_sha256: $HASH"
  echo "transcript: [[${DATE}-${SLUG}]]"
  echo "storage: purged"
  echo "transcribed: $DATE"
  echo "---"
  echo
  echo "# Metadata — $TITLE"
  echo
  echo "- **Type**: $KIND"
  echo "- **URL source**: $URL"
  echo "- **Durée**: $DURATION"
  echo "- **Transcript**: \`raw/transcripts/${DATE}-${SLUG}.md\`"
  echo "- **Média local**: purgé après transcription."
} > "$META"

# 5. Purge cache
rm -f "$AUDIO" "$VTT" "cache/audio/${SLUG}.txt"
echo "✓ Transcript: $TRANSCRIPT"
echo "✓ Meta: $META"
echo "✓ Cache purgé."
