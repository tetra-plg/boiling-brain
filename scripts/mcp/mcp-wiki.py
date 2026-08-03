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
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wiki_core  # noqa: E402
import ingest_jobs  # noqa: E402

from fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("boiling-brain-wiki")

INGEST_TIMEOUT_S = ingest_jobs.TIMEOUT_S  # single source of truth (#124)
INGEST_PERMISSION_MODE = os.environ.get("MCP_INGEST_PERMISSION_MODE", "")

# Formats the ingestion engine can consume: markdown/text and PDF natively,
# png/jpg images natively, audio/video through /ingest-video, docx/pptx through
# the markdown-twin conversion of /ingest (scripts/convert-doc.sh). The deposit
# channel must offer the same surface — any asymmetry between the two is a
# design bug (#112).
INGESTIBLE_EXT = (
    ".md", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".docx", ".pptx", ".m4a", ".mp4", ".wav",
)


def _allowed_source_roots():
    """Directories drop_file_to_raw is allowed to read from.

    Defaults to the vault owner's home — wide enough for Downloads and for a
    client app's working folder, narrow enough that the tool never becomes an
    arbitrary file reader for any MCP client. Override with
    LLMWIKI_DROP_SOURCE_ROOTS (os.pathsep-separated list of directories).
    Read at call time, so retargeting it doesn't require a server restart."""
    raw = os.environ.get("LLMWIKI_DROP_SOURCE_ROOTS", "")
    parts = [p for p in raw.split(os.pathsep) if p.strip()] or [str(Path.home())]
    roots = []
    for p in parts:
        try:
            roots.append(Path(p).expanduser().resolve())
        except Exception:
            continue
    return roots


def _vault_rel(p: Path) -> str:
    """Vault-relative form of an absolute path, tolerant of an unresolved
    WIKI_PATH (symlinked temp roots on macOS: /var -> /private/var)."""
    try:
        return str(p.relative_to(wiki_core.WIKI_PATH.resolve()))
    except ValueError:
        return str(p)


def _within(child: Path, parent: Path) -> bool:
    """True when child is parent itself or sits under it.

    Compared component-wise, never as a string prefix: `str.startswith` lets a
    sibling directory whose name extends the parent's slip through — subfolder
    "../rawbis" resolves to <vault>/rawbis, whose string does start with
    <vault>/raw, and the write lands outside raw/."""
    return child == parent or parent in child.parents


def _resolve_raw_dest(subfolder: str, filename: str):
    """Resolve raw/<subfolder>/<filename>, guarding both segments against path
    traversal. Returns ((dest_dir, dest_file), None) or (None, error message)."""
    try:
        raw_root = wiki_core.RAW_DIR.resolve()
        dest_dir = (wiki_core.RAW_DIR / subfolder).resolve()
        if not _within(dest_dir, raw_root):
            return None, "Error: invalid subfolder (path traversal detected)."
        dest_file = (dest_dir / filename).resolve()
        if not _within(dest_file, dest_dir):
            return None, "Error: invalid filename (path traversal detected)."
    except Exception as e:
        return None, f"Path validation error: {e}"
    return (dest_dir, dest_file), None


def _signal_pending(dest_file: Path) -> str:
    """Append the deposited path to cache/.pending-ingest (SessionStart signal)
    and return its vault-relative form."""
    wiki_core.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pending = wiki_core.CACHE_DIR / ".pending-ingest"
    rel_path = _vault_rel(dest_file)
    with open(pending, "a", encoding="utf-8") as f:
        f.write(rel_path + "\n")
    return rel_path


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
    resolved, err = _resolve_raw_dest(subfolder, filename)
    if err:
        return err
    dest_dir, dest_file = resolved

    if dest_file.exists():
        return f"File already exists: {_vault_rel(dest_file)}. Use another name."

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file.write_text(content, encoding="utf-8")

    rel_path = _signal_pending(dest_file)
    return f"File created: {rel_path}\n.pending-ingest signal updated."


