#!/usr/bin/env python3
"""mcp-wiki.py — MCP server (stdio) exposing the BoilingBrain wiki via FastMCP.

Thin wrapper layer: all query logic lives in wiki_core (dependency-free, also
used by wiki-cli.py). Each read tool delegates to wiki_core.<tool>_data + _md and
catches WikiLookupError to preserve the legacy plain-string error behaviour.

For headless / scriptable access without an MCP client, see wiki-cli.py.

Usage:
  Launched automatically by Claude Code (registered via `claude mcp add`).
  Set WIKI_PATH env var to override the vault root path.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wiki_core  # noqa: E402

from fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("boiling-brain-wiki")


def _md(md_fn, data_fn, *args, **kwargs):
    """Delegate to wiki_core: render data via md_fn, mapping WikiLookupError back
    to the legacy plain-string return so the MCP output is unchanged."""
    try:
        return md_fn(data_fn(*args, **kwargs))
    except wiki_core.WikiLookupError as e:
        return str(e)


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
    return _md(wiki_core.scan_domain_md, wiki_core.scan_domain_data, domain)


@mcp.tool(
    description=(
        "List concepts in a domain. Without query: top N by centrality (backlinks). "
        "With query: only concepts whose title/body/summary contain all tokens "
        "(case + separator insensitive), ranked by centrality. Use after scan_domain "
        "to drill into the concept layer."
    )
)
def scan_concepts(domain: str, query: str = "", top: int = 20) -> str:
    return _md(wiki_core.scan_type_md, wiki_core.scan_type_data, domain, "concept", query, top)


@mcp.tool(
    description="List entities (people, tools, places, organisations) in a domain. Same semantics as scan_concepts."
)
def scan_entities(domain: str, query: str = "", top: int = 20) -> str:
    return _md(wiki_core.scan_type_md, wiki_core.scan_type_data, domain, "entity", query, top)


@mcp.tool(
    description="List decisions (ADRs, retained tradeoffs) in a domain. Same semantics as scan_concepts."
)
def scan_decisions(domain: str, query: str = "", top: int = 20) -> str:
    return _md(wiki_core.scan_type_md, wiki_core.scan_type_data, domain, "decision", query, top)


@mcp.tool(
    description="List syntheses (cross-cutting summaries) in a domain. Same semantics as scan_concepts."
)
def scan_syntheses(domain: str, query: str = "", top: int = 20) -> str:
    return _md(wiki_core.scan_type_md, wiki_core.scan_type_data, domain, "synthesis", query, top)


@mcp.tool(
    description="List cheatsheets (quick-reference how-tos) in a domain. Same semantics as scan_concepts."
)
def scan_cheatsheets(domain: str, query: str = "", top: int = 20) -> str:
    return _md(wiki_core.scan_type_md, wiki_core.scan_type_data, domain, "cheatsheet", query, top)


@mcp.tool(
    description="List diagrams (visual artefacts) in a domain. Same semantics as scan_concepts."
)
def scan_diagrams(domain: str, query: str = "", top: int = 20) -> str:
    return _md(wiki_core.scan_type_md, wiki_core.scan_type_data, domain, "diagram", query, top)


@mcp.tool(
    description=(
        "List source pages in a domain. UNLIKE scan_concepts/entities/etc., "
        "scan_sources REQUIRES a non-empty query — sources are typically too "
        "numerous to enumerate usefully without a target. With query: only "
        "sources whose title/body/summary contain all tokens, ranked by centrality."
    )
)
def scan_sources(domain: str, query: str = "", top: int = 20) -> str:
    return _md(wiki_core.scan_type_md, wiki_core.scan_sources_data, domain, query, top)


@mcp.tool(
    description=(
        "Preview a wiki page: frontmatter fields + summary_l1 (2-5 sentence description). "
        "Use after scan_domain to assess relevance before reading the full body. "
        "page_path: relative path from vault root, e.g. 'wiki/concepts/my-concept.md'."
    )
)
def preview_page(page_path: str) -> str:
    return _md(wiki_core.preview_page_md, wiki_core.preview_page_data, page_path)


@mcp.tool(
    description=(
        "Read the full content of a wiki page. "
        "Use after preview_page when the summary confirms relevance. "
        "page_path: relative path from vault root, e.g. 'wiki/sources/2026-01-15-my-source.md'."
    )
)
def read_page(page_path: str) -> str:
    return _md(wiki_core.read_page_md, wiki_core.read_page_data, page_path)


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
    return _md(wiki_core.search_wiki_md, wiki_core.search_wiki_data, query, limit)


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
        dest_dir = (wiki_core.RAW_DIR / subfolder).resolve()
        if not str(dest_dir).startswith(str(wiki_core.RAW_DIR.resolve())):
            return "Erreur : sous-dossier invalide (path traversal détecté)."
        dest_file = (dest_dir / filename).resolve()
        if not str(dest_file).startswith(str(dest_dir)):
            return "Erreur : nom de fichier invalide (path traversal détecté)."
    except Exception as e:
        return f"Erreur de validation du chemin : {e}"

    if dest_file.exists():
        return f"Fichier déjà existant : {dest_file.relative_to(wiki_core.WIKI_PATH)}. Utilise un autre nom."

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file.write_text(content, encoding="utf-8")

    # Signal for SessionStart hook
    wiki_core.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pending = wiki_core.CACHE_DIR / ".pending-ingest"
    rel_path = str(dest_file.relative_to(wiki_core.WIKI_PATH))
    with open(pending, "a", encoding="utf-8") as f:
        f.write(rel_path + "\n")

    return f"Fichier créé : {rel_path}\nSignal .pending-ingest mis à jour."


if __name__ == "__main__":
    mcp.run(transport="stdio")
