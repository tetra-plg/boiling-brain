#!/usr/bin/env python3
"""
mcp-wiki.py — MCP server (stdio) exposing the BoilingBrain wiki via FastMCP.

Tools (12 total, organised as a tiered-loading hierarchy):

  Orient (entry point, ~1k tokens):
    scan_domain   — hub summary_l1 + counts per type + top 10 by centrality

  Drill (per-type, ~500 tokens each):
    scan_concepts, scan_entities, scan_decisions, scan_syntheses,
    scan_cheatsheets, scan_diagrams       — top N by centrality OR matching query
    scan_sources                          — same shape but query REQUIRED

  Tiered loading (page-level):
    preview_page  — frontmatter + summary_l1
    read_page     — full body

  Cross-coupe (cross-type, cross-domain):
    search_wiki   — tokenised full-text + ranking by centrality

  Write side:
    drop_to_raw   — server-side write into raw/ (bypasses protect-raw.sh)

Usage:
  Launched automatically by Claude Code (registered via `claude mcp add`).
  Set WIKI_PATH env var to override the vault root path.
"""

import os
import re
import json
import unicodedata
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

WIKI_PATH = Path(os.environ.get("WIKI_PATH", str(Path(__file__).parent.parent.parent)))
WIKI_DIR = WIKI_PATH / "wiki"
RAW_DIR = WIKI_PATH / "raw"
CACHE_DIR = WIKI_PATH / "cache"

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


_BACKLINK_CACHE: dict[str, int] | None = None
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]")


def _build_backlink_index() -> dict[str, int]:
    """Scan every wiki page once and count [[slug]] occurrences. Result is
    cached in-process. Slug = page path relative to WIKI_DIR, without the .md
    extension (e.g. 'concepts/model-context-protocol' for
    wiki/concepts/model-context-protocol.md). Wikilinks may also use bare
    slugs ('model-context-protocol') — those are counted under the bare-slug
    bucket and added to the full-slug count by _compute_centrality.
    """
    counts: dict[str, int] = {}
    for p in _all_wiki_pages():
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in _WIKILINK_RE.finditer(content):
            target = m.group(1).strip()
            counts[target] = counts.get(target, 0) + 1
    return counts


def _compute_centrality(page_path: str) -> int:
    """Return the number of backlinks pointing to `page_path` (relative to
    WIKI_PATH, e.g. 'wiki/concepts/foo.md'). Builds the backlink index lazily;
    subsequent calls reuse the cache. To refresh, set the module-level
    `_BACKLINK_CACHE = None` and call again.
    """
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


def _normalize_query(q: str) -> list[str]:
    """Lowercase, NFC-normalise, split on whitespace and hyphens, drop empties.
    Used by the matching layer to make 'two-words', 'two words', and 'twowords'
    queries behave consistently against the page content.
    """
    q = unicodedata.normalize("NFC", q).lower()
    tokens: list[str] = []
    for chunk in q.replace("-", " ").split():
        if chunk:
            tokens.append(chunk)
    return tokens


def _normalize_haystack(text: str) -> str:
    """Counterpart of _normalize_query for the searched text. Lowercase, NFC,
    collapse hyphens and whitespace to single spaces.
    """
    text = unicodedata.normalize("NFC", text).lower()
    text = text.replace("-", " ")
    text = " ".join(text.split())
    return text


def _all_tokens_present(tokens: list[str], haystack: str) -> bool:
    """True iff every token from _normalize_query is a substring of the
    pre-normalised haystack.
    """
    return all(t in haystack for t in tokens)


def _compact_l0(fm: dict, p) -> str:
    """Compact one-line representation used by scan_<type> outputs.
    Format: '- <slug> — <summary_l0>'. The slug is the page filename
    without the .md extension; the type is left implicit (the caller
    knows it from its own tool name).
    """
    l0 = fm.get("summary_l0", "—") or "—"
    slug = p.stem
    return f"- {slug} — {l0}"


# Map from the directory-style plural name used in the scan_<type> tool to the
# singular value stored in the `type:` frontmatter field.
_TYPE_TOOL_TO_FRONTMATTER = {
    "concepts": "concept",
    "sources": "source",
    "syntheses": "synthesis",
    "entities": "entity",
    "cheatsheets": "cheatsheet",
    "decisions": "decision",
    "diagrams": "diagram",
}


