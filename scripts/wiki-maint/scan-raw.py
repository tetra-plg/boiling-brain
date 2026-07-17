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


def normalize_path(p: str) -> str:
    return unicodedata.normalize("NFC", p).replace("’", "'")


def frontmatter_lines(text: str):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    out = []
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        out.append(line)
    return []  # unterminated block -> treat as none


def _strip_item(line: str) -> str:
    s = line.lstrip()
    if s.startswith("- "):
        s = s[2:]
    elif s == "-":
        s = ""
    else:
        s = s[1:] if s.startswith("-") else s
    s = s.strip().strip('"')
    return s.strip()


def _ends_block(line: str) -> bool:
    # a line starting with a non-space, non-dash char closes a YAML list block
    return bool(line) and line[0] not in (" ", "\t", "-")


def parse_source_page(text: str) -> dict:
    fm = frontmatter_lines(text)
    indexed, covered, legacy = [], [], []
    first_sp = None
    sha = None
    composite = None

    # pass 1: source_path (scalar/list) + covered_paths
    mode = None  # None | "sp" | "covered"
    for line in fm:
        if line.startswith("source_path:"):
            val = line[len("source_path:"):].strip().strip('"')
            if val:
                indexed.append(val)
                if first_sp is None:
                    first_sp = val
                mode = None
            else:
                mode = "sp"
            continue
        if line.startswith("covered_paths:"):
            mode = "covered"
            continue
        if line.startswith("source_sha256_composite:"):
            composite = line[len("source_sha256_composite:"):].strip().strip('"')
            mode = None
            continue
        if line.startswith("source_sha256:"):
            v = line[len("source_sha256:"):].strip().strip('"')
            if v and not v.startswith("-"):
                sha = v
            mode = None
            continue
        if mode in ("sp", "covered"):
            if _ends_block(line):
                mode = None
                continue
            item = _strip_item(line)
            if item:
                indexed.append(item)
                if mode == "covered":
                    covered.append(item)
                if mode == "sp" and first_sp is None:
                    first_sp = item

    # pass 2: legacy `sources:`
    in_sources = False
    for line in fm:
        if line.startswith("sources:"):
            in_sources = True
            continue
        if in_sources:
            if _ends_block(line):
                in_sources = False
                continue
            item = _strip_item(line)
            if item:
                indexed.append(item)
                legacy.append(item)

    return {
        "indexed_paths": indexed,
        "first_source_path": first_sp,
        "source_sha256": sha,
        "source_sha256_composite": composite,
        "covered_paths": covered,
    }


class Index:
    def __init__(self):
        self.path_to_slug = {}     # normalized path -> slug (last wins, as bash)
        self.path_to_sha = {}      # normalized first_source_path -> stored sha
        self.dir_to_slug = {}      # normalized "raw/a/b/c/" -> slug (first wins)
        self.meta_to_slug = {}     # normalized videos-meta path -> slug (first wins)
        self.claims = {}           # normalized path -> [slugs] (lint: duplicate-claim)
        self.missing_sha = []      # slugs with source_path but no sha/composite
        self.composites = []       # (slug, covered_paths, stored_composite)
        self.all_indexed = []      # (normalized path, slug) for orphan detection


def build_index(sources_dir: str) -> Index:
    idx = Index()
    for source_file in sorted(Path(sources_dir).glob("*.md"), key=lambda p: str(p).encode()):
        slug = source_file.stem
        try:
            text = source_file.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"WARN: cannot read {source_file}: {e}", file=sys.stderr)
            continue
        meta = parse_source_page(text)

        for raw_path in meta["indexed_paths"]:
            key = normalize_path(raw_path)
            idx.path_to_slug[key] = slug
            idx.claims.setdefault(key, [])
            if slug not in idx.claims[key]:
                idx.claims[key].append(slug)
            idx.all_indexed.append((key, slug))

            # implicit-dir index (parent dir, depth >= 4 slashes)
            idir = raw_path.rsplit("/", 1)[0] + "/" if "/" in raw_path else ""
            if idir:
                idir_key = normalize_path(idir)
                if idir.count("/") >= 4 and idir_key not in idx.dir_to_slug:
                    idx.dir_to_slug[idir_key] = slug

            # videos-meta -> transcript map
            if raw_path.startswith("raw/transcripts/"):
                stem = raw_path.rsplit("/", 1)[-1]
                if stem.endswith(".md"):
                    stem = stem[:-3]
                meta_key = normalize_path(f"raw/videos-meta/{stem}.meta.md")
                idx.meta_to_slug.setdefault(meta_key, slug)

        fsp = meta["first_source_path"]
        if fsp and meta["source_sha256"]:
            idx.path_to_sha[normalize_path(fsp)] = meta["source_sha256"]

        # lint material
        if fsp and not meta["source_sha256"] and not meta["source_sha256_composite"]:
            idx.missing_sha.append(slug)
        if meta["source_sha256_composite"] and meta["covered_paths"]:
            idx.composites.append((slug, meta["covered_paths"], meta["source_sha256_composite"]))

    return idx


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
