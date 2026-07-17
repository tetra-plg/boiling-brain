#!/usr/bin/env python3
"""scan-raw.py — detect each raw/ file's state vs the wiki (NEW/SKIP/MODIFIED).

Invoked through scan-raw.sh, which resolves a working Python interpreter
(Windows-Store-stub safe, #64) then execs this engine. Single process:
no per-path subprocess spawns (the #70 fix). Stdlib only.
"""
import argparse
import hashlib
import json
import os
import sys
import unicodedata
from pathlib import Path

BINARY_EXT = (".png", ".jpg", ".jpeg", ".gif", ".m4a", ".mp4", ".wav", ".webp", ".pdf")


def _force_utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _is_scannable(rel: str) -> bool:
    if rel.endswith(".sync-meta.json"):
        return False
    return not rel.lower().endswith(BINARY_EXT)


def collect_files(vault_root: str, arg_paths):
    """Return (sorted abs paths, warnings). Mirrors the bash _scan_find filters.
    Sort by UTF-8 bytes so ordering is locale-independent."""
    root = Path(vault_root)
    warnings = []
    collected = set()

    def add_tree(base: Path):
        for p in base.rglob("*"):
            if p.is_file():
                rel = os.path.relpath(str(p), vault_root).replace(os.sep, "/")
                if _is_scannable(rel):
                    collected.add(str(p))

    if not arg_paths:
        add_tree(root / "raw")
    else:
        for arg in arg_paths:
            abs_p = arg if arg.startswith("/") else os.path.join(vault_root, arg)
            abs_p = os.path.normpath(abs_p)
            ap = Path(abs_p)
            if ap.is_file():
                collected.add(str(ap))
            elif ap.is_dir():
                add_tree(ap)
            else:
                warnings.append(f"path not found: {arg}")

    files = sorted(collected, key=lambda s: s.encode("utf-8"))
    return files, warnings


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="scan-raw.sh",
        description="Detect each raw/ file's state vs the wiki (NEW/SKIP/MODIFIED).",
    )
    parser.add_argument("--force", action="store_true",
                        help="reclassify every SKIP as MODIFIED")
    parser.add_argument("--orphans", action="store_true",
                        help="also list indexed paths whose raw file is gone")
    parser.add_argument("--pending", action="store_true",
                        help="scope = entries of cache/.pending-ingest (read-only)")
    parser.add_argument("--format", choices=("text", "json"), default="text",
                        help="output format (default: text)")
    parser.add_argument("paths", nargs="*", help="files or folders (default: all of raw/)")
    return parser.parse_args(argv)


def main(argv):
    _force_utf8()
    ns = parse_args(argv)
    vault_root = os.environ.get("VAULT_ROOT") or str(Path(__file__).resolve().parents[2])
    files, warnings = collect_files(vault_root, ns.paths)
    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)
    if not files:
        print("No files to analyze.", file=sys.stderr)
        return 0
    # classification wired in Task 4
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
