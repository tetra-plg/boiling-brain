#!/usr/bin/env python3
"""unittest suite for wiki_core.py — drives the pure query layer on a temp vault.

Run: cd scripts/mcp && python3 -m unittest test_wiki_core
Does NOT require fastmcp (the parity test self-skips if fastmcp is absent).
"""
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wiki_core  # noqa: E402


# A small, deterministic vault. Backlink counts (full-slug):
#   concepts/alpha : demo(1) + beta(2) + acme(1) = 4
#   concepts/beta  : demo(1) + alpha(1)          = 2
#   others                                        = 0
PAGES = {
    "domains/demo.md": textwrap.dedent("""\
        ---
        type: domain
        domains: [demo]
        summary_l0: "Demo domain hub"
        summary_l1: "Hub of the demo domain for tests."
        ---
        # Demo
        See [[concepts/alpha]] and [[concepts/beta]].
        """),
    "concepts/alpha.md": textwrap.dedent("""\
        ---
        type: concept
        domains: [demo]
        created: 2026-01-01
        summary_l0: "Alpha concept"
        summary_l1: "Alpha is the central concept."
        ---
        # Alpha
        Links to [[concepts/beta]].
        """),
    "concepts/beta.md": textwrap.dedent("""\
        ---
        type: concept
        domains: [demo]
        created: 2026-01-02
        summary_l0: "Beta concept"
        ---
        # Beta
        Refers to [[concepts/alpha]] then [[concepts/alpha]] again.
        """),
    "entities/acme.md": textwrap.dedent("""\
        ---
        type: entity
        domains: [demo]
        summary_l0: "Acme org"
        ---
        # Acme
        Uses [[concepts/alpha]].
        """),
    "sources/2026-01-03-doc.md": textwrap.dedent("""\
        ---
        type: source
        domains: [demo]
        summary_l0: "A source doc"
        ---
        # Source
        Mentions alpha and beta.
        """),
}


def make_vault(tmp: Path, pages: dict):
    """pages: {relpath_under_wiki: file_body}. Builds the wiki/ tree."""
    for rel, body in pages.items():
        p = tmp / "wiki" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


class WikiCoreTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name)
        make_vault(self.vault, PAGES)
        wiki_core.configure(self.vault)

    def tearDown(self):
        self._tmp.cleanup()


class TestHelpers(WikiCoreTestBase):
    def test_centrality_counts_backlinks(self):
        self.assertEqual(wiki_core._compute_centrality("wiki/concepts/alpha.md"), 4)
        self.assertEqual(wiki_core._compute_centrality("wiki/concepts/beta.md"), 2)
        self.assertEqual(wiki_core._compute_centrality("wiki/entities/acme.md"), 0)

    def test_domain_pages_filters_by_frontmatter(self):
        rels = sorted(str(p.relative_to(self.vault)) for p in wiki_core._domain_pages("demo"))
        self.assertEqual(len(rels), 5)
        self.assertIn("wiki/concepts/alpha.md", rels)
        self.assertEqual(wiki_core._domain_pages("nope"), [])


class TestReadPage(WikiCoreTestBase):
    def test_read_returns_full_content(self):
        data = wiki_core.read_page_data("wiki/concepts/alpha.md")
        self.assertEqual(data["page_path"], "wiki/concepts/alpha.md")
        self.assertIn("# Alpha", data["content"])
        self.assertEqual(wiki_core.read_page_md(data), data["content"])

    def test_read_missing_raises(self):
        with self.assertRaises(wiki_core.WikiLookupError) as ctx:
            wiki_core.read_page_data("wiki/concepts/ghost.md")
        self.assertEqual(str(ctx.exception), "Page introuvable : wiki/concepts/ghost.md")

    def test_read_path_traversal_raises(self):
        with self.assertRaises(wiki_core.WikiLookupError) as ctx:
            wiki_core.read_page_data("../../etc/passwd")
        self.assertIn("path traversal", str(ctx.exception))