@mcp.tool(
    description=(
        "Copy an existing local file into raw/ and signal it for ingestion. "
        "The binary counterpart of drop_to_raw: use it for PDFs, images, "
        "docx/pptx documents, audio and video — anything drop_to_raw's text-only "
        "content parameter cannot carry. The server runs on the vault machine "
        "and copies the file server-side. DESKTOP clients (files already on "
        "the vault machine): a direct call on the local path is the nominal "
        "path. CLOUD sessions (Claude Cowork in the cloud): an attachment "
        "lives in the session container, NOT on the vault machine — this tool "
        "cannot see it; first commit/save it into the project working folder "
        "on the vault machine, then call this tool with that path. "
        "source_path: absolute (or ~-prefixed) path of the file to deposit; it "
        "must sit under an allowed source root ($HOME by default, override with "
        "the LLMWIKI_DROP_SOURCE_ROOTS env var) and carry an extension the "
        "ingestion engine consumes. "
        "subfolder: subpath under raw/ (e.g. 'pdfs', 'documents', 'clippings'). "
        "The original is left in place (a copy, not a move) and the target "
        "filename is taken from the source — an existing file is never "
        "overwritten, raw/ being immutable. Creates cache/.pending-ingest with "
        "the new file path; run /ingest (or the ingest() tool) to actually "
        "ingest it. See tetra-plg/boiling-brain#112."
    )
)
def drop_file_to_raw(source_path: str, subfolder: str) -> str:
    try:
        src = Path(source_path).expanduser().resolve()
    except Exception as e:
        return f"Path validation error: {e}"

    # Source allowlist, checked on the symlink-resolved path so a link planted
    # inside an allowed root can't smuggle a file out of it.
    roots = _allowed_source_roots()
    if not roots:
        return ("Error: no usable source root — LLMWIKI_DROP_SOURCE_ROOTS lists "
                "no resolvable directory.")
    if not any(_within(src, r) for r in roots):
        return (f"Error: source path outside the allowed source roots "
                f"({os.pathsep.join(str(r) for r in roots)}). If this file is "
                f"an attachment in a CLOUD session, it lives in the session "
                f"container, not on the vault machine — first commit/save it "
                f"into the project working folder on the vault machine, then "
                f"retry with that path. For a genuinely local file, set "
                f"LLMWIKI_DROP_SOURCE_ROOTS to widen the roots.")

    if _within(src, wiki_core.RAW_DIR.resolve()):
        return "Error: source is already inside raw/ — nothing to deposit."
    if not src.exists():
        return (f"Error: file not found: {source_path}. If this is a "
                f"cloud-session attachment path, the file lives in the session "
                f"container — first commit/save it into the project working "
                f"folder on the vault machine, then retry with that path.")
    if not src.is_file():
        return f"Error: not a regular file: {source_path}."
    if src.suffix.lower() not in INGESTIBLE_EXT:
        return (f"Error: unsupported file type \"{src.suffix}\" — the ingestion "
                f"engine consumes {', '.join(INGESTIBLE_EXT)}.")

    resolved, err = _resolve_raw_dest(subfolder, src.name)
    if err:
        return err
    dest_dir, dest_file = resolved

    if dest_file.exists():
        return (f"File already exists: {_vault_rel(dest_file)}. raw/ is immutable — "
                f"deposit the new version under another name.")

    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, dest_file)
    except OSError as e:
        return f"Error: could not copy {source_path} ({e})."

    rel_path = _signal_pending(dest_file)
    return f"File copied: {rel_path}\n.pending-ingest signal updated."


