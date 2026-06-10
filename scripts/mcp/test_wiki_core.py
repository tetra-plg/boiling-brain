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


if __name__ == "__main__":
    unittest.main()
