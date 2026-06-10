#!/usr/bin/env python3
"""unittest suite for wiki-cli.py — drives the CLI via subprocess on a temp vault.

Run: cd scripts/mcp && python3 -m unittest test_wiki_cli
Requires NO fastmcp (the CLI imports only wiki_core).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parent / "wiki-cli.py"

PAGES = {
    "domains/demo.md": "---\ntype: domain\ndomains: [demo]\nsummary_l1: \"Hub.\"\n---\n# Demo\n[[concepts/alpha]]\n",
    "concepts/alpha.md": "---\ntype: concept\ndomains: [demo]\nsummary_l0: \"Alpha\"\n---\n# Alpha\n",
}


def make_vault(tmp: Path):
    for rel, body in PAGES.items():
        p = tmp / "wiki" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def run(vault, *args):
    return subprocess.run(
        [sys.executable, str(CLI), *args, "--wiki-path", str(vault)],
        capture_output=True, text=True)


class TestWikiCli(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name)
        make_vault(self.vault)

    def tearDown(self):
        self._tmp.cleanup()

    def test_search_markdown_exit_zero(self):
        r = run(self.vault, "search", "alpha")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Résultats pour « alpha »", r.stdout)

    def test_search_json_is_parsable(self):
        r = run(self.vault, "search", "alpha", "--json")
        self.assertEqual(r.returncode, 0)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["query"], "alpha")
        self.assertTrue(payload["results"][0]["path"].startswith("wiki/"))

    def test_json_path_is_reinjectable_into_read(self):
        r = run(self.vault, "search", "alpha", "--json")
        path = json.loads(r.stdout)["results"][0]["path"]
        r2 = run(self.vault, "read", path)
        self.assertEqual(r2.returncode, 0)
        self.assertIn("# Alpha", r2.stdout)

    def test_missing_page_exits_2_with_stderr(self):
        r = run(self.vault, "read", "wiki/concepts/ghost.md")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Page introuvable", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_empty_search_no_match_exits_0(self):
        r = run(self.vault, "search", "zzzznope")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Aucun résultat", r.stdout)

    def test_scan_sources_without_query_exits_2(self):
        r = run(self.vault, "scan-sources", "demo")
        self.assertEqual(r.returncode, 2)
        self.assertIn("sans query", r.stderr)

    def test_scan_domain_json(self):
        r = run(self.vault, "scan-domain", "demo", "--json")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["domain"], "demo")

    def test_scan_concepts_markdown_and_json(self):
        r = run(self.vault, "scan-concepts", "demo")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Concepts dans demo", r.stdout)
        self.assertIn("- alpha — Alpha", r.stdout)
        rj = run(self.vault, "scan-concepts", "demo", "--json")
        self.assertEqual(rj.returncode, 0)
        payload = json.loads(rj.stdout)
        self.assertEqual(payload["type"], "concept")
        self.assertEqual(payload["results"][0]["slug"], "alpha")

    def test_preview_markdown(self):
        r = run(self.vault, "preview", "wiki/concepts/alpha.md")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.startswith("# Preview : wiki/concepts/alpha.md"))
        self.assertIn("**type**: concept", r.stdout)


class TestCliMcpMdParity(unittest.TestCase):
    """The CLI markdown output (default) must equal wiki_core's *_md output —
    i.e. the same bytes a consumer would get from the MCP tool."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name)
        make_vault(self.vault)
        sys.path.insert(0, str(CLI.parent))
        import wiki_core
        self.wiki_core = wiki_core
        wiki_core.configure(self.vault)

    def tearDown(self):
        self._tmp.cleanup()

    def test_search_md_matches_core(self):
        r = run(self.vault, "search", "alpha")
        expected = self.wiki_core.search_wiki_md(self.wiki_core.search_wiki_data("alpha"))
        self.assertEqual(r.stdout.rstrip("\n"), expected)

    def test_scan_domain_md_matches_core(self):
        r = run(self.vault, "scan-domain", "demo")
        expected = self.wiki_core.scan_domain_md(self.wiki_core.scan_domain_data("demo"))
        self.assertEqual(r.stdout.rstrip("\n"), expected)


if __name__ == "__main__":
    unittest.main()
