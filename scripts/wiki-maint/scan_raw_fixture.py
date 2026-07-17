#!/usr/bin/env python3
"""Deterministic parity fixture for scan-raw. Shared by the golden generator
and test_scan_raw.py so the committed golden stays reproducible.

Covers: source_path scalar & list, covered_paths, legacy `sources:`,
sha identical / divergent / absent, implicit-dir depth 3 (not matched) vs
4 (matched), explicit trailing-slash dir cover, videos-meta->transcript,
filtered extensions, .sync-meta.json. ASCII-only paths (locale-stable sort).
"""
import hashlib
from pathlib import Path


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# raw files: rel path under raw/ -> content
RAW = {
    "notes/scalar.md": "scalar body\n",
    "notes/listed-a.md": "listed a\n",
    "notes/listed-b.md": "listed b\n",
    "notes/composite-1.md": "comp one\n",
    "notes/composite-2.md": "comp two\n",
    "notes/legacy.md": "legacy body\n",
    "notes/modified.md": "NEW content on disk\n",   # sha will diverge from stored
    "notes/brand-new.md": "never seen\n",
    "clippings/cover-dir/inside.md": "under an explicit covered dir\n",
    "deep/a/b/c/anchor.md": "implicit-dir anchor (idir raw/deep/a/b/c/ = 5 slashes >= 4 -> matched)\n",
    "deep/a/b/c/sibling.md": "implicit-dir sibling -> SKIP\n",
    "shallow/b/anchor.md": "shallow anchor (idir raw/shallow/b/ = 3 slashes < 4 -> NOT matched)\n",
    "shallow/b/sibling.md": "shallow sibling -> NEW\n",
    "transcripts/vid-slug.md": "transcript body\n",
    "videos-meta/vid-slug.meta.md": "meta body\n",
    "notes/image.png": "binary-ish\n",          # filtered by extension
    "notes/data.sync-meta.json": "{}\n",         # filtered by name
}


def build(tmp: Path) -> Path:
    vault = tmp
    for rel, content in RAW.items():
        p = vault / "raw" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    sources = vault / "wiki" / "sources"
    sources.mkdir(parents=True, exist_ok=True)

    def page(slug: str, lines: list[str]):
        (sources / f"{slug}.md").write_text(
            "---\n" + "\n".join(lines) + "\n---\n\nbody\n", encoding="utf-8")

    # exact scalar match, sha identical -> SKIP
    page("scalar", [
        "type: source",
        "source_path: raw/notes/scalar.md",
        f"source_sha256: {_sha(RAW['notes/scalar.md'])}",
    ])
    # scalar match, sha divergent -> MODIFIED (stored != on-disk)
    page("modified", [
        "type: source",
        "source_path: raw/notes/modified.md",
        f"source_sha256: {_sha('OLD content')}",
    ])
    # source_path as YAML list (both listed -> SKIP), no sha
    page("listed", [
        "type: source",
        "source_path:",
        "  - raw/notes/listed-a.md",
        "  - raw/notes/listed-b.md",
    ])
    # covered_paths + composite (composite value is placeholder here; the
    # composite-mismatch behaviour is tested in Task 12, not in this golden)
    page("composite", [
        "type: source",
        "source_path: raw/notes/composite-1.md",
        f"source_sha256: {_sha(RAW['notes/composite-1.md'])}",
        "covered_paths:",
        "  - raw/notes/composite-2.md",
    ])
    # legacy `sources:` list -> treated as covered
    page("legacy", [
        "type: source",
        "sources:",
        "  - raw/notes/legacy.md",
    ])
    # explicit covered dir (trailing slash) -> covers everything under it
    page("coverdir", [
        "type: source",
        "source_path: raw/clippings/cover-dir/",
    ])
    # implicit-dir anchor at depth 4 -> sibling SKIP; depth-3 anchor -> sibling NEW
    page("deep-anchor", [
        "type: source",
        "source_path: raw/deep/a/b/c/anchor.md",
    ])
    page("shallow-anchor", [
        "type: source",
        "source_path: raw/shallow/b/anchor.md",
    ])
    # transcript indexed -> videos-meta/vid-slug.meta.md SKIP via transcript map
    page("transcript", [
        "type: source",
        "source_path: raw/transcripts/vid-slug.md",
    ])
    return vault


if __name__ == "__main__":
    import sys, tempfile, subprocess
    with tempfile.TemporaryDirectory() as d:
        v = build(Path(d))
        print("built fixture at", v, file=sys.stderr)
        subprocess.run(["find", str(v), "-type", "f"])
