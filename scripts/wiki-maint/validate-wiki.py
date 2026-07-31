#!/usr/bin/env python3
"""
validate-wiki.py — Deterministic integrity checker for a vault's wiki/ tree.

Runs in CI (where raw/ is absent) and locally. For every wiki/**/*.md it checks:
  - [[wikilinks]] resolve to an existing wiki page (full path or bare slug);
    a [[raw/…]] wikilink is always flagged — the wiki must never link into raw/
  - internal relative markdown links / anchors resolve (non-raw, non-external)
  - frontmatter conforms to the common schema and per-type requirements (#104):
    required fields per type (decision: status; source: source_path, source_sha256,
    ingested), closed enums (status: pending|accepted; verdict: validated|
    invalidated|partial), sha256 format validation, and verdict companions
  - frontmatter is valid YAML (yaml.safe_load), matching the MCP/index consumers
    — skipped with a stderr note if PyYAML is not installed
Plus a repo-wide scan for leftover git conflict markers in any markdown
(`<<<<<<<` / `>>>>>>>`) — e.g. from an unresolved /update-vault 3-way merge.

Relative markdown links under raw/ are SKIPPED: raw/ is gitignored and never
present on the remote — its existence is the job of the local /lint command.
(A [[raw/…]] wikilink, by contrast, is a convention defect, flagged above.)
External links (http/https/mailto) are ignored: the weekly link-check-report
job covers them.

Exit code: 0 if clean, 1 if any defect. Defects are printed as
`relpath:line — message`, grouped, with a final count.

Usage: validate-wiki.py [--root <repo-root>] [--warn-frontmatter-types]
  --warn-frontmatter-types: transitional flag (#104) that downgrades per-type
    frontmatter defects to stderr warnings instead of failing CI
"""
import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # PyYAML is optional: the frontmatter YAML-syntax check
    yaml = None      # degrades gracefully (like the MCP/index consumers) if absent.

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
MDLINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
EXTERNAL_RE = re.compile(r"^(https?:|mailto:|tel:)", re.IGNORECASE)
FENCE_RE = re.compile(r"^(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`]*`")

# Dirs excluded from the repo-wide conflict-marker scan (gitignored / VCS / editor).
SCAN_EXCLUDE = {"node_modules", "raw", "cache", "dist", "worktrees", ".git", ".obsidian", "superpowers"}


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

