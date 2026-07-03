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
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wiki_core  # noqa: E402

from fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("boiling-brain-wiki")

INGEST_TIMEOUT_S = 600
INGEST_PERMISSION_MODE = os.environ.get("MCP_INGEST_PERMISSION_MODE", "")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _ingest_settings_json():
    """Build a --settings JSON that scopes a PreToolUse allowlist hook to just
    the claude -p session ingest() spawns below. Verified empirically to
    merge with (not replace) the vault's own .claude/settings.json, and to
    apply to subagent tool calls, not just the main context. The matcher
    covers every tool (empty string, this codebase's established
    "match all" convention — see setup-mcp.sh's Stop hook registration) so
    the guard script's own per-tool dispatch — including its default-deny
    for anything it doesn't explicitly recognize — actually runs for every
    tool call, not just Write/Edit/Bash."""
    guard = str(wiki_core.WIKI_PATH / "scripts" / "mcp" / "ingest-headless-guard.sh")
    hook = {"type": "command", "command": guard, "timeout": 3000}
    return json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "", "hooks": [hook]},
    ]}})


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
        "List valid domain slugs for this vault, with a short description and whether "
        "a domain-expert agent exists for it. Call this BEFORE ingest(domain_hint=...) "
        "to know which hints are valid — domains are added/renamed dynamically via "
        "/domain, so hardcoding slugs in a third-party app will drift."
    )
)
def list_domains() -> str:
    return _md(wiki_core.list_domains_md, wiki_core.list_domains_data)


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


@mcp.tool(
    description=(
        "Trigger ingestion of a file already present in raw/ (e.g. just written via "
        "drop_to_raw) into the wiki, via a headless domain-expert agent run. Blocks "
        "until the run completes (can take minutes for cross-domain sources). "
        "path: relative path from vault root, e.g. 'raw/notes/2026-07-02-my-note.md'. "
        "domain_hint: optional domain slug (see list_domains()) to skip expert-agent "
        "disambiguation. If omitted and the source is ambiguous or low-confidence, the "
        "file is left pending for a future interactive /ingest session instead of "
        "being guessed at. "
        "By default this session runs with the caller's normal (unescalated) "
        "permission mode, so headless journaling writes (wiki/log.md, "
        "wiki/radar.md, wiki/index.md) and the final format step may be "
        "blocked with no human present to approve them. To let ingestion "
        "complete unattended, the vault owner must explicitly opt in by "
        "setting the MCP_INGEST_PERMISSION_MODE env var (recommended: "
        "'auto') when registering this MCP server — a deliberate, "
        "durable choice, not a silent default. A PreToolUse allowlist hook "
        "(scripts/mcp/ingest-headless-guard.sh) is always active for this "
        "session regardless, bounding Write/Bash to the ingest workflow's "
        "known operations. See tetra-plg/boiling-brain#62."
    )
)
def ingest(path: str, domain_hint: str = "") -> str:
    if domain_hint and not _SLUG_RE.match(domain_hint):
        return (f"Erreur : domain_hint invalide : « {domain_hint} » — attendu un slug "
                 f"(minuscules, chiffres, tirets). Voir list_domains() pour les valeurs valides.")

    if any(c.isspace() for c in path) or any(part.startswith("-") for part in path.split("/")):
        return (f"Erreur : path invalide : « {path} » — ne doit contenir ni espace ni "
                 f"segment commençant par « - » (risque d'injection de flag dans la commande construite).")

    try:
        target = (wiki_core.WIKI_PATH / path).resolve()
        if not str(target).startswith(str(wiki_core.RAW_DIR.resolve())):
            return "Erreur : chemin invalide (path traversal détecté)."
    except Exception as e:
        return f"Erreur de validation du chemin : {e}"

    if not target.exists():
        return f"Erreur : fichier introuvable : {path}."

    prompt = f"/ingest {path} --headless"
    if domain_hint:
        prompt += f" --domain-hint={domain_hint}"

    cmd = ["claude", "-p", prompt, "--settings", _ingest_settings_json()]
    if INGEST_PERMISSION_MODE:
        cmd += ["--permission-mode", INGEST_PERMISSION_MODE]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=INGEST_TIMEOUT_S,
            cwd=str(wiki_core.WIKI_PATH))
    except subprocess.TimeoutExpired:
        return f"Erreur : ingestion de {path} interrompue après {INGEST_TIMEOUT_S}s (timeout)."
    except FileNotFoundError:
        return "Erreur : CLI `claude` introuvable dans l'environnement du serveur MCP."
    except Exception as e:
        return f"Erreur : ingestion de {path} interrompue de façon inattendue ({e})."

    if result.returncode != 0:
        detail = result.stderr.strip() or "code de sortie non nul, sans détail sur stderr."
        return f"Erreur : l'ingestion de {path} a échoué ({detail})"

    return result.stdout


if __name__ == "__main__":
    mcp.run(transport="stdio")
