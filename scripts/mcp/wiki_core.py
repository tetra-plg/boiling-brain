#!/usr/bin/env python3
"""wiki_core.py — pure, dependency-free query layer over a BoilingBrain vault.

Shared by mcp-wiki.py (FastMCP stdio server) and wiki-cli.py (headless CLI).
No third-party dependency is required: PyYAML is used opportunistically for
frontmatter and degrades to {} if absent; fastmcp is NOT imported here.

Each read tool is split into:
  <tool>_data(...) -> dict   # structured source of truth (also the JSON shape)
  <tool>_md(data)  -> str    # human-readable markdown, byte-identical to the
                             # historical mcp-wiki.py output

Errors that should map to a non-zero CLI exit raise WikiLookupError; the MCP
wrappers catch it and return str(e) so the legacy markdown behaviour is kept.

Point the module at a vault via the WIKI_PATH env var or configure().
"""
import os
import re
import json
import unicodedata
from pathlib import Path


class WikiLookupError(Exception):
    """Genuine lookup error (missing page, empty domain, path traversal, usage
    misuse). CLI maps it to stderr + exit 2; MCP wrappers return str(e)."""


WIKI_PATH = Path(os.environ.get("WIKI_PATH", str(Path(__file__).parent.parent.parent)))
WIKI_DIR = WIKI_PATH / "wiki"
RAW_DIR = WIKI_PATH / "raw"
CACHE_DIR = WIKI_PATH / "cache"

FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]")
_BACKLINK_CACHE = None

# Directory-style plural (scan tool name) -> singular value stored in `type:`.
_TYPE_TOOL_TO_FRONTMATTER = {
    "concepts": "concept",
    "sources": "source",
    "syntheses": "synthesis",
    "entities": "entity",
    "cheatsheets": "cheatsheet",
    "decisions": "decision",
    "diagrams": "diagram",
}

_TYPE_PLURAL = {
    "concept": "Concepts", "entity": "Entities", "decision": "Decisions",
    "synthesis": "Syntheses", "cheatsheet": "Cheatsheets", "diagram": "Diagrams",
    "source": "Sources",
}


def configure(wiki_path):
    """Re-point the module at a different vault root and reset caches. Used by
    wiki-cli.py --wiki-path and by tests. The MCP server relies on the WIKI_PATH
    env var resolved at import time and does not call this."""
    global WIKI_PATH, WIKI_DIR, RAW_DIR, CACHE_DIR, _BACKLINK_CACHE
    WIKI_PATH = Path(wiki_path)
    WIKI_DIR = WIKI_PATH / "wiki"
    RAW_DIR = WIKI_PATH / "raw"
    CACHE_DIR = WIKI_PATH / "cache"
    _BACKLINK_CACHE = None


# ---- frontmatter + page enumeration -------------------------------------
def _parse_front(content):
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


def _all_wiki_pages():
    return sorted(WIKI_DIR.rglob("*.md"))


def _domain_pages(domain):
    """Pages whose frontmatter `domains` contains domain (case-insensitive)."""
    domain_lower = domain.lower()
    matches = []
    for p in _all_wiki_pages():
        try:
            fm, _ = _parse_front(p.read_text(encoding="utf-8"))
            domains = fm.get("domains", [])
            if isinstance(domains, str):
                domains = [domains]
            if any(domain_lower in str(d).lower() for d in domains):
                matches.append(p)
        except Exception:
            continue
    return matches


def _safe_get_type(p):
    try:
        fm, _ = _parse_front(p.read_text(encoding="utf-8"))
        return str(fm.get("type", "")).strip().lower()
    except Exception:
        return ""


# ---- centrality ----------------------------------------------------------
def _build_backlink_index():
    counts = {}
    for p in _all_wiki_pages():
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in _WIKILINK_RE.finditer(content):
            target = m.group(1).strip()
            counts[target] = counts.get(target, 0) + 1
    return counts


def _compute_centrality(page_path):
    """Number of backlinks pointing to page_path (rel to WIKI_PATH). Lazily
    builds and caches the backlink index; configure() resets it."""
    global _BACKLINK_CACHE
    if _BACKLINK_CACHE is None:
        _BACKLINK_CACHE = _build_backlink_index()
    if not page_path.startswith("wiki/"):
        page_path = "wiki/" + page_path
    rel = page_path[len("wiki/"):]
    if rel.endswith(".md"):
        rel = rel[:-3]
    full = _BACKLINK_CACHE.get(rel, 0)
    bare = _BACKLINK_CACHE.get(rel.rsplit("/", 1)[-1], 0) if "/" in rel else 0
    return full + bare


# ---- query normalisation -------------------------------------------------
def _normalize_query(q):
    q = unicodedata.normalize("NFC", q).lower()
    tokens = []
    for chunk in q.replace("-", " ").split():
        if chunk:
            tokens.append(chunk)
    return tokens


def _normalize_haystack(text):
    text = unicodedata.normalize("NFC", text).lower()
    text = text.replace("-", " ")
    text = " ".join(text.split())
    return text


def _all_tokens_present(tokens, haystack):
    return all(t in haystack for t in tokens)


def _outgoing_wikilinks(body, limit=10):
    seen, seen_set = [], set()
    for m in _WIKILINK_RE.finditer(body):
        slug = m.group(1).strip()
        if slug in seen_set:
            continue
        seen_set.add(slug)
        seen.append(slug)
        if len(seen) >= limit:
            break
    return seen


# ---- JSON helper ---------------------------------------------------------
def to_json(data):
    """Serialize a *_data() result to JSON. Keys prefixed with '_' are
    presentation hints and are dropped from the JSON output."""
    clean = {k: v for k, v in data.items() if not k.startswith("_")}
    return json.dumps(clean, ensure_ascii=False, indent=2)


def _resolve_in_vault(page_path):
    """Resolve page_path under the vault, guarding against path traversal."""
    target = (WIKI_PATH / page_path).resolve()
    if not str(target).startswith(str(WIKI_PATH.resolve())):
        raise WikiLookupError("Erreur : chemin invalide (path traversal détecté).")
    if not target.exists():
        raise WikiLookupError(f"Page introuvable : {page_path}")
    return target
