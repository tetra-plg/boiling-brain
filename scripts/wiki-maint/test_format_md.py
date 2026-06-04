#!/usr/bin/env python3
"""unittest suite for format-md.py — verifies Obsidian-safe formatting.

Run: cd scripts/wiki-maint && python3 -m unittest test_format_md
(Invokes Prettier via npx; first run may download it.)
"""
import importlib.util
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "format-md.py"

_spec = importlib.util.spec_from_file_location("format_md", SCRIPT)
fmt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fmt)


def run(args, cwd):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=cwd,
    )


class MaskUnmaskTest(unittest.TestCase):
    def test_roundtrip_wikilink_alias(self):
        s = "| a | [[entities/y|Alias]] |\n"
        self.assertNotIn("|Alias", fmt.mask(s).split("[[")[1])  # pipe masked inside
        self.assertEqual(fmt.unmask(fmt.mask(s)), s)

    def test_roundtrip_codespan(self):
        s = "| a | `skip|rewrite` |\n"
        self.assertEqual(fmt.unmask(fmt.mask(s)), s)

    def test_separator_pipes_untouched(self):
        # pipes outside wikilinks/code spans must NOT be masked
        s = "| a | b |\n"
        self.assertEqual(fmt.mask(s), s)


class WriteTest(unittest.TestCase):
    def _table(self):
        return textwrap.dedent("""\
            # T

            | Col | Lien | Détail |
            | --- | --- | --- |
            | a | [[entities/y|Alias non échappé]] | `skip|rewrite` |
            | b | [[entities/z]] | plain |
            """)

    def test_alias_and_codespan_survive_format(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "t.md"
            f.write_text(self._table(), encoding="utf-8")
            r = run(["--write", "t.md"], cwd=str(tmp))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            out = f.read_text(encoding="utf-8")
            # wikilink alias kept in ONE cell (pipe not turned into separator)
            self.assertIn("[[entities/y|Alias non échappé]]", out)
            # code span kept intact
            self.assertIn("`skip|rewrite`", out)
            # table still has exactly 3 columns on the separator row
            sep = [ln for ln in out.splitlines() if ln.strip().startswith("|") and "---" in ln][0]
            self.assertEqual(sep.count("|"), 4)  # 3 cols → 4 pipes

    def test_no_sentinel_leaks(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "t.md"
            f.write_text(self._table(), encoding="utf-8")
            run(["--write", "t.md"], cwd=str(tmp))
            self.assertNotIn(fmt.SENTINEL, f.read_text(encoding="utf-8"))


class CheckTest(unittest.TestCase):
    def test_check_flags_unformatted(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / ".prettierrc").write_text('{"proseWrap":"preserve"}', encoding="utf-8")
            f = tmp / "t.md"
            f.write_text("#  Bad   heading\n\n\n\nextra blanks\n", encoding="utf-8")
            r = run(["--check", "t.md"], cwd=str(tmp))
            self.assertEqual(r.returncode, 1)
            # original file untouched by --check
            self.assertIn("extra blanks", f.read_text(encoding="utf-8"))

    def test_check_passes_after_write(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / ".prettierrc").write_text('{"proseWrap":"preserve"}', encoding="utf-8")
            f = tmp / "t.md"
            f.write_text("| a | [[x|y]] | `p|q` |\n| --- | --- | --- |\n| 1 | 2 | 3 |\n",
                         encoding="utf-8")
            run(["--write", "t.md"], cwd=str(tmp))
            r = run(["--check", "t.md"], cwd=str(tmp))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