class TestPreviewPage(WikiCoreTestBase):
    def test_preview_with_summary_l1(self):
        data = wiki_core.preview_page_data("wiki/concepts/alpha.md")
        self.assertEqual(data["frontmatter"]["type"], "concept")
        self.assertEqual(data["summary_l1"], "Alpha is the central concept.")
        self.assertIsNone(data["body_snippet"])
        md = wiki_core.preview_page_md(data)
        self.assertTrue(md.startswith("# Preview : wiki/concepts/alpha.md"))
        self.assertIn("**type**: concept", md)
        self.assertIn("## summary_l1\nAlpha is the central concept.", md)

    def test_preview_without_summary_l1_falls_back_to_snippet(self):
        # beta.md has no summary_l1
        data = wiki_core.preview_page_data("wiki/concepts/beta.md")
        self.assertEqual(data["summary_l1"], "")
        self.assertIsNotNone(data["body_snippet"])
        self.assertIn("## Début de page", wiki_core.preview_page_md(data))

    def test_preview_missing_raises(self):
        with self.assertRaises(wiki_core.WikiLookupError):
            wiki_core.preview_page_data("wiki/concepts/ghost.md")


class TestSearchWiki(WikiCoreTestBase):
    def test_search_ranks_by_centrality_and_uses_canonical_path(self):
        data = wiki_core.search_wiki_data("alpha")
        self.assertEqual(data["query"], "alpha")
        paths = [r["path"] for r in data["results"]]
        # alpha (4 backlinks) ranks before beta (2); paths are 'wiki/....md'
        self.assertTrue(all(p.startswith("wiki/") and p.endswith(".md") for p in paths))
        self.assertLess(paths.index("wiki/concepts/alpha.md"),
                        paths.index("wiki/concepts/beta.md"))
        self.assertEqual(data["results"][0]["backlinks"], 4)

    def test_search_no_match_is_empty_not_error(self):
        data = wiki_core.search_wiki_data("zzzznomatch")
        self.assertEqual(data["results"], [])
        self.assertEqual(wiki_core.search_wiki_md(data),
                         "Aucun résultat pour « zzzznomatch ».")

    def test_search_empty_query_raises(self):
        with self.assertRaises(wiki_core.WikiLookupError) as ctx:
            wiki_core.search_wiki_data("   ")
        self.assertEqual(str(ctx.exception), "Requête vide.")

    def test_search_null_summary_l0_renders_dash(self):
        # A page whose summary_l0 is explicitly null must render "—", not "None".
        extra = self.vault / "wiki" / "concepts" / "nullsum.md"
        extra.write_text(
            "---\ntype: concept\ndomains: [demo]\nsummary_l0: null\n---\n"
            "# Nullsum\nUniquetokenxyz here.\n", encoding="utf-8")
        wiki_core.configure(self.vault)  # reset caches after adding a file
        data = wiki_core.search_wiki_data("uniquetokenxyz")
        self.assertEqual(data["results"][0]["summary_l0"], "")
        md = wiki_core.search_wiki_md(data)
        self.assertIn("(concept) — — — wikilinks:", md)
        self.assertNotIn("None", md)


class TestScanType(WikiCoreTestBase):
    def test_concepts_ranked_by_centrality(self):
        data = wiki_core.scan_type_data("demo", "concept")
        slugs = [r["slug"] for r in data["results"]]
        self.assertEqual(slugs, ["alpha", "beta"])  # 4 backlinks before 2
        md = wiki_core.scan_type_md(data)
        self.assertTrue(md.startswith("# Concepts dans demo — top 2 par centralité"))
        self.assertIn("- alpha — Alpha concept", md)

    def test_concepts_with_query_header(self):
        data = wiki_core.scan_type_data("demo", "concept", query="alpha")
        md = wiki_core.scan_type_md(data)
        self.assertIn("pour « alpha »", md)

    def test_empty_domain_raises(self):
        with self.assertRaises(wiki_core.WikiLookupError) as ctx:
            wiki_core.scan_type_data("nope", "concept")
        self.assertEqual(str(ctx.exception),
                         "Aucune page de type « concept » dans le domaine « nope ».")

    def test_type_absent_in_populated_domain_is_empty(self):
        data = wiki_core.scan_type_data("demo", "diagram")  # no diagrams in demo
        self.assertEqual(data["results"], [])
        self.assertEqual(data["_reason"], "no_typed")
        self.assertEqual(wiki_core.scan_type_md(data),
                         "Aucune page de type « diagram » dans le domaine « demo ».")

    def test_query_no_match_is_empty(self):
        data = wiki_core.scan_type_data("demo", "concept", query="zzzz")
        self.assertEqual(data["results"], [])
        self.assertEqual(data["_reason"], "no_match")
        self.assertIn("ne matche « zzzz »", wiki_core.scan_type_md(data))

    def test_scan_sources_without_query_raises_guidance(self):
        with self.assertRaises(wiki_core.WikiLookupError) as ctx:
            wiki_core.scan_sources_data("demo")
        self.assertIn("sans query retournerait 1 sources", str(ctx.exception))

    def test_scan_sources_with_query(self):
        data = wiki_core.scan_sources_data("demo", query="source")
        self.assertEqual(data["type"], "source")
        self.assertEqual(len(data["results"]), 1)

    def test_to_json_strips_underscore_keys(self):
        import json as _json
        data = wiki_core.scan_type_data("demo", "diagram")  # has _reason
        parsed = _json.loads(wiki_core.to_json(data))
        self.assertNotIn("_reason", parsed)
        self.assertEqual(parsed["results"], [])


