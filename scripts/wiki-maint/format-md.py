#!/usr/bin/env python3
"""
format-md.py — Obsidian-safe markdown formatter (wraps Prettier).

Prettier's GFM table formatter treats a bare `|` inside a wikilink alias
(`[[target|alias]]`) or a code span (`` `a|b` ``) as a column separator and
corrupts the table (splits the cell, shifts every following column). Those
pipes are legitimate Obsidian syntax. This wrapper masks the interior pipes
with a private-use sentinel before running Prettier, then restores them — so
Prettier still aligns and normalises everything without ever seeing an
ambiguous pipe.

Usage:
  format-md.py --write <glob-or-path>...   # format in place
  format-md.py --check <glob-or-path>...   # exit 1 if any file is not formatted

Both modes invoke Prettier ONCE for the whole batch (npx startup is the cost),
so they scale to thousands of files. --check never mutates the working tree
(it formats masked copies in a temp dir and diffs).
"""
import argparse
import glob as globlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Unicode private-use codepoint, width 1, never present in real markdown.
SENTINEL = ""

WIKILINK_RE = re.compile(r"\[\[[^\]\n]*\]\]")
# Matched run of backticks ... same run of backticks (code span), single line.
CODESPAN_RE = re.compile(r"(`+)(?:[^`\n]|(?!\1)`)*?\1")


def mask(text: str) -> str:
    """Replace `|` inside wikilinks and code spans with the sentinel."""
    text = WIKILINK_RE.sub(lambda m: m.group(0).replace("|", SENTINEL), text)
    text = CODESPAN_RE.sub(lambda m: m.group(0).replace("|", SENTINEL), text)
    return text


def unmask(text: str) -> str:
    return text.replace(SENTINEL, "|")


# Directories never formatted. KEEP ALIGNED with .prettierignore and the
# markdownlint globs in .github/workflows/lint.yml. A path is excluded if any
# of its segments matches one of these (or starts with ".venv": virtualenvs).
# "superpowers" = docs/superpowers/ (session artifacts, gitignored, never committed).
EXCLUDE_DIRS = {"node_modules", "raw", "cache", "dist", "worktrees", ".git", ".obsidian", "superpowers"}


def _excluded(path: str) -> bool:
    return any(seg in EXCLUDE_DIRS or seg.startswith(".venv") for seg in Path(path).parts)


def expand(paths):
    files = []
    for p in paths:
        if os.path.isfile(p):
            files.append(p)
        else:
            # include_hidden=True (Python 3.11+) so `**/*.md` descends into
            # dotted dirs like .claude/ and .github/ (excluded ones dropped below).
            files.extend(globlib.glob(p, recursive=True, include_hidden=True))
    # dedupe, keep markdown only, drop excluded dirs
    seen, out = set(), []
    for f in files:
        if f.endswith(".md") and os.path.isfile(f) and f not in seen and not _excluded(f):
            seen.add(f)
            out.append(f)
    return out


def _npx():
    exe = shutil.which("npx")
    if not exe:
        raise RuntimeError("npx introuvable sur le PATH — installe Node.js (qui fournit npx).")
    return exe


def run_prettier(files, cwd=None):
    proc = subprocess.run(
        [_npx(), "-y", "prettier", "--write", *files],
        capture_output=True, text=True, cwd=cwd,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"prettier failed:\n{proc.stderr}")


MAX_WRITE_PASSES = 5


def _format_pass(files):
    """One mask in place → prettier --write (one call) → unmask in place."""
    masked = []
    try:
        for f in files:
            orig = Path(f).read_text(encoding="utf-8")
            if SENTINEL in orig:
                print(f"skip (sentinel already present): {f}", file=sys.stderr)
                continue
            Path(f).write_text(mask(orig), encoding="utf-8")
            masked.append(f)
        run_prettier(masked)
    finally:
        # Always restore, even if prettier raised, so we never leave masked files.
        for f in masked:
            Path(f).write_text(unmask(Path(f).read_text(encoding="utf-8")), encoding="utf-8")


def do_write(files):
    """Format to a fixed point: repeat the mask/prettier/unmask pass until a
    pass changes nothing (some markdown needs 2+ passes to stabilise). Bounded
    by MAX_WRITE_PASSES so we never loop forever."""
    if not files:
        return 0
    for _ in range(MAX_WRITE_PASSES):
        before = {f: Path(f).read_text(encoding="utf-8") for f in files}
        _format_pass(files)
        if all(Path(f).read_text(encoding="utf-8") == before[f] for f in files):
            return 0
    print(f"warning: did not reach a fixed point after {MAX_WRITE_PASSES} passes "
          f"(run --check to see remaining files)", file=sys.stderr)
    return 0


def do_check(files):
    """Format masked copies in a temp tree, diff against originals. No mutation."""
    if not files:
        return 0
    repo_root = Path.cwd()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # Carry the Prettier config so formatting matches the real run.
        for cfg in (".prettierrc", ".prettierignore", ".prettierrc.json", ".prettierrc.yaml"):
            if (repo_root / cfg).is_file():
                shutil.copy(repo_root / cfg, tmp / cfg)
        rel_copies = []
        skipped = []
        for f in files:
            orig = Path(f).read_text(encoding="utf-8")
            if SENTINEL in orig:
                skipped.append(f)
                continue
            rel = Path(f)
            dest = tmp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(mask(orig), encoding="utf-8")
            rel_copies.append(str(rel))
        run_prettier(rel_copies, cwd=str(tmp))
        unformatted = []
        for f in rel_copies:
            formatted = unmask((tmp / f).read_text(encoding="utf-8"))
            if formatted != Path(f).read_text(encoding="utf-8"):
                unformatted.append(f)
    for f in skipped:
        print(f"skip (sentinel already present): {f}", file=sys.stderr)
    if unformatted:
        print("Not formatted (run: python3 scripts/wiki-maint/format-md.py --write ...):")
        for f in unformatted:
            print(f"  {f}")
        return 1
    print(f"✓ format: {len(files)} file(s) clean")
    return 0


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Obsidian-safe markdown formatter (wraps Prettier).")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="format files in place")
    mode.add_argument("--check", action="store_true", help="exit 1 if any file is unformatted")
    ap.add_argument("paths", nargs="+", help="files or globs (e.g. '**/*.md')")
    args = ap.parse_args()
    files = expand(args.paths)
    return do_write(files) if args.write else do_check(files)


if __name__ == "__main__":
    sys.exit(main())
