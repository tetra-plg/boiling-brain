#!/usr/bin/env python3
"""unittest suite for purge-pending-ingest.sh — the only writer that removes
entries from cache/.pending-ingest.

Run: python3 -m unittest discover -s scripts/wiki-maint -p "test_*.py"
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "purge-pending-ingest.sh"


class PurgePendingTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name)
        (self.vault / "cache").mkdir()
        self.pending = self.vault / "cache" / ".pending-ingest"

    def tearDown(self):
        self._tmp.cleanup()

    def purge(self, *paths):
        return subprocess.run(["bash", str(SCRIPT), *paths], cwd=self.vault,
                              capture_output=True, text=True)

    def test_removes_plain_entries(self):
        self.pending.write_text("raw/a.md\nraw/b.md\n", encoding="utf-8")
        r = self.purge("raw/a.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.pending.read_text(encoding="utf-8"), "raw/b.md\n")

    def test_removes_entry_carrying_a_domain_hint(self):
        # #154: `<path>\t<hint>` lines are matched on the path field.
        self.pending.write_text("raw/a.md\tdemo\nraw/b.md\tother\nraw/c.md\n",
                                encoding="utf-8")
        r = self.purge("raw/a.md", "raw/c.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.pending.read_text(encoding="utf-8"), "raw/b.md\tother\n")

    def test_path_prefix_is_not_a_match(self):
        self.pending.write_text("raw/a.md.bak\nraw/a.md\tdemo\n", encoding="utf-8")
        self.purge("raw/a.md")
        self.assertEqual(self.pending.read_text(encoding="utf-8"), "raw/a.md.bak\n")

    def test_empty_manifest_is_removed(self):
        self.pending.write_text("raw/a.md\tdemo\n", encoding="utf-8")
        self.purge("raw/a.md")
        self.assertFalse(self.pending.exists())

    def test_noop_without_manifest_or_arguments(self):
        self.assertEqual(self.purge("raw/a.md").returncode, 0)
        self.pending.write_text("raw/a.md\n", encoding="utf-8")
        self.assertEqual(self.purge().returncode, 0)
        self.assertEqual(self.pending.read_text(encoding="utf-8"), "raw/a.md\n")


if __name__ == "__main__":
    unittest.main()
