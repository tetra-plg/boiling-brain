#!/usr/bin/env python3
"""unittest suite for scan-raw.sh — verifies Python interpreter resolution.

Run: cd scripts/wiki-maint && python3 -m unittest test_scan_raw
Builds a hermetic PATH per test (symlinks to only the coreutils the script
needs) so each scenario (missing python3, python-only, broken interpreter)
is deterministic regardless of what's installed on the host running the
suite.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

import scan_raw_fixture  # local module, same dir

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "scan-raw.sh"
BASH = shutil.which("bash")
REAL_PYTHON = sys.executable
FIXTURE_GOLDEN = HERE / "fixtures" / "scan-raw"

_engine_spec = importlib.util.spec_from_file_location("scan_raw", HERE / "scan-raw.py")
scan_raw = importlib.util.module_from_spec(_engine_spec)
_engine_spec.loader.exec_module(scan_raw)

REQUIRED_TOOLS = ["find", "grep", "sed", "sort", "sha256sum", "dirname", "basename", "wc", "tr", "cut"]


def _hermetic_bin(tmp):
    """A bin/ dir with symlinks to only the coreutils scan-raw.sh needs.
    No python3/python here — callers add those explicitly per scenario."""
    bindir = tmp / "bin"
    bindir.mkdir(exist_ok=True)
    for tool in REQUIRED_TOOLS:
        src = shutil.which(tool)
        assert src, f"{tool} not found on the test host's PATH"
        (bindir / tool).symlink_to(src)
    return bindir


def _write_broken_python(path):
    """Simulates a PATH entry that resolves but isn't a working interpreter
    (e.g. the Windows Store python3 stub): any invocation fails."""
    path.write_text('#!/bin/sh\necho "not a real interpreter" >&2\nexit 9\n', encoding="utf-8")
    path.chmod(0o755)


def _write_marker_python(path, marker_file):
    path.write_text(
        f'#!/bin/sh\necho called >> "{marker_file}"\nexec "{REAL_PYTHON}" "$@"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def _make_vault(tmp, raw_files, sources):
    """raw_files: {rel_path_under_raw: content}. sources: {slug: {source_path, source_sha256?}}."""
    dest_script_dir = tmp / "scripts" / "wiki-maint"
    dest_script_dir.mkdir(parents=True)
    dest_script = dest_script_dir / "scan-raw.sh"
    dest_script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    dest_script.chmod(0o755)

    # engine must ride along with the thin wrapper
    engine = dest_script_dir / "scan-raw.py"
    engine.write_text((HERE / "scan-raw.py").read_text(encoding="utf-8"), encoding="utf-8")
    engine.chmod(0o755)

    for rel, content in raw_files.items():
        p = tmp / "raw" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    sources_dir = tmp / "wiki" / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    for slug, fm in sources.items():
        lines = ["---"]
        lines.append(f"source_path: {fm['source_path']}")
        if "source_sha256" in fm:
            lines.append(f"source_sha256: {fm['source_sha256']}")
        lines.append("---")
        (sources_dir / f"{slug}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return dest_script


def run_scan(script, env, cwd):
    return subprocess.run([BASH, str(script)], capture_output=True, text=True, env=env, cwd=cwd)


class PythonResolutionTest(unittest.TestCase):
    def test_baseline_python3_present_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            bindir = _hermetic_bin(tmp)
            (bindir / "python3").symlink_to(REAL_PYTHON)
            script = _make_vault(
                tmp,
                {"foo.md": "hello\n"},
                {"foo": {"source_path": "raw/foo.md"}},
            )
            r = run_scan(script, env={"PATH": str(bindir)}, cwd=str(tmp))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("SKIP     raw/foo.md  (covered-by: foo)", r.stdout)

    def test_python_only_no_python3_resolves(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            bindir = _hermetic_bin(tmp)
            (bindir / "python").symlink_to(REAL_PYTHON)  # no python3 entry
            script = _make_vault(
                tmp,
                {"foo.md": "hello\n"},
                {"foo": {"source_path": "raw/foo.md"}},
            )
            r = run_scan(script, env={"PATH": str(bindir)}, cwd=str(tmp))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("SKIP     raw/foo.md  (covered-by: foo)", r.stdout)

    def test_no_interpreter_fails_loudly_no_false_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            bindir = _hermetic_bin(tmp)  # neither python nor python3
            script = _make_vault(
                tmp,
                {"foo.md": "hello\n"},
                {"foo": {"source_path": "raw/foo.md"}},
            )
            r = run_scan(script, env={"PATH": str(bindir)}, cwd=str(tmp))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("python", r.stderr.lower())
            self.assertNotIn("covered-by", r.stdout)
            self.assertNotIn("NEW", r.stdout)

    def test_non_functional_interpreter_fails_loudly(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            bindir = _hermetic_bin(tmp)
            _write_broken_python(bindir / "python3")  # resolves, but unusable (Store-stub-like)
            script = _make_vault(
                tmp,
                {"foo.md": "hello\n"},
                {"foo": {"source_path": "raw/foo.md"}},
            )
            r = run_scan(script, env={"PATH": str(bindir)}, cwd=str(tmp))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("python", r.stderr.lower())
            self.assertNotIn("covered-by", r.stdout)

    def test_python_bin_override_respected(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            bindir = _hermetic_bin(tmp)
            (bindir / "python3").symlink_to(REAL_PYTHON)  # present but must NOT be used
            marker_file = tmp / "marker.txt"
            marker_python = tmp / "marker_python.sh"
            _write_marker_python(marker_python, marker_file)
            script = _make_vault(
                tmp,
                {"foo.md": "hello\n"},
                {"foo": {"source_path": "raw/foo.md"}},
            )
            env = {"PATH": str(bindir), "PYTHON_BIN": str(marker_python)}
            r = run_scan(script, env=env, cwd=str(tmp))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("SKIP     raw/foo.md  (covered-by: foo)", r.stdout)
            self.assertTrue(marker_file.exists(), "PYTHON_BIN override was not invoked")


class CollectFilesTest(unittest.TestCase):
    def _vault(self, tmp):
        for rel in ["raw/notes/a.md", "raw/notes/b.md", "raw/notes/pic.png",
                    "raw/notes/x.sync-meta.json", "raw/other/c.md"]:
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x\n", encoding="utf-8")
        return tmp

    def test_no_arg_scans_all_raw_filtered_sorted(self):
        with tempfile.TemporaryDirectory() as d:
            v = self._vault(Path(d))
            files, warns = scan_raw.collect_files(str(v), [])
            rels = [f[len(str(v)) + 1:] for f in files]
            self.assertEqual(rels, ["raw/notes/a.md", "raw/notes/b.md", "raw/other/c.md"])
            self.assertEqual(warns, [])

    def test_single_file_arg(self):
        with tempfile.TemporaryDirectory() as d:
            v = self._vault(Path(d))
            files, warns = scan_raw.collect_files(str(v), ["raw/notes/a.md"])
            self.assertEqual([f[len(str(v)) + 1:] for f in files], ["raw/notes/a.md"])

    def test_missing_path_warns_and_continues(self):
        with tempfile.TemporaryDirectory() as d:
            v = self._vault(Path(d))
            files, warns = scan_raw.collect_files(str(v), ["raw/nope.md"])
            self.assertEqual(files, [])
            self.assertEqual(warns, ["path not found: raw/nope.md"])

    def test_parse_args_defaults(self):
        ns = scan_raw.parse_args([])
        self.assertFalse(ns.force)
        self.assertFalse(ns.orphans)
        self.assertFalse(ns.pending)
        self.assertEqual(ns.format, "text")
        self.assertEqual(ns.paths, [])


class NormalizeTest(unittest.TestCase):
    def test_nfc_and_apostrophe_fold(self):
        # U+2019 -> U+0027
        self.assertEqual(scan_raw.normalize_path("l’ete.md"), "l'ete.md")
        # NFC: decomposed e + combining acute -> precomposed
        self.assertEqual(scan_raw.normalize_path("é.md"),
                         unicodedata.normalize("NFC", "é.md"))


class FrontmatterTest(unittest.TestCase):
    def test_fields_only_inside_block(self):
        text = ("---\n"
                "type: source\n"
                "source_path: raw/notes/real.md\n"
                "---\n"
                "body mentions source_path: raw/notes/ghost.md\n")
        meta = scan_raw.parse_source_page(text)
        self.assertEqual(meta["indexed_paths"], ["raw/notes/real.md"])
        self.assertNotIn("raw/notes/ghost.md", meta["indexed_paths"])

    def test_source_path_list_and_covered_and_legacy(self):
        text = ("---\n"
                "source_path:\n"
                "  - raw/a.md\n"
                "  - raw/b.md\n"
                "covered_paths:\n"
                "  - raw/c.md\n"
                "sources:\n"
                "  - raw/legacy.md\n"
                "source_sha256: abc123\n"
                "---\n")
        meta = scan_raw.parse_source_page(text)
        self.assertEqual(meta["indexed_paths"], ["raw/a.md", "raw/b.md", "raw/c.md"])
        self.assertEqual(meta["legacy_paths"], ["raw/legacy.md"])
        self.assertEqual(meta["first_source_path"], "raw/a.md")
        self.assertEqual(meta["source_sha256"], "abc123")
        self.assertEqual(meta["covered_paths"], ["raw/c.md"])

    def test_no_frontmatter_yields_nothing(self):
        meta = scan_raw.parse_source_page("no fm here\nsource_path: raw/x.md\n")
        self.assertEqual(meta["indexed_paths"], [])
        self.assertEqual(meta["legacy_paths"], [])


class BuildIndexTest(unittest.TestCase):
    def _sources(self, tmp, pages):
        d = tmp / "wiki" / "sources"
        d.mkdir(parents=True, exist_ok=True)
        for slug, body in pages.items():
            (d / f"{slug}.md").write_text(body, encoding="utf-8")
        return str(d)

    def test_exact_and_sha_indexed(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            sd = self._sources(tmp, {
                "s": "---\nsource_path: raw/notes/a.md\nsource_sha256: deadbeef\n---\n",
            })
            idx = scan_raw.build_index(sd)
            self.assertEqual(idx.path_to_slug[scan_raw.normalize_path("raw/notes/a.md")], "s")
            self.assertEqual(idx.path_to_sha[scan_raw.normalize_path("raw/notes/a.md")], "deadbeef")

    def test_implicit_dir_depth_gate(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            sd = self._sources(tmp, {
                "deep": "---\nsource_path: raw/deep/a/b/c/anchor.md\n---\n",
                "shallow": "---\nsource_path: raw/shallow/b/anchor.md\n---\n",
            })
            idx = scan_raw.build_index(sd)
            self.assertIn(scan_raw.normalize_path("raw/deep/a/b/c/"), idx.dir_to_slug)
            self.assertNotIn(scan_raw.normalize_path("raw/shallow/b/"), idx.dir_to_slug)

    def test_videos_meta_map(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            sd = self._sources(tmp, {
                "t": "---\nsource_path: raw/transcripts/vid.md\n---\n",
            })
            idx = scan_raw.build_index(sd)
            self.assertEqual(
                idx.meta_to_slug[scan_raw.normalize_path("raw/videos-meta/vid.meta.md")], "t")


class ClassifyTest(unittest.TestCase):
    def _idx(self, tmp, pages):
        d = tmp / "wiki" / "sources"
        d.mkdir(parents=True, exist_ok=True)
        for slug, body in pages.items():
            (d / f"{slug}.md").write_text(body, encoding="utf-8")
        return scan_raw.build_index(str(d))

    def test_exact_skip_when_sha_matches(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            raw = tmp / "raw" / "notes" / "a.md"
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text("x\n", encoding="utf-8")
            sha = hashlib.sha256(b"x\n").hexdigest()
            idx = self._idx(tmp, {"s": f"---\nsource_path: raw/notes/a.md\nsource_sha256: {sha}\n---\n"})
            v = scan_raw.classify("raw/notes/a.md", str(raw), idx, force=False)
            self.assertEqual((v.status, v.covered_by, v.reason), ("SKIP", "s", "exact"))

    def test_exact_modified_when_sha_diverges(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            raw = tmp / "raw" / "notes" / "a.md"
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text("new\n", encoding="utf-8")
            idx = self._idx(tmp, {"s": "---\nsource_path: raw/notes/a.md\nsource_sha256: oldsha\n---\n"})
            v = scan_raw.classify("raw/notes/a.md", str(raw), idx, force=False)
            self.assertEqual((v.status, v.reason), ("MODIFIED", "sha-changed"))

    def test_force_turns_skip_into_modified_forced(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            raw = tmp / "raw" / "notes" / "a.md"
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text("x\n", encoding="utf-8")
            sha = hashlib.sha256(b"x\n").hexdigest()
            idx = self._idx(tmp, {"s": f"---\nsource_path: raw/notes/a.md\nsource_sha256: {sha}\n---\n"})
            v = scan_raw.classify("raw/notes/a.md", str(raw), idx, force=True)
            self.assertEqual((v.status, v.reason, v.covered_by), ("MODIFIED", "forced", "s"))

    def test_new_when_unmatched(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            idx = self._idx(tmp, {})
            v = scan_raw.classify("raw/notes/z.md", "/nope", idx, force=False)
            self.assertEqual(v.status, "NEW")

    def test_format_lines_byte_exact(self):
        V = scan_raw.Verdict
        self.assertEqual(scan_raw.format_text_line(V("NEW"), "raw/z.md"), "NEW      raw/z.md")
        self.assertEqual(scan_raw.format_text_line(V("SKIP", "s", "exact"), "raw/a.md"),
                         "SKIP     raw/a.md  (covered-by: s)")
        self.assertEqual(scan_raw.format_text_line(V("MODIFIED", "s", "sha-changed"), "raw/a.md"),
                         "MODIFIED raw/a.md  (covered-by: s, sha-changed)")
        self.assertEqual(scan_raw.format_text_line(V("SKIP", "d", "dir"), "raw/a.md"),
                         "SKIP     raw/a.md  (covered-by-dir: d)")
        self.assertEqual(scan_raw.format_text_line(V("SKIP", "d", "dir-implicit"), "raw/a.md"),
                         "SKIP     raw/a.md  (covered-by-dir-implicit: d)")
        self.assertEqual(scan_raw.format_text_line(V("SKIP", "t", "transcript"), "raw/a.md"),
                         "SKIP     raw/a.md  (covered-by-transcript: t)")
        self.assertEqual(scan_raw.format_text_line(V("MODIFIED", "s", "forced"), "raw/a.md"),
                         "MODIFIED raw/a.md  (covered-by: s, forced)")

    def test_legacy_only_coverage_and_claims_preserved(self):
        # issue #103 caveat: legacy `sources:` entries stay in path_to_slug
        # (coverage) and claims (double-coverage lint); only orphan
        # detection ignores them.
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            raw = tmp / "raw" / "notes" / "old.md"
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text("x\n", encoding="utf-8")
            idx = self._idx(tmp, {
                "legacy-page": "---\nsources:\n  - raw/notes/old.md\n---\n",
                "modern-page": "---\ncovered_paths:\n  - raw/notes/old.md\n---\n",
            })
            key = scan_raw.normalize_path("raw/notes/old.md")
            self.assertEqual(sorted(idx.claims[key]), ["legacy-page", "modern-page"])
            v = scan_raw.classify("raw/notes/old.md", str(raw), idx, force=False)
            self.assertEqual(v.status, "SKIP")
            self.assertEqual(v.covered_by, "modern-page")

    def test_legacy_entries_feed_dir_and_meta_indexes(self):
        # issue #103 caveat: legacy `sources:` entries still feed dir_to_slug
        # and meta_to_slug indexes (implicit dir coverage, transcript meta maps);
        # only orphan detection ignores them.
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            # Create the legacy-only page with transcript and deep dir entries
            d = tmp / "wiki" / "sources"
            d.mkdir(parents=True)
            (d / "legacy-vid.md").write_text(
                "---\nsources:\n"
                '  - raw/transcripts/vid.md\n'
                '  - raw/deep/a/b/c/anchor.md\n'
                "---\n",
                encoding="utf-8",
            )
            # Create actual files on disk so classify() can work
            vid_file = tmp / "raw" / "transcripts" / "vid.md"
            vid_file.parent.mkdir(parents=True, exist_ok=True)
            vid_file.write_text("x\n", encoding="utf-8")
            sibling_file = tmp / "raw" / "deep" / "a" / "b" / "c" / "sibling.md"
            sibling_file.parent.mkdir(parents=True, exist_ok=True)
            sibling_file.write_text("x\n", encoding="utf-8")

            idx = scan_raw.build_index(str(d))

            # Check meta_to_slug index: legacy transcript entries feed it
            meta_key = scan_raw.normalize_path("raw/videos-meta/vid.meta.md")
            self.assertEqual(idx.meta_to_slug[meta_key], "legacy-vid")

            # Check dir_to_slug index: legacy deep-dir entries feed it
            # (depth >= 4 slashes: raw/deep/a/b/c/ has 5 slashes)
            dir_key = scan_raw.normalize_path("raw/deep/a/b/c/")
            self.assertEqual(idx.dir_to_slug[dir_key], "legacy-vid")

            # Sibling file under the dir should classify as SKIP via dir coverage
            v = scan_raw.classify("raw/deep/a/b/c/sibling.md", str(sibling_file), idx, force=False)
            self.assertEqual(v.status, "SKIP")
            self.assertEqual(v.reason, "dir-implicit")


class StrictFrontmatterDivergenceTest(unittest.TestCase):
    """The one intentional default-verdict divergence (spec §5.2): a source_path
    that appears in the BODY (not the frontmatter) is NOT indexed, so its raw
    file is NEW under Python (it was a phantom SKIP under the old bash)."""
    def test_body_motif_not_indexed(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            raw = tmp / "raw" / "notes" / "ghost.md"
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text("x\n", encoding="utf-8")
            d = tmp / "wiki" / "sources"
            d.mkdir(parents=True, exist_ok=True)
            (d / "s.md").write_text(
                "---\ntype: source\nsource_path: raw/notes/real.md\n---\n"
                "prose that mentions\nsource_path: raw/notes/ghost.md\n", encoding="utf-8")
            idx = scan_raw.build_index(str(d))
            v = scan_raw.classify("raw/notes/ghost.md", str(raw), idx, force=False)
            self.assertEqual(v.status, "NEW")


class OrphansTest(unittest.TestCase):
    def test_orphan_listed_when_raw_missing(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            d = tmp / "wiki" / "sources"; d.mkdir(parents=True)
            (d / "gone.md").write_text("---\nsource_path: raw/gone.md\n---\n", encoding="utf-8")
            idx = scan_raw.build_index(str(d))
            self.assertEqual(scan_raw.find_orphans(str(tmp), idx), [("raw/gone.md", "gone")])

    def test_no_orphan_when_present(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            raw = tmp / "raw" / "here.md"; raw.parent.mkdir(parents=True); raw.write_text("x\n")
            d = tmp / "wiki" / "sources"; d.mkdir(parents=True)
            (d / "here.md").write_text("---\nsource_path: raw/here.md\n---\n", encoding="utf-8")
            idx = scan_raw.build_index(str(d))
            self.assertEqual(scan_raw.find_orphans(str(tmp), idx), [])

    def test_orphans_flag_appends_lines(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            raw = tmp / "raw" / "here.md"; raw.parent.mkdir(parents=True); raw.write_text("x\n")
            d = tmp / "wiki" / "sources"; d.mkdir(parents=True)
            (d / "here.md").write_text("---\nsource_path: raw/here.md\n---\n", encoding="utf-8")
            (d / "gone.md").write_text("---\nsource_path: raw/gone.md\n---\n", encoding="utf-8")
            r = subprocess.run(["python3", str(HERE / "scan-raw.py"), "--orphans"],
                               capture_output=True, text=True,
                               env=dict(os.environ, VAULT_ROOT=str(tmp)))
            self.assertIn("ORPHAN   raw/gone.md  (covered-by: gone)", r.stdout)

    def test_legacy_sources_wikilinks_are_not_orphans(self):
        # issue #103: [[wikilink]] entries in legacy `sources:` are wiki refs,
        # never disk paths — they must not be reported as missing raw files.
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            d = tmp / "wiki" / "sources"
            d.mkdir(parents=True)
            (d / "page.md").write_text(
                "---\n"
                "source_path: raw/notes/real.md\n"
                "sources:\n"
                '  - "[[sources/some-source]]"\n'
                "  - https://example.com/article\n"
                "---\n",
                encoding="utf-8",
            )
            (tmp / "raw" / "notes").mkdir(parents=True)
            (tmp / "raw" / "notes" / "real.md").write_text("x\n", encoding="utf-8")
            idx = scan_raw.build_index(str(d))
            self.assertEqual(scan_raw.find_orphans(str(tmp), idx), [])

    def test_deleted_pass1_path_still_reported_even_if_also_legacy(self):
        # A genuinely deleted raw file declared via covered_paths must stay
        # reported, even when the same path also appears in legacy `sources:`.
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            d = tmp / "wiki" / "sources"
            d.mkdir(parents=True)
            (d / "dual.md").write_text(
                "---\n"
                "covered_paths:\n"
                "  - raw/gone/deleted.md\n"
                "sources:\n"
                "  - raw/gone/deleted.md\n"
                "---\n",
                encoding="utf-8",
            )
            idx = scan_raw.build_index(str(d))
            self.assertEqual(scan_raw.find_orphans(str(tmp), idx),
                             [("raw/gone/deleted.md", "dual")])


class JsonFormatTest(unittest.TestCase):
    def _run_json(self, tmp, args):
        r = subprocess.run(["python3", str(HERE / "scan-raw.py"), "--format=json", *args],
                           capture_output=True, text=True,
                           env=dict(os.environ, VAULT_ROOT=str(tmp)))
        return r, json.loads(r.stdout)

    def test_json_shape_and_counts(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            for rel in ["raw/notes/skip.md", "raw/notes/new.md"]:
                p = tmp / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text("x\n")
            sha = hashlib.sha256(b"x\n").hexdigest()
            d = tmp / "wiki" / "sources"; d.mkdir(parents=True)
            (d / "s.md").write_text(f"---\nsource_path: raw/notes/skip.md\nsource_sha256: {sha}\n---\n")
            r, doc = self._run_json(tmp, [])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(doc["version"], 1)
            self.assertFalse(doc["force"])
            by = {f["path"]: f for f in doc["files"]}
            self.assertEqual(by["raw/notes/skip.md"]["status"], "SKIP")
            self.assertEqual(by["raw/notes/skip.md"]["reason"], "exact")
            self.assertEqual(by["raw/notes/new.md"]["status"], "NEW")
            self.assertEqual(doc["counts"], {"new": 1, "modified": 0, "skipped": 1, "orphans": 0})
            self.assertNotIn("orphans", doc)  # flag absent

    def test_json_includes_orphans_when_flagged(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            d = tmp / "wiki" / "sources"; d.mkdir(parents=True)
            (d / "gone.md").write_text("---\nsource_path: raw/gone.md\n---\n")
            r, doc = self._run_json(tmp, ["--orphans"])
            self.assertEqual(doc["orphans"], [{"path": "raw/gone.md", "covered_by": "gone"}])
            self.assertEqual(doc["counts"]["orphans"], 1)


class LintTest(unittest.TestCase):
    def test_duplicate_claim_warns_on_stderr(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            d = tmp / "wiki" / "sources"; d.mkdir(parents=True)
            (d / "a.md").write_text("---\nsource_path: raw/dup.md\n---\n")
            (d / "b.md").write_text("---\nsource_path: raw/dup.md\n---\n")
            r = subprocess.run(["python3", str(HERE / "scan-raw.py")],
                               capture_output=True, text=True,
                               env=dict(os.environ, VAULT_ROOT=str(tmp)))
            self.assertIn("WARN: duplicate-claim raw/dup.md", r.stderr)

    def test_missing_sha_warns(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            d = tmp / "wiki" / "sources"; d.mkdir(parents=True)
            (d / "nosha.md").write_text("---\nsource_path: raw/x.md\n---\n")
            r = subprocess.run(["python3", str(HERE / "scan-raw.py")],
                               capture_output=True, text=True,
                               env=dict(os.environ, VAULT_ROOT=str(tmp)))
            self.assertIn("WARN: missing-sha nosha", r.stderr)

    def test_summary_line_on_stderr(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            p = tmp / "raw" / "new.md"; p.parent.mkdir(parents=True); p.write_text("x\n")
            (tmp / "wiki" / "sources").mkdir(parents=True)
            r = subprocess.run(["python3", str(HERE / "scan-raw.py")],
                               capture_output=True, text=True,
                               env=dict(os.environ, VAULT_ROOT=str(tmp)))
            self.assertIn("1 new · 0 modified · 0 skipped", r.stderr)

    def test_lint_warnings_in_json(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            d = tmp / "wiki" / "sources"; d.mkdir(parents=True)
            (d / "a.md").write_text("---\nsource_path: raw/dup.md\n---\n")
            (d / "b.md").write_text("---\nsource_path: raw/dup.md\n---\n")
            r = subprocess.run(["python3", str(HERE / "scan-raw.py"), "--format=json"],
                               capture_output=True, text=True,
                               env=dict(os.environ, VAULT_ROOT=str(tmp)))
            doc = json.loads(r.stdout)
            kinds = {w["kind"] for w in doc["warnings"]}
            self.assertIn("duplicate-claim", kinds)


class PendingTest(unittest.TestCase):
    def _vault(self, tmp):
        # skip.md is covered (SKIP -> purgeable), gone.md not on disk (STALE)
        p = tmp / "raw" / "skip.md"; p.parent.mkdir(parents=True); p.write_text("x\n")
        sha = hashlib.sha256(b"x\n").hexdigest()
        d = tmp / "wiki" / "sources"; d.mkdir(parents=True)
        (d / "s.md").write_text(f"---\nsource_path: raw/skip.md\nsource_sha256: {sha}\n---\n")
        cache = tmp / "cache"; cache.mkdir()
        (cache / ".pending-ingest").write_text("raw/skip.md\nraw/gone.md\n", encoding="utf-8")
        return tmp

    def test_pending_text_stale_line(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = self._vault(Path(dd))
            r = subprocess.run(["python3", str(HERE / "scan-raw.py"), "--pending"],
                               capture_output=True, text=True,
                               env=dict(os.environ, VAULT_ROOT=str(tmp)))
            self.assertIn("SKIP     raw/skip.md  (covered-by: s)", r.stdout)
            self.assertIn("STALE    raw/gone.md  (not-on-disk)", r.stdout)

    def test_pending_json_buckets(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = self._vault(Path(dd))
            r = subprocess.run(["python3", str(HERE / "scan-raw.py"), "--pending", "--format=json"],
                               capture_output=True, text=True,
                               env=dict(os.environ, VAULT_ROOT=str(tmp)))
            doc = json.loads(r.stdout)
            self.assertEqual(doc["pending"]["purgeable"], ["raw/skip.md"])
            self.assertEqual(doc["pending"]["stale"], ["raw/gone.md"])

    def test_pending_readonly_manifest_untouched(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = self._vault(Path(dd))
            before = (tmp / "cache" / ".pending-ingest").read_text()
            subprocess.run(["python3", str(HERE / "scan-raw.py"), "--pending"],
                           capture_output=True, text=True,
                           env=dict(os.environ, VAULT_ROOT=str(tmp)))
            self.assertEqual((tmp / "cache" / ".pending-ingest").read_text(), before)

    def test_pending_empty_says_nothing_pending(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd); (tmp / "wiki" / "sources").mkdir(parents=True)
            r = subprocess.run(["python3", str(HERE / "scan-raw.py"), "--pending"],
                               capture_output=True, text=True,
                               env=dict(os.environ, VAULT_ROOT=str(tmp)))
            self.assertEqual(r.returncode, 0)
            self.assertIn("Nothing pending.", r.stderr)

    def test_pending_with_path_is_usage_error(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            r = subprocess.run(["python3", str(HERE / "scan-raw.py"), "--pending", "raw/x.md"],
                               capture_output=True, text=True,
                               env=dict(os.environ, VAULT_ROOT=str(tmp)))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("--pending", r.stderr)


class CompositeTest(unittest.TestCase):
    def _sh(self, b): return hashlib.sha256(b).hexdigest()

    def test_canonical_formula_matches_shasum_pipeline(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            for rel, content in [("raw/b.md", b"beta\n"), ("raw/a.md", b"alpha\n")]:
                p = tmp / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(content)
            # expected: sorted lexicographically -> a.md then b.md
            expected_stream = (f"{self._sh(b'alpha\n')}  raw/a.md\n"
                               f"{self._sh(b'beta\n')}  raw/b.md\n").encode()
            expected = hashlib.sha256(expected_stream).hexdigest()
            got = scan_raw.compute_composite(["raw/b.md", "raw/a.md"], str(tmp))
            self.assertEqual(got, expected)

    def test_missing_covered_file_returns_none(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            self.assertIsNone(scan_raw.compute_composite(["raw/nope.md"], str(tmp)))

    def test_composite_mismatch_warns(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            for rel, c in [("raw/1.md", "one\n"), ("raw/2.md", "two\n")]:
                p = tmp / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(c)
            d = tmp / "wiki" / "sources"; d.mkdir(parents=True)
            (d / "m.md").write_text(
                "---\nsource_path: raw/1.md\nsource_sha256_composite: deadbeef\n"
                "covered_paths:\n  - raw/2.md\n---\n")
            r = subprocess.run(["python3", str(HERE / "scan-raw.py"), "--format=json"],
                               capture_output=True, text=True,
                               env=dict(os.environ, VAULT_ROOT=str(tmp)))
            doc = json.loads(r.stdout)
            cm = [w for w in doc["warnings"] if w["kind"] == "composite-mismatch"]
            self.assertEqual(len(cm), 1)
            self.assertEqual(cm[0]["slug"], "m")
            self.assertEqual(cm[0]["stored"], "deadbeef")

    def test_composite_intact_no_warn(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            for rel, c in [("raw/1.md", "one\n"), ("raw/2.md", "two\n")]:
                p = tmp / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(c)
            good = scan_raw.compute_composite(["raw/1.md", "raw/2.md"], str(tmp))
            d = tmp / "wiki" / "sources"; d.mkdir(parents=True)
            (d / "m.md").write_text(
                f"---\nsource_path: raw/1.md\nsource_sha256_composite: {good}\n"
                "covered_paths:\n  - raw/1.md\n  - raw/2.md\n---\n")
            r = subprocess.run(["python3", str(HERE / "scan-raw.py"), "--format=json"],
                               capture_output=True, text=True,
                               env=dict(os.environ, VAULT_ROOT=str(tmp)))
            doc = json.loads(r.stdout)
            self.assertEqual([w for w in doc["warnings"] if w["kind"] == "composite-mismatch"], [])


def _stage(tmp):
    """Build the parity fixture and copy BOTH scripts into it so the wrapper
    resolves VAULT_ROOT to the fixture and can exec the engine."""
    vault = scan_raw_fixture.build(tmp)
    dst = vault / "scripts" / "wiki-maint"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy(SCRIPT, dst / "scan-raw.sh")
    engine = HERE / "scan-raw.py"
    if engine.exists():
        shutil.copy(engine, dst / "scan-raw.py")
    return vault, dst / "scan-raw.sh"


class GoldenParityTest(unittest.TestCase):
    def test_default_output_matches_frozen_golden(self):
        expected = (FIXTURE_GOLDEN / "default.golden").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as d:
            vault, script = _stage(Path(d))
            r = subprocess.run([BASH, str(script)], capture_output=True,
                               text=True, cwd=str(vault))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout, expected)


class HashCacheTest(unittest.TestCase):
    def test_hit_reuses_stored_digest_without_rehashing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            f = root / "raw" / "a.md"; f.parent.mkdir(parents=True); f.write_text("hello", encoding="utf-8")
            c = scan_raw.HashCache(str(root))
            first = c.get(str(f))
            self.assertEqual(first, hashlib.sha256(b"hello").hexdigest())
            # poison the cache entry; a hit must return the poisoned value (proves no re-hash)
            c.data["raw/a.md"][2] = "deadbeef"
            self.assertEqual(c.get(str(f)), "deadbeef")

    def test_miss_on_size_change_recomputes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            f = root / "raw" / "a.md"; f.parent.mkdir(parents=True); f.write_text("hello", encoding="utf-8")
            c = scan_raw.HashCache(str(root))
            c.get(str(f))
            f.write_text("hello world", encoding="utf-8")  # size changes
            self.assertEqual(c.get(str(f)), hashlib.sha256(b"hello world").hexdigest())

    def test_save_and_reload_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            f = root / "raw" / "a.md"; f.parent.mkdir(parents=True); f.write_text("hello", encoding="utf-8")
            c = scan_raw.HashCache(str(root)); c.get(str(f)); c.save()
            self.assertTrue((root / "cache" / ".hash-cache.json").is_file())
            c2 = scan_raw.HashCache(str(root))
            self.assertIn("raw/a.md", c2.data)

    def test_corrupt_cache_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "cache").mkdir(parents=True)
            (root / "cache" / ".hash-cache.json").write_text("{not json", encoding="utf-8")
            c = scan_raw.HashCache(str(root))  # must not raise
            self.assertEqual(c.data, {})

    def test_unwritable_cache_dir_degrades_gracefully(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            f = root / "raw" / "a.md"; f.parent.mkdir(parents=True); f.write_text("hi", encoding="utf-8")
            (root / "cache").write_text("blocker", encoding="utf-8")  # cache/ is a FILE
            c = scan_raw.HashCache(str(root))
            self.assertEqual(c.get(str(f)), hashlib.sha256(b"hi").hexdigest())
            c.save()  # must not raise


class LineageTest(unittest.TestCase):
    def test_lineage_key_under_snapshot(self):
        snaps = {"raw/tracked-repos/next/abc1234"}
        self.assertEqual(
            scan_raw.lineage_key("raw/tracked-repos/next/abc1234/docs/a.md", snaps),
            ("raw/tracked-repos/next", "docs/a.md"),
        )

    def test_lineage_key_none_outside_snapshot(self):
        self.assertIsNone(scan_raw.lineage_key("raw/notes/x.md", set()))

    def test_find_snapshot_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            snap = root / "raw" / "tracked-repos" / "next" / "abc1234"
            snap.mkdir(parents=True)
            (snap / ".sync-meta.json").write_text("{}", encoding="utf-8")
            (snap / "README.md").write_text("x", encoding="utf-8")
            self.assertEqual(
                scan_raw.find_snapshot_dirs(str(root)),
                {"raw/tracked-repos/next/abc1234"},
            )


class ContentCoverageTest(unittest.TestCase):
    def _vault_two_snapshots(self, tmp, second_files):
        """snapA (abc1234) covered by a page (dir cover). snapB (def5678) = second_files.
        Each snapshot gets a .sync-meta.json. Returns vault_root path (str)."""
        root = Path(tmp)
        dest = root / "raw" / "tracked-repos" / "next"
        a = dest / "abc1234"; a.mkdir(parents=True)
        (a / ".sync-meta.json").write_text('{"shortsha":"abc1234"}', encoding="utf-8")
        (a / "README.md").write_text("readme v1\n", encoding="utf-8")
        (a / "docs").mkdir()
        (a / "docs" / "a.md").write_text("alpha\n", encoding="utf-8")
        (a / "docs" / "b.md").write_text("bravo\n", encoding="utf-8")
        b = dest / "def5678"; b.mkdir(parents=True)
        (b / ".sync-meta.json").write_text('{"shortsha":"def5678"}', encoding="utf-8")
        for rel, content in second_files.items():
            p = b / rel; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        sources = root / "wiki" / "sources"; sources.mkdir(parents=True)
        (sources / "next-abc1234.md").write_text(
            "---\ntype: source\nsource_path: raw/tracked-repos/next/abc1234/README.md\n"
            "covered_paths:\n  - raw/tracked-repos/next/abc1234/\n---\n", encoding="utf-8")
        return str(root)

    def _scan(self, vault_root):
        cache = scan_raw.HashCache(vault_root)
        idx = scan_raw.build_index(os.path.join(vault_root, "wiki", "sources"))
        snaps = scan_raw.find_snapshot_dirs(vault_root)
        content = scan_raw.build_content_index(idx, vault_root, cache, snaps)

        class NS:
            force = False; orphans = False; pending = False; paths = []; format = "text"
        files, results, _ = scan_raw.run(vault_root, NS, idx, cache)
        scan_raw.apply_content_coverage(results, vault_root, cache, snaps, content)
        return {rel: v.status for rel, v in results}

    def test_noop_total_all_skip(self):
        with tempfile.TemporaryDirectory() as d:
            vr = self._vault_two_snapshots(d, {
                "README.md": "readme v1\n", "docs/a.md": "alpha\n", "docs/b.md": "bravo\n",
            })
            st = self._scan(vr)
            for rel in ["raw/tracked-repos/next/def5678/README.md",
                        "raw/tracked-repos/next/def5678/docs/a.md",
                        "raw/tracked-repos/next/def5678/docs/b.md"]:
                self.assertEqual(st[rel], "SKIP", rel)

    def test_partial_change_only_changed_is_new(self):
        with tempfile.TemporaryDirectory() as d:
            vr = self._vault_two_snapshots(d, {
                "README.md": "readme v1\n", "docs/a.md": "ALPHA CHANGED\n", "docs/b.md": "bravo\n",
            })
            st = self._scan(vr)
            self.assertEqual(st["raw/tracked-repos/next/def5678/docs/a.md"], "NEW")
            self.assertEqual(st["raw/tracked-repos/next/def5678/docs/b.md"], "SKIP")
            self.assertEqual(st["raw/tracked-repos/next/def5678/README.md"], "SKIP")

    def test_cross_dest_no_leak(self):
        with tempfile.TemporaryDirectory() as d:
            vr = self._vault_two_snapshots(d, {"README.md": "readme v1\n"})
            other = Path(vr) / "raw" / "tracked-repos" / "other" / "zzz9999"
            other.mkdir(parents=True)
            (other / ".sync-meta.json").write_text('{"shortsha":"zzz9999"}', encoding="utf-8")
            (other / "README.md").write_text("readme v1\n", encoding="utf-8")
            st = self._scan(vr)
            self.assertEqual(st["raw/tracked-repos/other/zzz9999/README.md"], "NEW")

    def test_outside_snapshot_not_content_covered(self):
        with tempfile.TemporaryDirectory() as d:
            vr = self._vault_two_snapshots(d, {"README.md": "readme v1\n"})
            note = Path(vr) / "raw" / "notes" / "loose.md"
            note.parent.mkdir(parents=True)
            note.write_text("alpha\n", encoding="utf-8")  # identical to covered docs/a.md
            st = self._scan(vr)
            self.assertEqual(st["raw/notes/loose.md"], "NEW")

    def test_empty_file_not_content_covered(self):
        with tempfile.TemporaryDirectory() as d:
            vr = self._vault_two_snapshots(d, {"README.md": "readme v1\n", "empty.txt": ""})
            st = self._scan(vr)
            self.assertEqual(st["raw/tracked-repos/next/def5678/empty.txt"], "NEW")


class StrictCoverageTest(unittest.TestCase):
    """--strict-coverage audit (issue #105): list snapshot files covered
    only by implicit-dir inheritance, never declared, never content-read."""

    def _vault(self, tmp):
        """Snapshot raw/repos/proj/abc1234/ with one declared anchor
        (docs/a.md) and one undeclared sibling (docs/b.md)."""
        snap = tmp / "raw" / "repos" / "proj" / "abc1234"
        (snap / "docs").mkdir(parents=True)
        (snap / ".sync-meta.json").write_text("{}", encoding="utf-8")
        (snap / "docs" / "a.md").write_text("anchor\n", encoding="utf-8")
        (snap / "docs" / "b.md").write_text("sibling\n", encoding="utf-8")
        d = tmp / "wiki" / "sources"
        d.mkdir(parents=True)
        (d / "proj-doc.md").write_text(
            "---\nsource_path: raw/repos/proj/abc1234/docs/a.md\n---\n",
            encoding="utf-8",
        )
        return d

    def _audit(self, tmp, sources_dir):
        idx = scan_raw.build_index(str(sources_dir))
        cache = scan_raw.HashCache(str(tmp))
        snapshot_dirs = scan_raw.find_snapshot_dirs(str(tmp))
        content_index = scan_raw.build_content_index(idx, str(tmp), cache, snapshot_dirs)
        files, results, _ = scan_raw.run(str(tmp), _ns(), idx, cache)
        scan_raw.apply_content_coverage(results, str(tmp), cache, snapshot_dirs, content_index)
        return scan_raw.find_undeclared(results, str(tmp), cache, snapshot_dirs, content_index)

    def test_dir_implicit_sibling_is_undeclared(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            sd = self._vault(tmp)
            self.assertEqual(self._audit(tmp, sd),
                             [("raw/repos/proj/abc1234/docs/b.md", "proj-doc")])

    def test_fully_declared_snapshot_reports_nothing(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            sd = self._vault(tmp)
            (sd / "proj-doc.md").write_text(
                "---\nsource_path:\n"
                "  - raw/repos/proj/abc1234/docs/a.md\n"
                "  - raw/repos/proj/abc1234/docs/b.md\n---\n",
                encoding="utf-8",
            )
            self.assertEqual(self._audit(tmp, sd), [])

    def test_dir_implicit_outside_snapshot_not_listed(self):
        # No .sync-meta.json anywhere: out of the audit's scope.
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            deep = tmp / "raw" / "notes" / "a" / "b" / "c"
            deep.mkdir(parents=True)
            (deep / "anchor.md").write_text("x\n", encoding="utf-8")
            (deep / "sibling.md").write_text("y\n", encoding="utf-8")
            d = tmp / "wiki" / "sources"
            d.mkdir(parents=True)
            (d / "s.md").write_text(
                "---\nsource_path: raw/notes/a/b/c/anchor.md\n---\n",
                encoding="utf-8",
            )
            self.assertEqual(self._audit(tmp, d), [])

    def test_content_covered_sibling_not_listed(self):
        # The sibling's bytes were read under a previously covered snapshot
        # of the same dest: not a coverage deficit (deviation from the
        # issue's letter, aligned with its spirit + #88).
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            sd = self._vault(tmp)
            old = tmp / "raw" / "repos" / "proj" / "0000000"
            (old / "docs").mkdir(parents=True)
            (old / ".sync-meta.json").write_text("{}", encoding="utf-8")
            (old / "docs" / "b.md").write_text("sibling\n", encoding="utf-8")
            (sd / "proj-old.md").write_text(
                "---\nsource_path: raw/repos/proj/0000000/docs/b.md\n---\n",
                encoding="utf-8",
            )
            self.assertEqual(self._audit(tmp, sd), [])

    def test_flag_combinations_rejected(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            self._vault(tmp)
            env = {**os.environ, "VAULT_ROOT": str(tmp)}
            for combo in (["--strict-coverage", "--force"],
                          ["--strict-coverage", "--pending"]):
                r = subprocess.run(
                    ["python3", str(HERE / "scan-raw.py"), *combo],
                    capture_output=True, text=True, env=env)
                self.assertEqual(r.returncode, 2, combo)
                self.assertIn("--strict-coverage", r.stderr)

    def test_text_and_json_output_and_default_byte_identical(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            self._vault(tmp)
            env = {**os.environ, "VAULT_ROOT": str(tmp)}
            base = subprocess.run(["python3", str(HERE / "scan-raw.py")],
                                  capture_output=True, text=True, env=env)
            strict = subprocess.run(
                ["python3", str(HERE / "scan-raw.py"), "--strict-coverage"],
                capture_output=True, text=True, env=env)
            # default output: no UNDECLARED anywhere
            self.assertNotIn("UNDECLARED", base.stdout + base.stderr)
            # strict: same verdict lines, plus the appended audit line
            self.assertEqual(
                strict.stdout,
                base.stdout
                + "UNDECLARED raw/repos/proj/abc1234/docs/b.md  (dir-covered-by: proj-doc)\n")  # no padding on UNDECLARED
            self.assertIn("1 undeclared", strict.stderr)
            # JSON: key present only under the flag
            base_j = json.loads(subprocess.run(
                ["python3", str(HERE / "scan-raw.py"), "--format=json"],
                capture_output=True, text=True, env=env).stdout)
            strict_j = json.loads(subprocess.run(
                ["python3", str(HERE / "scan-raw.py"), "--strict-coverage",
                 "--format=json"],
                capture_output=True, text=True, env=env).stdout)
            self.assertNotIn("undeclared", base_j)
            self.assertNotIn("undeclared", base_j["counts"])
            self.assertEqual(strict_j["undeclared"],
                             [{"path": "raw/repos/proj/abc1234/docs/b.md",
                               "dir_covered_by": "proj-doc"}])
            self.assertEqual(strict_j["counts"]["undeclared"], 1)

    def test_orphans_and_undeclared_combined_and_path_scoped(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            sd = self._vault(tmp)
            # Create an orphan: a declared file that no longer exists on disk
            (sd / "orphan-doc.md").write_text(
                "---\nsource_path: raw/repos/proj/abc1234/nonexistent.md\n---\n",
                encoding="utf-8",
            )
            env = {**os.environ, "VAULT_ROOT": str(tmp)}
            # Test combined --orphans --strict-coverage
            r = subprocess.run(
                ["python3", str(HERE / "scan-raw.py"), "--orphans", "--strict-coverage"],
                capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0)
            # Verify output order: ORPHAN line followed by UNDECLARED line
            lines = r.stdout.strip().split("\n")
            orphan_lines = [l for l in lines if l.startswith("ORPHAN")]
            undeclared_lines = [l for l in lines if l.startswith("UNDECLARED")]
            self.assertEqual(len(orphan_lines), 1)
            self.assertEqual(len(undeclared_lines), 1)
            orphan_idx = lines.index(orphan_lines[0])
            undeclared_idx = lines.index(undeclared_lines[0])
            self.assertLess(orphan_idx, undeclared_idx, "ORPHAN should appear before UNDECLARED")
            # Verify summary mentions both
            self.assertIn("1 orphans", r.stderr)
            self.assertIn("1 undeclared", r.stderr)
            # Test path-scoped audit: --strict-coverage raw/repos/proj/abc1234/docs
            r_scoped = subprocess.run(
                ["python3", str(HERE / "scan-raw.py"), "--strict-coverage",
                 "raw/repos/proj/abc1234/docs"],
                capture_output=True, text=True, env=env)
            self.assertEqual(r_scoped.returncode, 0)
            # The UNDECLARED line should still appear (scoping preserves content_index)
            self.assertIn("UNDECLARED raw/repos/proj/abc1234/docs/b.md", r_scoped.stdout)

    def test_empty_undeclared_sibling_is_flagged(self):
        with tempfile.TemporaryDirectory() as dd:
            tmp = Path(dd)
            snap = tmp / "raw" / "repos" / "proj" / "abc1234"
            (snap / "docs").mkdir(parents=True)
            (snap / ".sync-meta.json").write_text("{}", encoding="utf-8")
            # One declared non-empty file and one empty undeclared sibling
            (snap / "docs" / "a.md").write_text("anchor\n", encoding="utf-8")
            (snap / "docs" / "empty.txt").write_text("", encoding="utf-8")
            # Create another snapshot with an identical empty file (declared)
            old = tmp / "raw" / "repos" / "proj" / "0000000"
            (old / "docs").mkdir(parents=True)
            (old / ".sync-meta.json").write_text("{}", encoding="utf-8")
            (old / "docs" / "empty.txt").write_text("", encoding="utf-8")
            d = tmp / "wiki" / "sources"
            d.mkdir(parents=True)
            (d / "proj-doc.md").write_text(
                "---\nsource_path: raw/repos/proj/abc1234/docs/a.md\n---\n",
                encoding="utf-8",
            )
            (d / "proj-old.md").write_text(
                "---\nsource_path: raw/repos/proj/0000000/docs/empty.txt\n---\n",
                encoding="utf-8",
            )
            # Run audit
            idx = scan_raw.build_index(str(d))
            cache = scan_raw.HashCache(str(tmp))
            snapshot_dirs = scan_raw.find_snapshot_dirs(str(tmp))
            content_index = scan_raw.build_content_index(idx, str(tmp), cache, snapshot_dirs)
            files, results, _ = scan_raw.run(str(tmp), _ns(), idx, cache)
            scan_raw.apply_content_coverage(results, str(tmp), cache, snapshot_dirs, content_index)
            undeclared = scan_raw.find_undeclared(results, str(tmp), cache, snapshot_dirs, content_index)
            # The empty sibling should be flagged (content never covers empty files)
            self.assertEqual(undeclared,
                             [("raw/repos/proj/abc1234/docs/empty.txt", "proj-doc")])


def _ns():
    """Namespace for tests."""
    class NS:
        force = False
        orphans = False
        pending = False
        paths = []
        format = "text"
    return NS()


if __name__ == "__main__":
    unittest.main()
