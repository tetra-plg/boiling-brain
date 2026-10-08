#!/usr/bin/env python3
"""journal-ingest.py — deterministic journaling step of /ingest (step 4).

Reads one ingest report file (written by the main context after the expert
agent returned) and appends, with the canonical formatting:

- a `wiki/log.md` entry `## [date] ingest | <title> (agent: <agent>)` — headless:
  `(agent: <agent>, mode: headless, hint: <hint|none>)` — followed by a
  `- Source:` line and the `## Ingest summary` bullets verbatim;
- the `## Radar items` to `wiki/radar.md`: an optional leading tag
  `[verify]|[research]|[decide]|[improve]|[watch]` routes the item to the
  matching `## To <tag> ...` section; untagged or unmatched items go to a
  `## Triage` section at the top of the body (created if absent).

Report file: a frontmatter (`source`, `title`, `agent` required; `mode`
headless|interactive, default interactive; `hint` optional; `date` optional,
default today) followed by the agent's blocks verbatim.

Idempotent: if wiki/log.md already holds an `ingest |` entry for the same date
whose block carries the same `- Source:` line, nothing is written (log=skipped).
wiki/log.md is created if absent; an absent wiki/radar.md is reported on
stderr and left absent.

Usage: journal-ingest.py [--root <repo-root>] <report-file>
Stdout (machine-parseable): `log=appended|skipped`, `radar=<N>`, `triage=<M>`
(radar counts every item written, triage the subset routed to `## Triage`).
Exit 0 on success, 2 on an unreadable report or a missing/invalid key
(nothing written).
"""
import argparse
import datetime
import re
import sys
from pathlib import Path

REQUIRED_KEYS = ("source", "title", "agent")
MODES = ("headless", "interactive")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HEADER_RE = re.compile(r"^(#{1,6}) +(.*\S)\s*$")
TAG_RE = re.compile(r"^\[(verify|research|decide|improve|watch)\]\s*(.*)$")
EMPTY_ITEMS = ("", "n/a", "na", "none")
TRIAGE_SECTION = "Triage"

LOG_SKELETON = "---\ntype: log\n---\n\n# Log\n"


class ReportError(Exception):
    pass


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


def parse_report(text):
    """Return (meta dict, blocks dict title -> body lines). Raises ReportError."""
    fm_lines, body = split_frontmatter(text)
    if not fm_lines:
        raise ReportError("report has no frontmatter block")
    meta = {}
    for line in fm_lines[1:-1]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)  # first colon only: titles may hold one
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        meta[key.strip()] = value
    for key in REQUIRED_KEYS:
        if not meta.get(key):
            raise ReportError(f"missing required frontmatter key: {key}")
    meta.setdefault("mode", "interactive")
    meta["mode"] = meta["mode"] or "interactive"
    if meta["mode"] not in MODES:
        raise ReportError(f"invalid mode: {meta['mode']} (expected headless|interactive)")
    meta["date"] = meta.get("date") or datetime.date.today().isoformat()
    if not DATE_RE.match(meta["date"]):
        raise ReportError(f"invalid date: {meta['date']} (expected YYYY-MM-DD)")

    blocks = {}
    current = None
    for line in body:
        hm = HEADER_RE.match(line)
        if hm and len(hm.group(1)) == 2:
            current = hm.group(2)
            blocks[current] = []
        elif current is not None:
            blocks[current].append(line.rstrip())
    return meta, blocks


def log_header(meta):
    if meta["mode"] == "headless":
        hint = meta.get("hint") or "none"
        paren = f"agent: {meta['agent']}, mode: headless, hint: {hint}"
    else:
        paren = f"agent: {meta['agent']}"
    return f"## [{meta['date']}] ingest | {meta['title']} ({paren})"


def already_logged(log_text, meta):
    """True if an `ingest |` entry of the same date carries the same Source line."""
    prefix = f"## [{meta['date']}] ingest |"
    source_line = f"- Source: `{meta['source']}`"
    in_entry = False
    for line in log_text.splitlines():
        if line.startswith("## "):
            in_entry = line.startswith(prefix)
        elif in_entry and line.strip() == source_line:
            return True
    return False


def build_log_entry(meta, blocks):
    lines = [log_header(meta), "", f"- Source: `{meta['source']}`"]
    lines.extend(l for l in blocks.get("Ingest summary", []) if l.strip())
    return "\n".join(lines) + "\n"