@mcp.tool(
    description=(
        "Trigger ingestion of a file already present in raw/ (e.g. just written via "
        "drop_to_raw) into the wiki, via a headless domain-expert agent run. Blocks "
        "until the run completes (can take minutes for cross-domain sources). "
        "path: relative path from vault root, e.g. 'raw/notes/2026-07-02-my-note.md'. "
        "domain_hint: domain slug (see list_domains()) — strongly recommended. "
        "Without it an ambiguous or cross-domain source is deferred to "
        "needs-human-triage and produces NO pages (the report says so and "
        "names the fix); the file stays pending for a future run instead of "
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
    prompt, err = ingest_jobs.validate_request(path, domain_hint)
    if err:
        return err

    # Resolve the CLI with shutil.which before building the command. On Windows
    # the CLI ships as a claude.CMD shim; subprocess.run(shell=False) uses
    # CreateProcess, which does NOT consult PATHEXT, so a bare "claude" raises
    # FileNotFoundError even when it is on PATH. shutil.which honours PATHEXT and
    # returns the full path (also correct on POSIX); shell=False is preserved, so
    # no command-injection surface is reintroduced. (#84)
    claude_exe = shutil.which("claude")
    if claude_exe is None:
        return "Error: `claude` CLI not found in the MCP server environment."

    cmd = [claude_exe, "-p", prompt, "--settings", _ingest_settings_json()]
    if INGEST_PERMISSION_MODE:
        cmd += ["--permission-mode", INGEST_PERMISSION_MODE]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=INGEST_TIMEOUT_S,
            cwd=str(wiki_core.WIKI_PATH))
    except subprocess.TimeoutExpired:
        return f"Error: ingestion of {path} aborted after {INGEST_TIMEOUT_S}s (timeout)."
    except FileNotFoundError:
        return "Error: `claude` CLI not found in the MCP server environment."
    except Exception as e:
        return f"Error: ingestion of {path} aborted unexpectedly ({e})."

    if result.returncode != 0:
        detail = result.stderr.strip() or "non-zero exit code, no detail on stderr."
        return f"Error: ingestion of {path} failed ({detail})"

    return result.stdout


@mcp.tool(
    description=(
        "Start a HEADLESS ingestion as a background job and return immediately "
        "with a job id — use this instead of ingest() when the run may exceed "
        "your client's tool-call timeout (real runs routinely take minutes). "
        "Same validation and guardrails as ingest() (path must live under raw/, "
        "PreToolUse allowlist hook always active, MCP_INGEST_PERMISSION_MODE "
        "opt-in). Pass a domain_hint from list_domains() — without it an "
        "ambiguous source is deferred to needs-human-triage and the run "
        "produces no pages. One job at a time: starting while a job is running "
        "returns an error naming the running job. Poll ingest_status(job_id) "
        "for the report."
    )
)
def ingest_start(path: str, domain_hint: str = "") -> str:
    prompt, err = ingest_jobs.validate_request(path, domain_hint)
    if err:
        return err
    claude_exe = shutil.which("claude")
    if claude_exe is None:
        return "Error: `claude` CLI not found in the MCP server environment."
    cmd = [claude_exe, "-p", prompt, "--settings", _ingest_settings_json()]
    if INGEST_PERMISSION_MODE:
        cmd += ["--permission-mode", INGEST_PERMISSION_MODE]
    return ingest_jobs.start(cmd, path)


@mcp.tool(
    description=(
        "Poll a background ingestion started with ingest_start(). Returns "
        "'running' with elapsed seconds, the same final report sync ingest() "
        "produces (with its machine-parseable '## Pages' block) once done, an "
        "error with a stderr excerpt on failure, or a timeout notice (the job "
        "is bounded by the same 600s watchdog as sync ingest(), enforced "
        "when polled)."
    )
)
def ingest_status(job_id: str) -> str:
    return ingest_jobs.status(job_id)


@mcp.tool(
    description=(
        "Cancel a background ingestion started with ingest_start(): terminates "
        "the child run (SIGTERM, then SIGKILL after 5s) and frees the "
        "single-job slot. Idempotent on an already-finished job (returns its "
        "final state instead of failing)."
    )
)
def ingest_cancel(job_id: str) -> str:
    return ingest_jobs.cancel(job_id)


if __name__ == "__main__":
    mcp.run(transport="stdio")
