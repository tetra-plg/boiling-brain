#!/usr/bin/env python3
"""unittest suite for validate-wiki.py — drives the CLI on temp fixture vaults.

Run: python3 -m unittest scripts.wiki-maint.test_validate_wiki
  (or: cd scripts/wiki-maint && python3 -m unittest test_validate_wiki)
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "validate-wiki.py"

GOOD_FM = textwrap.dedent("""\
    ---
    type: concept
    domains: [poker]
    created: 2026-05-01
    summary_l0: "Short scannable line"
    summary_l1: |
      A couple of sentences describing the page in enough depth.
    ---

    # Title
    """)


def make_vault(tmp: Path, pages: dict):
    """pages: {relpath_under_wiki: file_body}. Creates wiki/ tree."""
    for rel, body in pages.items():
        p = tmp / "wiki" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def run(tmp: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp)],
        capture_output=True, text=True,
    )


class ValidateWikiTest(unittest.TestCase):
    def test_clean_vault_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            make_vault(tmp, {
                "concepts/foo.md": GOOD_FM + "\nSee [[concepts/bar]].\n",
                "concepts/bar.md": GOOD_FM,
            })
            r = run(tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_broken_wikilink_detected(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            make_vault(tmp, {
                "concepts/foo.md": GOOD_FM + "\nSee [[concepts/missing]].\n",
            })
            r = run(tmp)
            self.assertEqual(r.returncode, 1)
            self.assertIn("missing", r.stdout)

    def test_bare_slug_wikilink_resolves(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            make_vault(tmp, {
                "concepts/foo.md": GOOD_FM + "\nSee [[bar]].\n",
                "concepts/bar.md": GOOD_FM,
            })
            r = run(tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_wikilink_with_alias_resolves(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            make_vault(tmp, {
                "concepts/foo.md": GOOD_FM + "\nSee [[concepts/bar|the bar]].\n",
                "concepts/bar.md": GOOD_FM,
            })
            r = run(tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_raw_link_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            # raw/ does not exist on disk (gitignored) — must NOT be flagged.
            make_vault(tmp, {
                "sources/s.md": GOOD_FM + "\n[src](../../raw/notes/x.md)\n",
            })
            r = run(tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_broken_relative_link_detected(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            make_vault(tmp, {
                "concepts/foo.md": GOOD_FM + "\n[x](./nope.md)\n",
            })
            r = run(tmp)
            self.assertEqual(r.returncode, 1)
            self.assertIn("nope.md", r.stdout)

    def test_external_link_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            make_vault(tmp, {
                "concepts/foo.md": GOOD_FM + "\n[ext](https://example.com/404)\n",
            })
            r = run(tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_summary_l1_detected(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            body = textwrap.dedent("""\
                ---
                type: concept
                domains: [poker]
                created: 2026-05-01
                summary_l0: "Short line"
                ---

                # Title
                """)
            make_vault(tmp, {"concepts/foo.md": body})
            r = run(tmp)
            self.assertEqual(r.returncode, 1)
            self.assertIn("summary_l1", r.stdout)

    def test_empty_domains_detected(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            body = GOOD_FM.replace("domains: [poker]", "domains: []")
            make_vault(tmp, {"concepts/foo.md": body})
            r = run(tmp)
            self.assertEqual(r.returncode, 1)
            self.assertIn("domains", r.stdout)

    def test_summary_l0_too_long_detected(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            long = "x" * 141
            body = GOOD_FM.replace('summary_l0: "Short scannable line"',
                                   f'summary_l0: "{long}"')
            make_vault(tmp, {"concepts/foo.md": body})
            r = run(tmp)
            self.assertEqual(r.returncode, 1)
            self.assertIn("summary_l0", r.stdout)

    def test_decision_requires_status(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            body = GOOD_FM.replace("type: concept", "type: decision")
            make_vault(tmp, {"decisions/adr.md": body})
            r = run(tmp)
            self.assertEqual(r.returncode, 1)
            self.assertIn("status", r.stdout)


if __name__ == "__main__":
    unittest.main()
