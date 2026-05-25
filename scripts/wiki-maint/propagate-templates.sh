#!/usr/bin/env bash
# propagate-templates.sh — copy template files into the vault with a 3-way merge
# that preserves local customisations.
#
# Usage:
#   bash scripts/wiki-maint/propagate-templates.sh LOCAL_SHA TARGET_BRANCH <<< "$FILES"
#   bash scripts/wiki-maint/propagate-templates.sh LOCAL_SHA TARGET_BRANCH < files.txt
#
#   FILES = one path per line (vault-relative).
#
# Outputs (stdout, one line per file, machine-parseable):
#   PROPAGATED <file>    — case A: new in template, absent in vault, copied as-is.
#   FAST_FORWARD <file>  — case C: vault matched baseline, copied template version.
#   AUTO_MERGED <file>   — case D clean: vault edits and template edits merged
#                          without overlap; local edits preserved.
#   CONFLICT <file>      — case B (added in both, different content) OR case D
#                          with overlapping edits. File on disk contains
#                          conflict markers (<<<<<<<, =======, >>>>>>>).
#                          Caller must resolve before commit.
#
# Exit code: 0 if no CONFLICT lines were emitted, 1 otherwise.
#
# Why `git merge-file` rather than `git show > $f` or `git cherry-pick`?
#   Bootstrap resets the git history. The vault has no common ancestor with the
#   template — cherry-pick would fail. A naive `git show … > $f` overwrites
#   local customisations silently. `git merge-file` is a content-only 3-way
#   merger that operates on three files on disk; it doesn't need a shared
#   history. It cleanly merges non-overlapping edits and only flags real
#   overlapping conflicts.

set -euo pipefail

if [ "$#" -lt 2 ]; then
  printf 'Usage: %s LOCAL_SHA TARGET_BRANCH <<< "$FILE_LIST"\n' "$0" >&2
  exit 2
fi

LOCAL_SHA="$1"
TARGET_BRANCH="$2"
TARGET_REF="template-upstream/${TARGET_BRANCH}"

emit() { printf '%s %s\n' "$1" "$2"; }                  # stdout: machine output
log()  { printf '%s\n' "$*" >&2; }                      # stderr: human messages

had_conflict=0

while IFS= read -r f; do
  [ -z "$f" ] && continue

  mkdir -p "$(dirname "$f")"

  base_tmp=$(mktemp)
  theirs_tmp=$(mktemp)
  merged_tmp=$(mktemp)

  # `git show` writes nothing and exits non-zero if the path doesn't exist in the
  # ref. We tolerate the failure (file absent in baseline = case A or B).
  if ! git show "${LOCAL_SHA}:$f" >"$base_tmp" 2>/dev/null; then
    : > "$base_tmp"
  fi
  if ! git show "${TARGET_REF}:$f" >"$theirs_tmp" 2>/dev/null; then
    log "  ! target ref ${TARGET_REF} has no file '$f' — skipping (likely deleted upstream)"
    rm -f "$base_tmp" "$theirs_tmp" "$merged_tmp"
    continue
  fi

  base_empty=0
  [ ! -s "$base_tmp" ] && base_empty=1

  if [ "$base_empty" = "1" ] && [ ! -e "$f" ]; then
    # Case A: new in template, absent in vault → just copy theirs.
    cp "$theirs_tmp" "$f"
    emit PROPAGATED "$f"
  elif [ "$base_empty" = "1" ] && [ -e "$f" ]; then
    # Case B: new in template, present in vault with different content → conflict.
    # Write a marker-annotated version using empty base.
    if git merge-file -p "$f" "$base_tmp" "$theirs_tmp" >"$merged_tmp" 2>/dev/null; then
      # Identical content somehow → treat as fast-forward.
      cp "$theirs_tmp" "$f"
      emit FAST_FORWARD "$f"
    else
      cp "$merged_tmp" "$f"
      emit CONFLICT "$f"
      had_conflict=1
    fi
  elif [ -e "$f" ] && cmp -s "$f" "$base_tmp"; then
    # Case C: vault file matches baseline → fast-forward.
    cp "$theirs_tmp" "$f"
    emit FAST_FORWARD "$f"
  else
    # Case D: vault customised vs baseline → 3-way merge.
    # `ours` is the file on disk if it exists, empty otherwise (treated below).
    ours_tmp=$(mktemp)
    if [ -e "$f" ]; then cp "$f" "$ours_tmp"; else : > "$ours_tmp"; fi

    if git merge-file -p "$ours_tmp" "$base_tmp" "$theirs_tmp" >"$merged_tmp" 2>/dev/null; then
      cp "$merged_tmp" "$f"
      emit AUTO_MERGED "$f"
    else
      cp "$merged_tmp" "$f"   # write the marker-annotated version on disk
      emit CONFLICT "$f"
      had_conflict=1
    fi
    rm -f "$ours_tmp"
  fi

  rm -f "$base_tmp" "$theirs_tmp" "$merged_tmp"
done

exit "$had_conflict"
