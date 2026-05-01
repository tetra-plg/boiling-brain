#!/usr/bin/env python3
"""
mcp-wiki.py — MCP server (stdio) exposant le wiki BoilingBrain via FastMCP.

Outils disponibles :
  scan_domain   — liste les pages d'un domaine avec summary_l0 (tiered loading L0)
  preview_page  — lit le frontmatter + summary_l1 d'une page (tiered loading L1)
  read_page     — lit le corps complet d'une page (tiered loading L2)
  search_wiki   — recherche full-text dans wiki/
  drop_to_raw   — écrit un fichier dans raw/ et crée cache/.pending-ingest

Usage :
  Lancé automatiquement par Claude Code via ~/.claude/settings.json.
  Variable d'environnement WIKI_PATH pour overrider le chemin du vault.
"""

import os
import re
import json
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

WIKI_PATH = Path(os.environ.get("WIKI_PATH", str(Path(__file__).parent.parent)))
WIKI_DIR = WIKI_PATH / "wiki"
RAW_DIR = WIKI_PATH / "raw"
CACHE_DIR = WIKI_PATH / "cache"

MAX_PAGES = 80
MAX_OUTPUT_TOKENS_APPROX = 10_000

FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

mcp = FastMCP("boiling-brain-wiki")


def _parse_front(content: str) -> tuple[dict, str]:
    """Returns (frontmatter_dict, body). frontmatter_dict is {} if absent."""
    m = FRONT_RE.match(content)
    if not m:
        return {}, content
    try:
        import yaml
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception:
        fm = {}
    body = content[m.end():]
    return fm, body


def _all_wiki_pages() -> list[Path]:
    return sorted(WIKI_DIR.rglob("*.md"))


def _domain_pages(domain: str) -> list[Path]:
    """Returns pages whose frontmatter domains list contains domain (case-insensitive)."""
    domain_lower = domain.lower()
    matches = []
    for p in _all_wiki_pages():
        try:
            content = p.read_text(encoding="utf-8")
            fm, _ = _parse_front(content)
            domains = fm.get("domains", [])
            if isinstance(domains, str):
                domains = [domains]
            if any(domain_lower in str(d).lower() for d in domains):
                matches.append(p)
        except Exception:
            continue
    return matches


@mcp.tool(
    description=(
        "Use FIRST before answering any question about the user's knowledge domains. "
        "Lists wiki pages for a given domain with their summary_l0 (one-line synopsis). "
        "domain: one of poker, ia, factory, metier, tech, astro. "
        "Returns a compact index (up to 80 pages, sorted by last updated) — "
        "use preview_page or read_page for details."
    )
)
def scan_domain(domain: str) -> str:
    pages = _domain_pages(domain)
    if not pages:
        return f"Aucune page trouvée pour le domaine « {domain} »."

    # Sort by updated desc, then created desc
    def sort_key(p: Path):
        try:
            fm, _ = _parse_front(p.read_text(encoding="utf-8"))
            return (str(fm.get("updated", "")), str(fm.get("created", "")))
        except Exception:
            return ("", "")

    pages.sort(key=sort_key, reverse=True)
    pages = pages[:MAX_PAGES]

    lines = [f"# Domaine : {domain} ({len(pages)} pages)\n"]
    for p in pages:
        try:
            fm, _ = _parse_front(p.read_text(encoding="utf-8"))
        except Exception:
            fm = {}
        rel = str(p.relative_to(WIKI_PATH))
        l0 = fm.get("summary_l0", "—")
        page_type = fm.get("type", "")
        updated = fm.get("updated", fm.get("created", ""))
        lines.append(f"- [{rel}] ({page_type}, {updated}) — {l0}")

    return "\n".join(lines)