def parse_radar_items(block_lines):
    """Top-level `- ` bullets of the block, with their indented continuation
    lines; returns [(tag|None, text, continuation_lines)], N/A entries dropped."""
    items = []
    for line in block_lines:
        if line.startswith("- "):
            items.append([line[2:].strip(), []])
        elif items and line.strip() and line[:1] in (" ", "\t"):
            items[-1][1].append(line)
    out = []
    for text, cont in items:
        if text.rstrip(".").lower() in EMPTY_ITEMS:
            continue
        tm = TAG_RE.match(text)
        if tm:
            out.append((tm.group(1), tm.group(2), cont))
        else:
            out.append((None, text, cont))
    return out


def find_section(lines, predicate):
    """(start, insert_at) of the first level-2 section whose title satisfies
    predicate — insert_at is just after its last non-blank line — or None."""
    start = None
    for i, line in enumerate(lines):
        hm = HEADER_RE.match(line)
        if hm and len(hm.group(1)) == 2 and predicate(hm.group(2)):
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
    return start, end


def insert_items(lines, at, entries):
    """Insert entry lines at index `at`, with a blank line before them unless
    they extend an existing list (markdownlint MD032)."""
    prev = lines[at - 1] if at > 0 else ""
    pad = [] if prev.strip() == "" or prev.lstrip().startswith("- ") else [""]
    lines[at:at] = pad + entries + [""]


def triage_anchor(lines):
    """Insertion index for a new `## Triage` section: just after the first
    `---` separator below the intro, else before the first `## ` section,
    else the end of the body."""
    for i, line in enumerate(lines):
        hm = HEADER_RE.match(line)
        if hm and len(hm.group(1)) == 2:
            return i
        if line.strip() == "---":
            return i + 1
    return len(lines)


def route_radar_items(body_lines, items, domain, date):
    """Return (new_body_lines, triage_count)."""
    lines = list(body_lines)
    triage = 0
    for tag, text, cont in items:
        entry = [f"- [ ] **[{domain} · {date}]** {text}"] + cont
        section = None
        if tag is not None:
            section = find_section(
                lines, lambda t, tag=tag: t.lower().startswith(f"to {tag}"))
        if section is None:
            triage += 1
            section = find_section(lines, lambda t: t == TRIAGE_SECTION)
            if section is None:
                at = triage_anchor(lines)
                lines[at:at] = ["", f"## {TRIAGE_SECTION}", ""]
                section = (at + 1, at + 2)
        insert_items(lines, section[1], entry)
    return lines, triage


def bump_updated(fm_lines, date):
    """Return fm_lines with `updated:` set to date; insert before the closing
    fence if absent. No-op on empty frontmatter."""
    if not fm_lines:
        return fm_lines
    out = []
    found = False
    for line in fm_lines:
        if re.match(r"^updated:\s", line):
            out.append(f"updated: {date}")
            found = True
        else:
            out.append(line)
    if not found and out and out[-1].strip() == "---":
        out = out[:-1] + [f"updated: {date}", out[-1]]
    return out


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
    ap = argparse.ArgumentParser(description="Journal one ingest report into the log and radar.")
    ap.add_argument("--root",
                    default=str(Path(__file__).resolve().parent.parent.parent),
                    help="repo root (contains wiki/)")
    ap.add_argument("report", help="ingest report file (frontmatter + agent blocks)")
    args = ap.parse_args(argv)
    root = Path(args.root)

    try:
        text = Path(args.report).read_text(encoding="utf-8")
        meta, blocks = parse_report(text)
    except (OSError, UnicodeDecodeError) as e:
        print(f"error: cannot read report {args.report}: {e}", file=sys.stderr)
        return 2
    except ReportError as e:
        print(f"error: {args.report}: {e}", file=sys.stderr)
        return 2

    log_path = root / "wiki" / "log.md"
    radar_path = root / "wiki" / "radar.md"
    log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else LOG_SKELETON

    if already_logged(log_text, meta):
        print("log=skipped")
        print("radar=0")
        print("triage=0")
        return 0

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(log_text.rstrip("\n") + "\n\n" + build_log_entry(meta, blocks),
                        encoding="utf-8")

    items = parse_radar_items(blocks.get("Radar items", []))
    written = triage = 0
    if items and not radar_path.exists():
        print(f"note: {len(items)} radar item(s) not written — wiki/radar.md is absent",
              file=sys.stderr)
    elif items:
        domain = meta.get("hint") or re.sub(r"-expert$", "", meta["agent"])
        fm, body = split_frontmatter(radar_path.read_text(encoding="utf-8"))
        body, triage = route_radar_items(body, items, domain, meta["date"])
        radar_path.write_text(render(bump_updated(fm, meta["date"]), body), encoding="utf-8")
        written = len(items)

    print("log=appended")
    print(f"radar={written}")
    print(f"triage={triage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