REQUIRED_BY_TYPE = {
    "decision": ["status"],
    "source": ["source_path", "source_sha256", "ingested"],
}
ENUMS = {
    "status": ("pending", "accepted"),
    "verdict": ("validated", "invalidated", "partial"),
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
YAML_NULLS = (None, "", "null", "~", "Null", "NULL")


def _fm_value(fm, key):
    """Frontmatter value for per-type checks: surrounding quotes honoured,
    trailing YAML comment (` # ...`) dropped for unquoted values; None if absent."""
    if key not in fm:
        return None
    raw = fm[key].strip()
    if raw[:1] in ('"', "'"):
        q = raw[0]
        end = raw.find(q, 1)
        return raw[1:end] if end != -1 else raw.strip(q)
    return re.sub(r"\s+#.*$", "", raw).strip()


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


def check_frontmatter_by_type(relpath, text, out):
    """Per-type frontmatter requirements (#104), from .claude/rules/frontmatter.md:
    required fields per type, closed enums, sha256 format, verdict companions.
    Unknown types have no per-type requirements. Appends messages to `out`
    (the caller decides whether they are defects or transitional warnings)."""
    fm, _ = parse_frontmatter(text)
    if fm is None:
        return  # missing frontmatter is check_frontmatter's defect
    ptype = _fm_value(fm, "type") or ""
    for field in REQUIRED_BY_TYPE.get(ptype, []):
        if _fm_value(fm, field) in (None, ""):
            out.append(f"{relpath}:1 — type '{ptype}' requires frontmatter field '{field}'")
    if ptype == "decision":
        status = _fm_value(fm, "status")
        if status not in (None, "") and status not in ENUMS["status"]:
            shown = "a block scalar" if status == "<block>" else f"'{status}'"
            out.append(f"{relpath}:1 — 'status' must be one of pending|accepted (got {shown})")
        verdict = _fm_value(fm, "verdict")
        if verdict not in YAML_NULLS:
            if verdict not in ENUMS["verdict"]:
                shown = "a block scalar" if verdict == "<block>" else f"'{verdict}'"
                out.append(f"{relpath}:1 — 'verdict' must be one of "
                           f"validated|invalidated|partial (got {shown})")
            for comp in ("verdict_date", "verdict_evidence"):
                if _fm_value(fm, comp) in YAML_NULLS:
                    out.append(f"{relpath}:1 — 'verdict' is set but '{comp}' is missing or null")
    if ptype == "source":
        sha = _fm_value(fm, "source_sha256")
        if sha not in (None, "") and not SHA256_RE.match(sha):
            out.append(f"{relpath}:1 — 'source_sha256' is not a 64-char lowercase "
                       f"hex sha256 (got '{sha}')")


def frontmatter_block(text):
    """Return the raw text between the leading `---` fences, or None if absent
    or unterminated. Used to feed yaml.safe_load the exact frontmatter block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    block = []
    for line in lines[1:]:
        if line.strip() == "---":
            return "\n".join(block)
        block.append(line)
    return None  # unterminated frontmatter — structure handled by check_frontmatter


def check_frontmatter_yaml(relpath, text, defects):
    """Flag frontmatter the hand-rolled parser accepts but real YAML rejects.

    The consumers (MCP `wiki_core`, indexing) load frontmatter with
    `yaml.safe_load`; a page whose frontmatter is not valid YAML is silently
    dropped there (its `type` and summaries vanish → invisible to tiered
    loading), with no error. This check aligns the validator with them.

    Requires PyYAML; when it is absent the check is skipped (announced once on
    stderr from main(), so the degradation is not silent).
    """
    if yaml is None:
        return
    block = frontmatter_block(text)
    if block is None:
        return  # missing/unterminated frontmatter is handled by check_frontmatter
    try:
        yaml.safe_load(block)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        # +1 for the opening `---` line, +1 to convert the 0-indexed mark to a
        # 1-indexed file line; fall back to the frontmatter start if unavailable.
        line = mark.line + 2 if mark is not None else 1
        problem = getattr(e, "problem", None) or str(e).splitlines()[0]
        defects.append(f"{relpath}:{line} — frontmatter is not valid YAML: {problem}")


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
                # A wiki→raw/ wikilink is a convention violation, independent of
                # whether raw/ is present on disk: the wiki must never link into
                # raw/. Flag it (do not try to resolve the path).
                defects.append(
                    f"{relpath}:{n} — wikilink into raw/ [[{target}]] "
                    "(the wiki must never link into raw/)")
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


def check_conflict_markers(repo_root, defects):
    """Flag leftover git conflict markers in any markdown (repo-wide).

    A 3-way merge (e.g. /update-vault propagation) writes `<<<<<<<` / `>>>>>>>`
    markers on conflict; if left unresolved they must never reach a commit. We
    scan all markdown outside gitignored/VCS dirs so the CI catches them.
    """
    for p in sorted(repo_root.rglob("*.md")):
        if any(seg in SCAN_EXCLUDE or seg.startswith(".venv") for seg in p.relative_to(repo_root).parts):
            continue
        rel = str(p.relative_to(repo_root)).replace("\\", "/")
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if line.startswith("<<<<<<<") or line.startswith(">>>>>>>"):
                defects.append(f"{rel}:{n} — git conflict marker ({line[:7]})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent.parent),
                    help="repo root (contains wiki/)")
    ap.add_argument("--warn-frontmatter-types", action="store_true",
                    help="transitional (#104): report per-type frontmatter defects "
                         "as warnings on stderr instead of failing")
    args = ap.parse_args()
    repo_root = Path(args.root)
    wiki_root = repo_root / "wiki"
    if not wiki_root.is_dir():
        print(f"error: no wiki/ under {repo_root}", file=sys.stderr)
        return 2

    if yaml is None:
        print("note: PyYAML not available — skipping the frontmatter "
              "YAML-syntax check", file=sys.stderr)

    relpaths, bare = build_page_index(wiki_root)
    defects = []
    type_defects = []
    for p in sorted(wiki_root.rglob("*.md")):
        rel = str(p.relative_to(repo_root)).replace("\\", "/")
        text = p.read_text(encoding="utf-8", errors="replace")
        check_frontmatter(rel, text, defects)
        check_frontmatter_by_type(rel, text, type_defects)
        check_frontmatter_yaml(rel, text, defects)
        check_wikilinks(rel, text, relpaths, bare, defects)
        check_relative_links(rel, p, text, wiki_root, repo_root, defects)

    check_conflict_markers(repo_root, defects)

    if args.warn_frontmatter_types:
        for d in type_defects:
            print(f"WARN: {d}", file=sys.stderr)
        if type_defects:
            print(f"note: {len(type_defects)} per-type frontmatter warning(s) downgraded by "
                  f"--warn-frontmatter-types", file=sys.stderr)
    else:
        defects.extend(type_defects)

    if defects:
        print(f"✗ wiki integrity: {len(defects)} defect(s)\n")
        for d in defects:
            print(f"  {d}")
        return 1
    print("✓ wiki integrity: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