@mcp.tool(
    description=(
        "Preview a wiki page: frontmatter fields + summary_l1 (2-5 sentence description). "
        "Use after scan_domain to assess relevance before reading the full body. "
        "page_path: relative path from vault root, e.g. 'wiki/concepts/my-concept.md'."
    )
)
def preview_page(page_path: str) -> str:
    target = (WIKI_PATH / page_path).resolve()
    if not str(target).startswith(str(WIKI_PATH.resolve())):
        return "Erreur : chemin invalide (path traversal détecté)."
    if not target.exists():
        return f"Page introuvable : {page_path}"
    try:
        content = target.read_text(encoding="utf-8")
    except Exception as e:
        return f"Erreur de lecture : {e}"
    fm, body = _parse_front(content)
    lines = [f"# Preview : {page_path}\n"]
    for k, v in fm.items():
        if k != "summary_l1":
            lines.append(f"**{k}**: {v}")
    l1 = fm.get("summary_l1", "")
    if l1:
        lines.append(f"\n## summary_l1\n{l1}")
    else:
        # Fall back to first 300 chars of body
        snippet = body.strip()[:300]
        lines.append(f"\n## Début de page\n{snippet}…")
    return "\n".join(lines)


@mcp.tool(
    description=(
        "Read the full content of a wiki page. "
        "Use after preview_page when the summary confirms relevance. "
        "page_path: relative path from vault root, e.g. 'wiki/sources/2026-01-15-my-source.md'."
    )
)
def read_page(page_path: str) -> str:
    target = (WIKI_PATH / page_path).resolve()
    if not str(target).startswith(str(WIKI_PATH.resolve())):
        return "Erreur : chemin invalide (path traversal détecté)."
    if not target.exists():
        return f"Page introuvable : {page_path}"
    try:
        return target.read_text(encoding="utf-8")
    except Exception as e:
        return f"Erreur de lecture : {e}"


@mcp.tool(
    description=(
        "Full-text search across all wiki pages. "
        "Returns matching pages with filename, type, and the matching line. "
        "query: search term (case-insensitive). "
        "limit: max results (default 20)."
    )
)
def search_wiki(query: str, limit: int = 20) -> str:
    if not query.strip():
        return "Requête vide."
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    results = []
    for p in _all_wiki_pages():
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            if pattern.search(line):
                rel = str(p.relative_to(WIKI_PATH))
                results.append(f"{rel}:{i}: {line.strip()}")
                break  # one match per file
        if len(results) >= limit:
            break
    if not results:
        return f"Aucun résultat pour « {query} »."
    return f"# Résultats pour « {query} » ({len(results)})\n\n" + "\n".join(results)


@mcp.tool(
    description=(
        "Drop a file into raw/ and signal it for ingestion next Claude Code session. "
        "Use to add notes, articles, or clips to the wiki from any Claude Code instance. "
        "subfolder: subpath under raw/ (e.g. 'notes', 'articles', 'clippings'). "
        "filename: target filename (e.g. '2026-04-30-my-note.md'). "
        "content: full text content to write. "
        "Creates cache/.pending-ingest with the new file path."
    )
)
def drop_to_raw(subfolder: str, filename: str, content: str) -> str:
    # Path traversal protection
    try:
        dest_dir = (RAW_DIR / subfolder).resolve()
        if not str(dest_dir).startswith(str(RAW_DIR.resolve())):
            return "Erreur : sous-dossier invalide (path traversal détecté)."
        dest_file = (dest_dir / filename).resolve()
        if not str(dest_file).startswith(str(dest_dir)):
            return "Erreur : nom de fichier invalide (path traversal détecté)."
    except Exception as e:
        return f"Erreur de validation du chemin : {e}"

    if dest_file.exists():
        return f"Fichier déjà existant : {dest_file.relative_to(WIKI_PATH)}. Utilise un autre nom."

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file.write_text(content, encoding="utf-8")

    # Signal for SessionStart hook
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pending = CACHE_DIR / ".pending-ingest"
    rel_path = str(dest_file.relative_to(WIKI_PATH))
    with open(pending, "a", encoding="utf-8") as f:
        f.write(rel_path + "\n")

    return f"Fichier créé : {rel_path}\nSignal .pending-ingest mis à jour."


if __name__ == "__main__":
    mcp.run(transport="stdio")
