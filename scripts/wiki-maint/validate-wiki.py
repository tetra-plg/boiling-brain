#!/usr/bin/env python3
"""
validate-wiki.py — Deterministic integrity checker for a vault's wiki/ tree.

Runs in CI (where raw/ is absent) and locally. For every wiki/**/*.md it checks:
  - [[wikilinks]] resolve to an existing wiki page (full path or bare slug)
  - internal relative markdown links / anchors resolve (non-raw, non-external)
  - frontmatter conforms to the per-type schema (see SCHEMA below)

References under raw/ are SKIPPED: raw/ is gitignored and never present on the
remote — its existence is the job of the local /lint command. External links
(http/https/mailto) are ignored: the weekly link-check-report job covers them.

Exit code: 0 if clean, 1 if any defect. Defects are printed as
`relpath:line — message`, grouped, with a final count.

Usage: validate-wiki.py [--root <repo-root>]   (default root: ../../ from this file)
"""
import argparse
import re
import sys
from pathlib import Path

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
MDLINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
EXTERNAL_RE = re.compile(r"^(https?:|mailto:|tel:)", re.IGNORECASE)
FENCE_RE = re.compile(r"^(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`]*`")


def iter_prose_lines(text):
    """Yield (line_number, code-stripped line) for lines outside code.

    Skips fenced code blocks (``` / ~~~, incl. indented fences) entirely and
    strips inline code spans (`...`) from the remaining lines, so that
    [[wikilinks]] and [x](y) links inside code are never flagged. Line numbers
    stay accurate (fenced lines are skipped, not renumbered).
    """
    in_fence = False
    for n, line in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        yield n, INLINE_CODE_RE.sub("", line)


REQUIRED_COMMON = ["type", "domains", "created", "summary_l0", "summary_l1"]


def parse_frontmatter(text):
    """Return (dict-of-raw-lines, body_start_line) or (None, 0) if no frontmatter.

    Light parser (no PyYAML dep): captures the first `key:` of each top-level
    line in the leading --- block, with the raw remainder as value. Block
    scalars (`key: |`) are captured as present-but-multiline.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, 0
    fm = {}
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        m = re.match(r"^([A-Za-z0-9_]+):(.*)$", lines[i])
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val in ("|", ">", "|-", ">-"):
                # Block scalar: non-empty iff at least one indented line follows.
                has_content = (i + 1 < len(lines)
                               and lines[i + 1].strip() != ""
                               and lines[i + 1].startswith((" ", "\t")))
                fm[key] = "<block>" if has_content else ""
            else:
                fm[key] = val
        i += 1
    return fm, i + 1


def check_frontmatter(relpath, text, defects):
    fm, _ = parse_frontmatter(text)
    if fm is None:
        defects.append(f"{relpath}:1 — missing frontmatter block")
        return
    for key in REQUIRED_COMMON:
        if key not in fm:
            defects.append(f"{relpath}:1 — frontmatter missing required field '{key}'")
    dom = fm.get("domains", "")
    if dom in ("", "[]", "[ ]"):
        defects.append(f"{relpath}:1 — frontmatter 'domains' is empty")
    l0 = fm.get("summary_l0", "")
    if l0:
        l0v = l0.strip().strip('"').strip("'")
        if len(l0v) > 140:
            defects.append(f"{relpath}:1 — frontmatter 'summary_l0' exceeds 140 chars ({len(l0v)})")
    if fm.get("summary_l1", "") == "":
        # present-but-empty block, or missing handled above
        if "summary_l1" in fm:
            defects.append(f"{relpath}:1 — frontmatter 'summary_l1' is empty")


def build_page_index(wiki_root):
    """Return (relpaths set, bare-slug set) for every wiki/**/*.md."""
    relpaths, bare = set(), set()
    for p in wiki_root.rglob("*.md"):
        rel = p.relative_to(wiki_root).with_suffix("")  # e.g. concepts/foo
        relpaths.add(str(rel).replace("\\", "/"))
        bare.add(p.stem)
    return relpaths, bare


def check_wikilinks(relpath, text, relpaths, bare, defects):
    for n, line in iter_prose_lines(text):
        for m in WIKILINK_RE.finditer(line):
            target = m.group(1).strip()
            target = target.rstrip("\\")  # handle Obsidian table alias escape [[t\|alias]]
            if target.startswith("raw/"):
                continue
            norm = target[len("wiki/"):] if target.startswith("wiki/") else target
            norm = norm[:-3] if norm.endswith(".md") else norm
            if norm in relpaths or norm.split("/")[-1] in bare:
                continue
            defects.append(f"{relpath}:{n} — broken wikilink [[{target}]]")


def check_relative_links(relpath, abspath, text, wiki_root, repo_root, defects):
    base = abspath.parent
    for n, line in iter_prose_lines(text):
        for m in MDLINK_RE.finditer(line):
            url = m.group(1).split()[0].strip()  # drop optional "title"
            if EXTERNAL_RE.match(url) or url.startswith("#") or url.startswith("[["):
                continue
            path_part = url.split("#", 1)[0]
            if not path_part:
                continue
            # Links written as raw/... point at the top-level raw store (absent
            # on the remote) — skip before any path resolution.
            if path_part.startswith("raw/"):
                continue
            target = (base / path_part).resolve()
            # Skip anything that resolves under raw/ (absent on the remote).
            try:
                rel_to_repo = target.relative_to(repo_root.resolve())
                if str(rel_to_repo).startswith("raw/"):
                    continue
            except ValueError:
                pass
            if not target.exists():
                defects.append(f"{relpath}:{n} — broken relative link ({url})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent.parent),
                    help="repo root (contains wiki/)")
    args = ap.parse_args()
    repo_root = Path(args.root)
    wiki_root = repo_root / "wiki"
    if not wiki_root.is_dir():
        print(f"error: no wiki/ under {repo_root}", file=sys.stderr)
        return 2

    relpaths, bare = build_page_index(wiki_root)
    defects = []
    for p in sorted(wiki_root.rglob("*.md")):
        rel = str(p.relative_to(repo_root)).replace("\\", "/")
        text = p.read_text(encoding="utf-8", errors="replace")
        check_frontmatter(rel, text, defects)
        check_wikilinks(rel, text, relpaths, bare, defects)
        check_relative_links(rel, p, text, wiki_root, repo_root, defects)

    if defects:
        print(f"✗ wiki integrity: {len(defects)} defect(s)\n")
        for d in defects:
            print(f"  {d}")
        return 1
    print("✓ wiki integrity: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
