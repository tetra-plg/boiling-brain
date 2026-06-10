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


# ---- read_page -----------------------------------------------------------
def read_page_data(page_path):
    target = _resolve_in_vault(page_path)
    try:
        content = target.read_text(encoding="utf-8")
    except Exception as e:
        raise WikiLookupError(f"Erreur de lecture : {e}")
    return {"page_path": page_path, "content": content}


def read_page_md(data):
    return data["content"]


# ---- preview_page --------------------------------------------------------
def preview_page_data(page_path):
    target = _resolve_in_vault(page_path)
    try:
        content = target.read_text(encoding="utf-8")
    except Exception as e:
        raise WikiLookupError(f"Erreur de lecture : {e}")
    fm, body = _parse_front(content)
    # Whitelist caps verbosity — mirrors the historical preview_page output.
    preview_fields = ("type", "domains", "created", "updated", "summary_l0",
                      "sources", "status", "verdict")
    frontmatter = {k: fm[k] for k in preview_fields if k in fm}
    l1 = fm.get("summary_l1", "") or ""
    body_snippet = None if l1 else body.strip()[:300]
    return {"page_path": page_path, "frontmatter": frontmatter,
            "summary_l1": l1, "body_snippet": body_snippet}


def preview_page_md(data):
    lines = [f"# Preview : {data['page_path']}\n"]
    for k, v in data["frontmatter"].items():
        lines.append(f"**{k}**: {v}")
    if data["summary_l1"]:
        lines.append(f"\n## summary_l1\n{data['summary_l1']}")
    else:
        lines.append(f"\n## Début de page\n{data['body_snippet']}…")
    return "\n".join(lines)


# ---- search_wiki ---------------------------------------------------------
def search_wiki_data(query, limit=10):
    tokens = _normalize_query(query)
    if not tokens:
        raise WikiLookupError("Requête vide.")
    scored = []
    for p in _all_wiki_pages():
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
        fm, body = _parse_front(content)
        haystack = _normalize_haystack(" ".join([
            str(fm.get("summary_l0", "")),
            str(fm.get("summary_l1", "")),
            p.stem,
            body,
        ]))
        if _all_tokens_present(tokens, haystack):
            centrality = _compute_centrality(str(p.relative_to(WIKI_PATH)))
            scored.append((centrality, p, fm, body))
    scored.sort(key=lambda x: x[0], reverse=True)
    kept = scored[:limit]
    results = [{
        "path": str(p.relative_to(WIKI_PATH)),
        "type": fm.get("type", ""),
        "summary_l0": fm.get("summary_l0") or "",
        "backlinks": c,
        "wikilinks": _outgoing_wikilinks(body, limit=3),
    } for c, p, fm, body in kept]
    return {"query": query, "limit": limit, "results": results}


def search_wiki_md(data):
    results = data["results"]
    if not results:
        return f"Aucun résultat pour « {data['query']} »."
    lines = [f"# Résultats pour « {data['query']} » ({len(results)})", ""]
    for r in results:
        l0 = r["summary_l0"] or "—"
        wl = ", ".join(r["wikilinks"]) if r["wikilinks"] else "—"
        lines.append(f"- {r['path']} ({r['type']}) — {l0} — wikilinks: [{wl}]")
    return "\n".join(lines)


