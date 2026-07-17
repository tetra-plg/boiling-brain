#!/usr/bin/env python3
"""unittest suite for scan-raw.sh — verifies Python interpreter resolution.

Run: cd scripts/wiki-maint && python3 -m unittest test_scan_raw
Builds a hermetic PATH per test (symlinks to only the coreutils the script
needs) so each scenario (missing python3, python-only, broken interpreter)
is deterministic regardless of what's installed on the host running the
suite.
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import scan_raw_fixture  # local module, same dir

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "scan-raw.sh"
BASH = shutil.which("bash")
REAL_PYTHON = sys.executable
FIXTURE_GOLDEN = HERE / "fixtures" / "scan-raw"

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