class TestScanDomain(WikiCoreTestBase):
    def test_domain_overview_structure(self):
        data = wiki_core.scan_domain_data("demo")
        self.assertEqual(data["page_count"], 5)
        self.assertEqual(data["hub_summary_l1"], "Hub of the demo domain for tests.")
        # counts sorted by -n: concept(2) first
        self.assertEqual(data["counts"][0], {"type": "concept", "n": 2})
        # top_central ranked by backlinks, canonical paths
        self.assertEqual(data["top_central"][0]["path"], "wiki/concepts/alpha.md")
        self.assertEqual(data["top_central"][0]["backlinks"], 4)

    def test_domain_md_rendering(self):
        md = wiki_core.scan_domain_md(wiki_core.scan_domain_data("demo"))
        self.assertTrue(md.startswith("# Domaine demo (5 pages)"))
        self.assertIn("## Hub", md)
        self.assertIn("## Structure", md)
        self.assertIn("- concept: 2 → scan_concepts(\"demo\")", md)
        self.assertIn("## Top 10 pages centrales (par backlinks)", md)
        # display path is rel_dir/slug, not the canonical wiki/...md
        self.assertIn("- concepts/alpha (concept, 4 backlinks) — Alpha concept", md)

    def test_empty_domain_raises(self):
        with self.assertRaises(wiki_core.WikiLookupError) as ctx:
            wiki_core.scan_domain_data("nope")
        self.assertEqual(str(ctx.exception), "Aucune page trouvée pour le domaine « nope ».")


class TestListDomains(WikiCoreTestBase):
    def setUp(self):
        super().setUp()
        agents_dir = self.vault / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "demo-expert.md").write_text(
            "---\nname: demo-expert\n---\n", encoding="utf-8")
        orphan = self.vault / "wiki" / "domains" / "orphan.md"
        orphan.write_text(
            "---\ntype: domain\ndomains: [orphan]\n"
            "summary_l0: \"Orphan domain, no expert yet\"\n---\n# Orphan\n",
            encoding="utf-8")
        wiki_core.configure(self.vault)  # reset caches after adding files

    def test_list_domains_reports_expert_presence(self):
        data = wiki_core.list_domains_data()
        by_slug = {d["slug"]: d for d in data["domains"]}
        self.assertEqual(set(by_slug), {"demo", "orphan"})
        self.assertEqual(by_slug["demo"]["has_expert"], True)
        self.assertEqual(by_slug["demo"]["summary_l0"], "Demo domain hub")
        self.assertEqual(by_slug["orphan"]["has_expert"], False)
        self.assertEqual(by_slug["orphan"]["summary_l0"], "Orphan domain, no expert yet")

    def test_list_domains_md_flags_missing_expert(self):
        md = wiki_core.list_domains_md(wiki_core.list_domains_data())
        self.assertIn("- demo (agent expert disponible) — Demo domain hub", md)
        self.assertIn(
            "- orphan (pas d'agent expert (domain_hint inutilisable)) — "
            "Orphan domain, no expert yet", md)

    def test_list_domains_empty_vault(self):
        empty = tempfile.TemporaryDirectory()
        try:
            wiki_core.configure(Path(empty.name))
            data = wiki_core.list_domains_data()
            self.assertEqual(data["domains"], [])
            self.assertEqual(wiki_core.list_domains_md(data),
                             "Aucun domaine déclaré dans ce vault.")
        finally:
            empty.cleanup()
            wiki_core.configure(self.vault)


import os  # noqa: E402
import importlib.util  # noqa: E402


