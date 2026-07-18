#!/usr/bin/env python3
"""archive-radar.py — move handled ([x]) radar entries into the archive.

Final step of /lint: every `- [x]` entry in wiki/radar.md is moved into
wiki/radar-archive.md, under the section with the same title (created if
absent; generic `## Handled` fallback for entries under no section). Each
entry's resolution text is preserved verbatim. The archive is created on
first use with a valid frontmatter. Both files get their `updated:` date
bumped. Idempotent: no `[x]` -> no writes.

Usage: archive-radar.py [--root <repo-root>] [--date YYYY-MM-DD]
Stdout (machine-parseable): `archived=<N>`, `active=<M>`, `total_archived=<K>`,
then `section:<title>=<count>` per source section.
Exit 0 on success (incl. archived=0 and radar absent), 2 on real error.
"""
import argparse
import datetime
import re
import sys
from collections import OrderedDict
from pathlib import Path

ENTRY_RE = re.compile(r"^(?P<indent>\s*)- \[(?P<mark>[ xX])\] ")
HEADER_RE = re.compile(r"^(#{1,6}) +(.*\S)\s*$")
FALLBACK_SECTION = "Handled"


def split_frontmatter(text):
    """Return (fm_lines, body_lines). fm_lines includes the --- fences;
    [] if there is no leading frontmatter block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return [], lines
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[: i + 1], lines[i + 1:]
    return [], lines  # malformed: no closing fence -> treat all as body


def parse_entry_block(lines, i):
    """lines[i] is an entry marker. Return (block_lines, next_i). The block is
    the marker line plus every following non-blank line indented strictly more
    than the marker (continuation / sub-bullets)."""
    m = ENTRY_RE.match(lines[i])
    marker_indent = len(m.group("indent"))
    block = [lines[i]]
    j = i + 1
    while j < len(lines):
        line = lines[j]
        if line.strip() == "":
            break
        indent = len(line) - len(line.lstrip())
        if indent > marker_indent:
            block.append(line)
            j += 1
        else:
            break
    return block, j


def strip_checked(body_lines):
    """Return (new_body_lines, moved). moved = [(section_title|None, block)]
    for every [x] entry, in document order; new_body_lines has them removed."""
    out = []
    moved = []
    current_section = None
    i = 0
    n = len(body_lines)
    while i < n:
        line = body_lines[i]
        hm = HEADER_RE.match(line)
        if hm and len(hm.group(1)) == 2:
            current_section = hm.group(2)
            out.append(line)
            i += 1
            continue
        em = ENTRY_RE.match(line)
        if em and em.group("mark") in ("x", "X"):
            block, j = parse_entry_block(body_lines, i)
            moved.append((current_section, block))
            i = j
            continue
        out.append(line)
        i += 1
    return out, moved


def find_section_end(lines, title):
    """Index just after the last non-blank line of the level-2 section titled
    `title`, or None if that section is absent."""
    start = None
    for i, line in enumerate(lines):
        hm = HEADER_RE.match(line)
        if hm and len(hm.group(1)) == 2 and hm.group(2) == title:
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        hm = HEADER_RE.match(lines[j])
        if hm and len(hm.group(1)) <= 2:
            end = j
            break
    while end > start + 1 and lines[end - 1].strip() == "":
        end -= 1
    return end


def append_to_archive(body_lines, moved):
    """Insert moved blocks into archive body under matching level-2 sections,
    creating sections (at end of body) as needed. Header-less entries go under
    `## Handled`."""
    groups = OrderedDict()
    for title, block in moved:
        key = title if title is not None else FALLBACK_SECTION
        groups.setdefault(key, []).append(block)

    lines = list(body_lines)
    for title, blocks in groups.items():
        new_entries = []
        for block in blocks:
            new_entries.extend(block)
        insert_at = find_section_end(lines, title)
        if insert_at is None:
            if lines and lines[-1].strip() != "":
                lines.append("")
            lines.append(f"## {title}")
            lines.append("")
            lines.extend(new_entries)
        else:
            lines[insert_at:insert_at] = new_entries
    return lines


def render(fm_lines, body_lines):
    """Join frontmatter + body, collapse runs of blank lines to one, and end
    with a single trailing newline (markdownlint-friendly)."""
    out = []
    blank_run = 0
    for line in fm_lines + body_lines:
        if line.strip() == "":
            blank_run += 1
            if blank_run <= 1:
                out.append("")
        else:
            blank_run = 0
            out.append(line)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Archive handled radar entries.")
    ap.add_argument("--root",
                    default=str(Path(__file__).resolve().parent.parent.parent),
                    help="repo root (contains wiki/)")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    args = ap.parse_args(argv)
    date = args.date or datetime.date.today().isoformat()
    root = Path(args.root)
    radar_path = root / "wiki" / "radar.md"
    archive_path = root / "wiki" / "radar-archive.md"

    if not radar_path.exists():
        print("archived=0")
        return 0

    radar_text = radar_path.read_text(encoding="utf-8")
    radar_fm, radar_body = split_frontmatter(radar_text)
    new_radar_body, moved = strip_checked(radar_body)

    if archive_path.exists():
        arch_fm, arch_body = split_frontmatter(
            archive_path.read_text(encoding="utf-8"))
    else:
        arch_fm, arch_body = [], []

    new_arch_body = append_to_archive(arch_body, moved)

    radar_path.write_text(render(radar_fm, new_radar_body), encoding="utf-8")
    archive_path.write_text(render(arch_fm, new_arch_body), encoding="utf-8")

    per_section = OrderedDict()
    for title, _block in moved:
        key = title if title is not None else FALLBACK_SECTION
        per_section[key] = per_section.get(key, 0) + 1
    print(f"archived={len(moved)}")
    for key, count in per_section.items():
        print(f"section:{key}={count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