@mcp.tool(
    description=(
        "Use FIRST before answering any question about the user's knowledge domains. "
        "Returns a compact hierarchical overview of a domain: the hub page (summary_l1), "
        "page counts by type, and the top 10 pages by centrality (incoming wikilinks). "
        "Use scan_concepts / scan_entities / scan_<type>(domain, query=...) to drill down. "
        "domain: a domain slug declared in the vault's CLAUDE.md (e.g. one of the slugs "
        "listed in `wiki/domains/`)."
    )
)
def scan_domain(domain: str) -> str:
    pages = _domain_pages(domain)
    if not pages:
        return f"Aucune page trouvée pour le domaine « {domain} »."

    # Hub page lookup: wiki/domains/<domain>.md with type: domain
    hub_path = WIKI_DIR / "domains" / f"{domain}.md"
    hub_l1 = ""
    if hub_path.exists():
        try:
            hub_fm, _ = _parse_front(hub_path.read_text(encoding="utf-8"))
            hub_l1 = hub_fm.get("summary_l1", "") or ""
        except Exception:
            hub_l1 = ""

    # Counts by type (frontmatter `type:` value, lowercased and trimmed)
    counts: dict[str, int] = {}
    for p in pages:
        try:
            fm, _ = _parse_front(p.read_text(encoding="utf-8"))
            t = str(fm.get("type", "")).strip().lower()
            counts[t] = counts.get(t, 0) + 1
        except Exception:
            continue

    # Top 10 pages by centrality (backlinks)
    ranked: list[tuple[int, Path, dict]] = []
    for p in pages:
        try:
            fm, _ = _parse_front(p.read_text(encoding="utf-8"))
        except Exception:
            fm = {}
        rel = str(p.relative_to(WIKI_PATH))
        c = _compute_centrality(rel)
        ranked.append((c, p, fm))
    ranked.sort(key=lambda x: x[0], reverse=True)
    top = ranked[:10]

    # Assemble the response
    lines = [f"# Domaine {domain} ({len(pages)} pages)\n"]
    if hub_l1:
        lines.append("## Hub\n")
        lines.append(hub_l1.strip())
        lines.append("")

    lines.append("## Structure")
    type_to_tool = {v: k for k, v in _TYPE_TOOL_TO_FRONTMATTER.items()}
    sorted_counts = sorted(counts.items(), key=lambda kv: -kv[1])
    for t, n in sorted_counts:
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
    for c, p, fm in top:
        slug = p.stem
        rel_dir = str(p.parent.relative_to(WIKI_DIR))
        t = fm.get("type", "")
        l0 = fm.get("summary_l0", "—") or "—"
        lines.append(f"- {rel_dir}/{slug} ({t}, {c} backlinks) — {l0}")

    return "\n".join(lines)