def _fastmcp_available():
    try:
        import fastmcp  # noqa: F401
        return True
    except Exception:
        return False


_HAS_FASTMCP = _fastmcp_available()


def _load_mcp_module_fresh():
    """Load mcp-wiki.py fresh by path (its hyphenated name isn't importable).
    Its inner `import wiki_core` resolves to the already-imported module, so
    configuring wiki_core also configures what the server sees."""
    spec = importlib.util.spec_from_file_location(
        "mcp_wiki_fresh", str(Path(__file__).resolve().parent / "mcp-wiki.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@unittest.skipUnless(_HAS_FASTMCP, "fastmcp not installed")
class TestMcpParity(WikiCoreTestBase):
    """Byte-for-byte parity between wiki_core *_md(*_data(...)) and the MCP tools."""

    def setUp(self):
        super().setUp()                       # builds vault, configures wiki_core
        # Resolve symlinks (macOS /var -> /private/var) so the vault root matches
        # the canonical paths drop_to_raw derives via Path.resolve(), as a real
        # WIKI_PATH (env var / repo root) would already be canonical.
        self.vault = self.vault.resolve()
        self._prev_env = os.environ.get("WIKI_PATH")
        os.environ["WIKI_PATH"] = str(self.vault)
        self.m = _load_mcp_module_fresh()
        # The rewritten server always delegates to wiki_core; fail loudly if not.
        self.assertTrue(hasattr(self.m, "wiki_core"),
                        "mcp-wiki.py loaded without a wiki_core attribute")
        self.m.wiki_core.configure(self.vault)
        wiki_core.configure(self.vault)

    def tearDown(self):
        if self._prev_env is None:
            os.environ.pop("WIKI_PATH", None)
        else:
            os.environ["WIKI_PATH"] = self._prev_env
        super().tearDown()

    def test_scan_domain_parity(self):
        self.assertEqual(self.m.scan_domain("demo"),
                         wiki_core.scan_domain_md(wiki_core.scan_domain_data("demo")))

    def test_scan_concepts_parity(self):
        self.assertEqual(self.m.scan_concepts("demo"),
                         wiki_core.scan_type_md(wiki_core.scan_type_data("demo", "concept")))

    def test_scan_sources_refusal_parity(self):
        self.assertEqual(self.m.scan_sources("demo"),
                         self._safe_md(lambda: wiki_core.scan_sources_data("demo")))

    def test_preview_parity(self):
        self.assertEqual(self.m.preview_page("wiki/concepts/alpha.md"),
                         wiki_core.preview_page_md(wiki_core.preview_page_data("wiki/concepts/alpha.md")))

    def test_read_parity(self):
        self.assertEqual(self.m.read_page("wiki/concepts/alpha.md"),
                         wiki_core.read_page_md(wiki_core.read_page_data("wiki/concepts/alpha.md")))

    def test_search_parity(self):
        self.assertEqual(self.m.search_wiki("alpha"),
                         wiki_core.search_wiki_md(wiki_core.search_wiki_data("alpha")))

    def test_list_domains_parity(self):
        self.assertEqual(self.m.list_domains(),
                         wiki_core.list_domains_md(wiki_core.list_domains_data()))

    def test_missing_page_parity(self):
        self.assertEqual(self.m.read_page("wiki/x/ghost.md"),
                         self._safe_md(lambda: wiki_core.read_page_data("wiki/x/ghost.md")))

    def test_drop_to_raw_writes_file_and_signals(self):
        result = self.m.drop_to_raw("notes", "task7-check.md", "# Hello\nbody\n")
        dest = self.vault / "raw" / "notes" / "task7-check.md"
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_text(encoding="utf-8"), "# Hello\nbody\n")
        self.assertIn("Fichier créé", result)
        pending = (self.vault / "cache" / ".pending-ingest").read_text(encoding="utf-8")
        self.assertIn("raw/notes/task7-check.md", pending)

    def test_drop_to_raw_rejects_path_traversal(self):
        result = self.m.drop_to_raw("../evil", "x.md", "nope")
        self.assertIn("path traversal détecté", result)
        self.assertFalse((self.vault / "raw" / "evil").exists())

    def _safe_md(self, fn):
        try:
            return str(fn())
        except wiki_core.WikiLookupError as e:
            return str(e)


if __name__ == "__main__":
    unittest.main()
