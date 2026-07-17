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
        self.assertEqual(meta["indexed_paths"],
                         ["raw/a.md", "raw/b.md", "raw/c.md", "raw/legacy.md"])
        self.assertEqual(meta["first_source_path"], "raw/a.md")
        self.assertEqual(meta["source_sha256"], "abc123")
        self.assertEqual(meta["covered_paths"], ["raw/c.md"])

    def test_no_frontmatter_yields_nothing(self):
        meta = scan_raw.parse_source_page("no fm here\nsource_path: raw/x.md\n")
        self.assertEqual(meta["indexed_paths"], [])


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


if __name__ == "__main__":
    unittest.main()
