#!/usr/bin/env python3
"""unittest suite for format-md.py — verifies Obsidian-safe formatting.

Run: cd scripts/wiki-maint && python3 -m unittest test_format_md
(Invokes Prettier via npx; first run may download it.)
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "format-md.py"

_spec = importlib.util.spec_from_file_location("format_md", SCRIPT)
fmt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fmt)


def run(args, cwd, env=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=cwd, env=env,
    )


class NpxResolutionTest(unittest.TestCase):
    def test_npx_found_via_which(self):
        with mock.patch.object(fmt.shutil, "which", return_value="/usr/bin/npx") as m:
            self.assertEqual(fmt._npx(), "/usr/bin/npx")
            m.assert_called_once_with("npx")

    def test_npx_missing_raises_clear_error(self):
        with mock.patch.object(fmt.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                fmt._npx()
        self.assertIn("npx", str(ctx.exception).lower())
        self.assertIn("PATH", str(ctx.exception))

    def test_missing_npx_end_to_end_clear_error(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "t.md"
            f.write_text("# T\n", encoding="utf-8")
            env = {"PATH": "/usr/bin:/bin"}  # strip node/npx dirs
            r = run(["--write", "t.md"], cwd=str(tmp), env=env)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("npx", r.stderr)
            self.assertIn("PATH", r.stderr)


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

    def test_venv_is_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / ".prettierrc").write_text('{"proseWrap":"preserve"}', encoding="utf-8")
            pkg = tmp / ".venv-voice" / "lib" / "numpy"
            pkg.mkdir(parents=True)
            # deliberately unformatted file inside a virtualenv
            (pkg / "README.md").write_text("#  Bad\n\n\n\nx\n", encoding="utf-8")
            r = run(["--check", "**/*.md"], cwd=str(tmp))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # venv ignored → clean


class Utf8OutputTest(unittest.TestCase):
    def test_check_output_survives_ascii_console(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / ".prettierrc").write_text('{"proseWrap":"preserve"}', encoding="utf-8")
            f = tmp / "t.md"
            f.write_text("| a | [[x|y]] | `p|q` |\n| --- | --- | --- |\n| 1 | 2 | 3 |\n",
                         encoding="utf-8")
            run(["--write", "t.md"], cwd=str(tmp))
            env = {**os.environ, "PYTHONIOENCODING": "ascii"}
            r = run(["--check", "t.md"], cwd=str(tmp), env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertNotIn("UnicodeEncodeError", r.stderr)


class ExpandTest(unittest.TestCase):
    def test_excluded_dirs(self):
        self.assertTrue(fmt._excluded(".venv-voice/lib/x.md"))
        self.assertTrue(fmt._excluded("node_modules/p/README.md"))
        self.assertTrue(fmt._excluded("docs/superpowers/specs/x.md"))
        self.assertFalse(fmt._excluded("wiki/concepts/foo.md"))
        self.assertFalse(fmt._excluded("docs/guide.md"))


class WikiIgnoreOptOutTest(unittest.TestCase):
    """wiki/ est dans .prettierignore (Prettier nu le skippe) mais le wrapper
    opt-out via --ignore-path et DOIT quand même le formatter et le vérifier."""

    _UNFORMATTED_WIKI = (
        "#  Bad   heading\n\n\n\n"
        "| Col | Lien | Détail |\n| --- | --- | --- |\n"
        "| a | [[entities/y|Alias]] | `skip|rewrite` |\n"
    )

    def _vault(self, tmp):
        (tmp / ".prettierrc").write_text('{"proseWrap":"preserve"}', encoding="utf-8")
        (tmp / ".prettierignore").write_text("wiki/\n", encoding="utf-8")
        page = tmp / "wiki" / "domains" / "d.md"
        page.parent.mkdir(parents=True)
        page.write_text(self._UNFORMATTED_WIKI, encoding="utf-8")
        return page

    def test_write_formats_wiki_despite_prettierignore(self):
        # Sans l'opt-out, Prettier skiperait wiki/ (ignoré) → fichier inchangé.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            page = self._vault(tmp)
            r = run(["--write", "wiki/domains/d.md"], cwd=str(tmp))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            out = page.read_text(encoding="utf-8")
            self.assertNotIn("#  Bad", out)            # heading normalisé → reformaté
            self.assertNotIn("\n\n\n", out)            # runs de lignes vides collapsés
            self.assertIn("[[entities/y|Alias]]", out)  # pipe d'alias préservé
            self.assertIn("`skip|rewrite`", out)        # pipe de code-span préservé

    def test_check_flags_unformatted_wiki_despite_prettierignore(self):
        # Garde-fou anti-faux-négatif : --check doit voir le fichier mal formaté.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._vault(tmp)
            r = run(["--check", "wiki/domains/d.md"], cwd=str(tmp))
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_bare_prettier_skips_wiki(self):
        # Caractérisation (done-criterion #1) : Prettier nu respecte .prettierignore.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            page = self._vault(tmp)
            before = page.read_text(encoding="utf-8")
            proc = subprocess.run(
                [fmt._npx(), "-y", "prettier", "--write", "wiki/domains/d.md"],
                capture_output=True, text=True, cwd=str(tmp),
            )
            self.assertEqual(page.read_text(encoding="utf-8"), before,
                             proc.stdout + proc.stderr)


class RepoPrettierIgnoreTest(unittest.TestCase):
    def test_repo_prettierignore_excludes_wiki(self):
        repo_root = HERE.parent.parent
        ignore = (repo_root / ".prettierignore").read_text(encoding="utf-8")
        self.assertRegex(ignore, r"(?m)^wiki/\s*$")


if __name__ == "__main__":
    unittest.main()
