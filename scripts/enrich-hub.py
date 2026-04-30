#!/usr/bin/env python3
"""
enrich-hub.py — Enrichit les listes d'un hub `wiki/domains/<d>.md` avec les `summary_l0`
des pages liées. Non-destructeur : préserve l'intégralité du contenu éditorial existant.

Cible les bullets de la forme :
    - [[lien]] [...]
    - [[lien|alias]] [...]
qui ne contiennent **pas déjà un descriptif** (signaled par ` — `, ` : `, ou un texte > 20 chars).

Pour chaque match, append ` — <summary_l0>` à la ligne (récupéré depuis le frontmatter
de la page liée).

Usage : enrich-hub.py [--dry-run] <domain-slug>...
        enrich-hub.py [--dry-run] --all
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"

# Bullet line: `- [[lien|alias]] suffix`
BULLET_RE = re.compile(
    r"^(?P<indent>\s*[-*]\s+)"               # bullet
    r"\[\[(?P<target>[^|\]\n]+)(?:\|(?P<alias>[^\]\n]+))?\]\]"  # [[link|alias]]
    r"(?P<suffix>.*)$"                       # rest
)

L0_RE = re.compile(r'^summary_l0:\s*(.+)$', re.MULTILINE)


def find_page(target: str) -> Path | None:
    """Resolve [[target]] to a wiki path. Tries multiple conventions."""
    target = target.strip()
    # Strip path prefix if absolute-style (e.g. "wiki/concepts/foo")
    if target.startswith("wiki/"):
        target = target[5:]
    candidates = [
        WIKI / f"{target}.md",
        WIKI / target / "index.md",
    ]
    for cat in ("concepts", "entities", "sources", "cheatsheets", "syntheses",
                "decisions", "diagrams", "domains"):
        candidates.append(WIKI / cat / f"{Path(target).name}.md")
    for c in candidates:
        if c.is_file():
            return c
    return None


def extract_l0(page: Path) -> str | None:
    try:
        content = page.read_text(encoding="utf-8")
    except Exception:
        return None
    if not content.startswith("---"):
        return None
    end = content.find("\n---", 3)
    if end < 0:
        return None
    fm = content[3:end]
    m = L0_RE.search(fm)
    if not m:
        return None
    val = m.group(1).strip()
    # Unquote
    if (val.startswith('"') and val.endswith('"')) or \
       (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    return val


def line_already_described(alias: str | None, suffix: str) -> bool:
    """True if the line already has a meaningful descriptor (long alias or suffix)."""
    # Long alias is a descriptor (e.g. [[link|Description longue de la page]])
    if alias and len(alias.strip()) > 30:
        return True
    s = suffix.strip()
    if not s:
        return False
    # Already has a separator
    if " — " in s or " – " in s or " : " in s or s.startswith(("—", "–", ":", "-")):
        return True
    if len(s) > 30:
        return True
    return False


def process_hub(path: Path, dry_run: bool) -> tuple[int, int, int]:
    """Returns (enriched, skipped, unresolved)."""
    content = path.read_text(encoding="utf-8")
    lines = content.split("\n")
    out = []
    enriched = skipped = unresolved = 0

    in_frontmatter = False
    fm_seen = 0

    for line in lines:
        if line.strip() == "---":
            fm_seen += 1
            in_frontmatter = (fm_seen == 1)
            out.append(line)
            continue
        if fm_seen < 2:
            out.append(line)
            continue

        m = BULLET_RE.match(line)
        if not m:
            out.append(line)
            continue

        indent = m.group("indent")
        target = m.group("target")
        alias = m.group("alias")
        suffix = m.group("suffix")

        if line_already_described(alias, suffix):
            skipped += 1
            out.append(line)
            continue

        page = find_page(target)
        if page is None:
            unresolved += 1
            out.append(line)
            continue

        l0 = extract_l0(page)
        if not l0:
            unresolved += 1
            out.append(line)
            continue

        # Inject : after the [[link|...]] block, before the suffix
        link_text = line[len(indent):line.find("]]") + 2]
        new_line = f"{indent}{link_text} — {l0}{suffix}"
        out.append(new_line)
        enriched += 1

    new_content = "\n".join(out)
    if dry_run:
        if new_content != content:
            print(f"  --- DIFF preview pour {path.relative_to(ROOT)} ---")
            for orig, new in zip(content.split("\n"), out):
                if orig != new:
                    print(f"    -- {orig}")
                    print(f"    ++ {new}")
    else:
        if new_content != content:
            path.write_text(new_content, encoding="utf-8")

    return enriched, skipped, unresolved


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--all", action="store_true",
                   help="Tous les hubs wiki/domains/*.md")
    p.add_argument("domains", nargs="*",
                   help="Domain slugs (e.g. poker ia)")
    args = p.parse_args()

    if args.all:
        hubs = sorted((WIKI / "domains").glob("*.md"))
    elif args.domains:
        hubs = [WIKI / "domains" / f"{d}.md" for d in args.domains]
        for h in hubs:
            if not h.is_file():
                print(f"!! introuvable : {h}", file=sys.stderr)
                return 1
    else:
        p.print_help()
        return 1

    totals = {"enriched": 0, "skipped": 0, "unresolved": 0}
    for hub in hubs:
        e, s, u = process_hub(hub, args.dry_run)
        print(f"{hub.relative_to(ROOT)} : enriched={e}, skipped={s}, unresolved={u}")
        totals["enriched"] += e
        totals["skipped"] += s
        totals["unresolved"] += u

    print(f"=== TOTAL : {totals} ({'DRY-RUN' if args.dry_run else 'écrit'}) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