def _scan_type_impl(domain: str, type_singular: str, type_plural: str, query: str, top: int) -> str:
    """Shared implementation for scan_concepts, scan_entities, scan_decisions,
    scan_syntheses, scan_cheatsheets, scan_diagrams. scan_sources wraps this
    too but adds a refusal path for empty queries.
    """
    pages = []
    for p in _domain_pages(domain):
        try:
            fm, body = _parse_front(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(fm.get("type", "")).strip().lower() != type_singular:
            continue
        pages.append((p, fm, body))

    if not pages:
        return f"Aucune page de type « {type_singular} » dans le domaine « {domain} »."

    if query.strip():
        tokens = _normalize_query(query)
        scored = []
        for p, fm, body in pages:
            haystack_parts = [
                str(fm.get("summary_l0", "")),
                str(fm.get("summary_l1", "")),
                p.stem,
                body,
            ]
            haystack = _normalize_haystack(" ".join(haystack_parts))
            if _all_tokens_present(tokens, haystack):
                centrality = _compute_centrality(str(p.relative_to(WIKI_PATH)))
                scored.append((centrality, p, fm))
        scored.sort(key=lambda x: x[0], reverse=True)
        kept = scored[:top]
        if not kept:
            return f"Aucune page de type « {type_singular} » dans « {domain} » ne matche « {query} »."
    else:
        ranked = []
        for p, fm, _body in pages:
            centrality = _compute_centrality(str(p.relative_to(WIKI_PATH)))
            ranked.append((centrality, p, fm))
        ranked.sort(key=lambda x: x[0], reverse=True)
        kept = ranked[:top]

    header = (
        f"# {type_plural} dans {domain} — top {len(kept)}"
        + (f" pour « {query} »" if query.strip() else " par centralité")
    )
    lines = [header, ""]
    for _c, p, fm in kept:
        lines.append(_compact_l0(fm, p))
    return "\n".join(lines)


@mcp.tool(
    description=(
        "List concepts in a domain. Without query: top N by centrality (backlinks). "
        "With query: only concepts whose title/body/summary contain all tokens "
        "(case + separator insensitive), ranked by centrality. Use after scan_domain "
        "to drill into the concept layer."
    )
)
def scan_concepts(domain: str, query: str = "", top: int = 20) -> str:
    return _scan_type_impl(domain, "concept", "Concepts", query, top)


@mcp.tool(
    description="List entities (people, tools, places, organisations) in a domain. Same semantics as scan_concepts."
)
def scan_entities(domain: str, query: str = "", top: int = 20) -> str:
    return _scan_type_impl(domain, "entity", "Entities", query, top)


@mcp.tool(
    description="List decisions (ADRs, retained tradeoffs) in a domain. Same semantics as scan_concepts."
)
def scan_decisions(domain: str, query: str = "", top: int = 20) -> str:
    return _scan_type_impl(domain, "decision", "Decisions", query, top)


@mcp.tool(
    description="List syntheses (cross-cutting summaries) in a domain. Same semantics as scan_concepts."
)
def scan_syntheses(domain: str, query: str = "", top: int = 20) -> str:
    return _scan_type_impl(domain, "synthesis", "Syntheses", query, top)


@mcp.tool(
    description="List cheatsheets (quick-reference how-tos) in a domain. Same semantics as scan_concepts."
)
def scan_cheatsheets(domain: str, query: str = "", top: int = 20) -> str:
    return _scan_type_impl(domain, "cheatsheet", "Cheatsheets", query, top)


@mcp.tool(
    description="List diagrams (visual artefacts) in a domain. Same semantics as scan_concepts."
)
def scan_diagrams(domain: str, query: str = "", top: int = 20) -> str:
    return _scan_type_impl(domain, "diagram", "Diagrams", query, top)


@mcp.tool(
    description=(
        "List source pages in a domain. UNLIKE scan_concepts/entities/etc., "
        "scan_sources REQUIRES a non-empty query — sources are typically too "
        "numerous to enumerate usefully without a target. With query: only "
        "sources whose title/body/summary contain all tokens, ranked by centrality."
    )
)
def scan_sources(domain: str, query: str = "", top: int = 20) -> str:
    if not query.strip():
        n_sources = sum(
            1 for p in _domain_pages(domain)
            if _safe_get_type(p) == "source"
        )
        return (
            f"scan_sources(\"{domain}\") sans query retournerait {n_sources} sources, peu utile.\n"
            f"Préciser une query : scan_sources(\"{domain}\", query=\"<topic>\").\n"
            f"Pour explorer le domaine sans cible, préférer scan_domain(\"{domain}\") "
            f"ou scan_concepts(\"{domain}\")."
        )
    return _scan_type_impl(domain, "source", "Sources", query, top)


def _safe_get_type(p) -> str:
    try:
        fm, _ = _parse_front(p.read_text(encoding="utf-8"))
        return str(fm.get("type", "")).strip().lower()
    except Exception:
        return ""


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
    # Whitelist: caps verbosity — verdict_evidence, verdict_date, revisit_after intentionally skipped.
    preview_fields = ("type", "domains", "created", "updated", "summary_l0",
                      "sources", "status", "verdict")
    for k in preview_fields:
        if k in fm:
            lines.append(f"**{k}**: {fm[k]}")
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


def _outgoing_wikilinks(body: str, limit: int = 10) -> list[str]:
    seen: list[str] = []
    seen_set: set[str] = set()
    for m in _WIKILINK_RE.finditer(body):
        slug = m.group(1).strip()
        if slug in seen_set:
            continue
        seen_set.add(slug)
        seen.append(slug)
        if len(seen) >= limit:
            break
    return seen


@mcp.tool(
    description=(
        "Full-text tokenised search across all wiki pages. Cross-type, "
        "cross-domain. Returns up to `limit` matching pages with path, type, "
        "summary_l0, and up to 3 outgoing wikilinks per result for quick "
        "navigation. Use this for natural-language queries that are not "
        "domain-scoped; use scan_<type>(domain, query=...) for domain-scoped "
        "drill-downs. Query is tokenised (case + separator insensitive: 'two "
        "words' matches 'two-words' and 'twowords'). Results are ranked by "
        "centrality (incoming wikilinks)."
    )
)
def search_wiki(query: str, limit: int = 10) -> str:
    tokens = _normalize_query(query)
    if not tokens:
        return "Requête vide."
    scored: list[tuple[int, Path, dict, str]] = []
    for p in _all_wiki_pages():
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
        fm, body = _parse_front(content)
        haystack_parts = [
            str(fm.get("summary_l0", "")),
            str(fm.get("summary_l1", "")),
            p.stem,
            body,
        ]
        haystack = _normalize_haystack(" ".join(haystack_parts))
        if _all_tokens_present(tokens, haystack):
            centrality = _compute_centrality(str(p.relative_to(WIKI_PATH)))
            scored.append((centrality, p, fm, body))
    scored.sort(key=lambda x: x[0], reverse=True)
    kept = scored[:limit]
    if not kept:
        return f"Aucun résultat pour « {query} »."
    lines = [f"# Résultats pour « {query} » ({len(kept)})", ""]
    for _c, p, fm, body in kept:
        rel = str(p.relative_to(WIKI_PATH))
        t = fm.get("type", "")
        l0 = fm.get("summary_l0", "—") or "—"
        wikilinks = _outgoing_wikilinks(body, limit=3)
        wikilinks_str = ", ".join(wikilinks) if wikilinks else "—"
        lines.append(f"- {rel} ({t}) — {l0} — wikilinks: [{wikilinks_str}]")
    return "\n".join(lines)


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