# ---- scan_<type> ---------------------------------------------------------
def scan_type_data(domain, type_singular, query="", top=20):
    """Return structured scan results for a given type within a domain.

    Raises WikiLookupError when the domain has zero pages (empty domain).
    Returns an empty results list with a _reason key when the domain exists
    but has no pages of the requested type, or when the query yields no match.
    The _reason key is a presentation hint stripped from to_json() output.
    """
    domain_pages = _domain_pages(domain)
    if not domain_pages:
        raise WikiLookupError(
            f"Aucune page de type « {type_singular} » dans le domaine « {domain} ».")
    typed = []
    for p in domain_pages:
        try:
            fm, body = _parse_front(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(fm.get("type", "")).strip().lower() != type_singular:
            continue
        typed.append((p, fm, body))
    base = {"domain": domain, "type": type_singular, "query": query, "top": top}
    if not typed:
        return {**base, "results": [], "_reason": "no_typed"}
    if query.strip():
        tokens = _normalize_query(query)
        scored = []
        for p, fm, body in typed:
            haystack = _normalize_haystack(" ".join([
                str(fm.get("summary_l0", "")),
                str(fm.get("summary_l1", "")),
                p.stem,
                body,
            ]))
            if _all_tokens_present(tokens, haystack):
                centrality = _compute_centrality(str(p.relative_to(WIKI_PATH)))
                scored.append((centrality, p, fm))
        scored.sort(key=lambda x: x[0], reverse=True)
        kept = scored[:top]
        if not kept:
            return {**base, "results": [], "_reason": "no_match"}
    else:
        ranked = []
        for p, fm, _b in typed:
            centrality = _compute_centrality(str(p.relative_to(WIKI_PATH)))
            ranked.append((centrality, p, fm))
        ranked.sort(key=lambda x: x[0], reverse=True)
        kept = ranked[:top]
    results = [{
        "path": str(p.relative_to(WIKI_PATH)),
        "slug": p.stem,
        "type": type_singular,
        # Use `or ""` (not str(...)) so YAML-null summary_l0 becomes "" not "None".
        "summary_l0": fm.get("summary_l0") or "",
        "backlinks": c,
    } for c, p, fm in kept]
    return {**base, "results": results}


def scan_type_md(data):
    """Render scan_type_data() output as a human-readable markdown string."""
    type_singular = data["type"]
    type_plural = _TYPE_PLURAL.get(type_singular, type_singular.capitalize())
    domain, query = data["domain"], data["query"]
    if not data["results"]:
        if data.get("_reason") == "no_match":
            return (f"Aucune page de type « {type_singular} » dans « {domain} » "
                    f"ne matche « {query} ».")
        return f"Aucune page de type « {type_singular} » dans le domaine « {domain} »."
    header = (f"# {type_plural} dans {domain} — top {len(data['results'])}"
              + (f" pour « {query} »" if query.strip() else " par centralité"))
    lines = [header, ""]
    for r in data["results"]:
        l0 = r["summary_l0"] or "—"
        lines.append(f"- {r['slug']} — {l0}")
    return "\n".join(lines)


def scan_sources_data(domain, query="", top=20):
    """scan_type_data wrapper for sources that requires a non-empty query.

    Raises WikiLookupError with guidance when query is empty, matching the
    legacy scan_sources behaviour (too many sources to be useful without a target).
    """
    if not query.strip():
        n_sources = sum(1 for p in _domain_pages(domain) if _safe_get_type(p) == "source")
        raise WikiLookupError(
            f"scan_sources(\"{domain}\") sans query retournerait {n_sources} sources, peu utile.\n"
            f"Préciser une query : scan_sources(\"{domain}\", query=\"<topic>\").\n"
            f"Pour explorer le domaine sans cible, préférer scan_domain(\"{domain}\") "
            f"ou scan_concepts(\"{domain}\")."
        )
    return scan_type_data(domain, "source", query, top)


# ---- scan_domain ---------------------------------------------------------
def scan_domain_data(domain):
    """Return a structured overview of a domain: page count, hub summary,
    type counts sorted by descending count, and top-10 most central pages.

    Raises WikiLookupError when the domain has zero pages.
    """
    pages = _domain_pages(domain)
    if not pages:
        raise WikiLookupError(f"Aucune page trouvée pour le domaine « {domain} ».")
    hub_path = WIKI_DIR / "domains" / f"{domain}.md"
    hub_l1 = ""
    if hub_path.exists():
        try:
            hub_fm, _ = _parse_front(hub_path.read_text(encoding="utf-8"))
            hub_l1 = hub_fm.get("summary_l1", "") or ""
        except Exception:
            hub_l1 = ""
    counts = {}
    for p in pages:
        try:
            fm, _ = _parse_front(p.read_text(encoding="utf-8"))
            t = str(fm.get("type", "")).strip().lower()
            counts[t] = counts.get(t, 0) + 1
        except Exception:
            continue
    sorted_counts = sorted(counts.items(), key=lambda kv: -kv[1])
    ranked = []
    for p in pages:
        try:
            fm, _ = _parse_front(p.read_text(encoding="utf-8"))
        except Exception:
            fm = {}
        c = _compute_centrality(str(p.relative_to(WIKI_PATH)))
        ranked.append((c, p, fm))
    ranked.sort(key=lambda x: x[0], reverse=True)
    top_central = [{
        "path": str(p.relative_to(WIKI_PATH)),
        "type": fm.get("type", ""),
        "backlinks": c,
        # Use `or ""` (not str(...)) so YAML-null summary_l0 becomes "" not "None".
        "summary_l0": fm.get("summary_l0") or "",
    } for c, p, fm in ranked[:10]]
    return {
        "domain": domain,
        "page_count": len(pages),
        "hub_summary_l1": hub_l1,
        "counts": [{"type": t, "n": n} for t, n in sorted_counts],
        "top_central": top_central,
    }


def scan_domain_md(data):
    """Render scan_domain_data() output as a human-readable markdown string."""
    domain = data["domain"]
    lines = [f"# Domaine {domain} ({data['page_count']} pages)\n"]
    if data["hub_summary_l1"]:
        lines.append("## Hub\n")
        lines.append(data["hub_summary_l1"].strip())
        lines.append("")
    lines.append("## Structure")
    type_to_tool = {v: k for k, v in _TYPE_TOOL_TO_FRONTMATTER.items()}
    for entry in data["counts"]:
        t, n = entry["type"], entry["n"]
        tool = type_to_tool.get(t)
        if tool == "sources":
            hint = f'scan_sources("{domain}", query=...)  [query required]'
        elif tool:
            hint = f'scan_{tool}("{domain}")'
        else:
            hint = "(no dedicated scan tool for this type)"
        lines.append(f"- {t}: {n} → {hint}")
    lines.append("")
    lines.append("## Top 10 pages centrales (par backlinks)")
    for r in data["top_central"]:
        p = WIKI_PATH / r["path"]
        rel_dir = str(p.parent.relative_to(WIKI_DIR))
        l0 = r["summary_l0"] or "—"
        lines.append(f"- {rel_dir}/{p.stem} ({r['type']}, {r['backlinks']} backlinks) — {l0}")
    return "\n".join(lines)
