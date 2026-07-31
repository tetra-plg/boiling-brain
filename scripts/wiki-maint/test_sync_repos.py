#!/usr/bin/env python3
"""unittest suite for scripts/sync-repos.sh — drives the real bash script in a
temp vault with a stubbed `gh` on PATH (api → $FAKE_SHA; repo clone → cp -R of
$FAKE_REPO_DIR; auth status → ok). First test coverage of this script (#106)."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "sync-repos.sh"

GH_STUB = """#!/bin/sh
case "$1" in
  auth) exit 0 ;;
  api)  echo "$FAKE_SHA" ;;
  repo) cp -R "$FAKE_REPO_DIR" "$4" ;;
esac
"""


def make_vault(tmp: Path):
    """Copy the script into a temp vault (VAULT_ROOT is derived from $0)."""
    sdir = tmp / "scripts"
    sdir.mkdir(parents=True)
    dest = sdir / "sync-repos.sh"
    dest.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    dest.chmod(0o755)
    stub_dir = tmp / "stub-bin"
    stub_dir.mkdir()
    gh = stub_dir / "gh"
    gh.write_text(GH_STUB, encoding="utf-8")
    gh.chmod(0o755)
    return dest, stub_dir


def write_manifest(tmp: Path, paths, excludes=None):
    entry = {"name": "proj", "repo": "acme/proj", "branch": "main",
             "dest": "raw/repos/proj", "paths": paths}
    if excludes is not None:
        entry["exclude_paths"] = excludes
    (tmp / "tracked-repos.config.json").write_text(
        json.dumps({"sources": [entry]}), encoding="utf-8")


def make_fixture_repo(tmp: Path):
    repo = tmp / "fixture-repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "a.md").write_text("alpha\n", encoding="utf-8")
    (repo / "plans").mkdir()
    (repo / "plans" / "roadmap.md").write_text("plan\n", encoding="utf-8")
    (repo / "README.md").write_text("readme\n", encoding="utf-8")
    return repo


def run_sync(vault: Path, script: Path, stub_dir: Path, repo: Path, sha):
    env = {**os.environ,
           "PATH": f"{stub_dir}:{os.environ['PATH']}",
           "FAKE_SHA": sha,
           "FAKE_REPO_DIR": str(repo)}
    return subprocess.run(["bash", str(script)], capture_output=True,
                          text=True, env=env, cwd=str(vault))


SHA1 = "a" * 40
SHA2 = "b" * 40


class SyncReposPerimeterTest(unittest.TestCase):
    def _setup(self, paths, excludes=None):
        self._td = tempfile.TemporaryDirectory()
        tmp = Path(self._td.name)
        self.addCleanup(self._td.cleanup)
        script, stub = make_vault(tmp)
        write_manifest(tmp, paths, excludes)
        repo = make_fixture_repo(tmp)
        return tmp, script, stub, repo

    def test_first_sync_creates_base(self):
        tmp, script, stub, repo = self._setup(["docs/"])
        r = run_sync(tmp, script, stub, repo, SHA1)
        self.assertIn(f"CREATED raw/repos/proj/{SHA1[:7]}", r.stdout)
        meta = json.loads((tmp / "raw/repos/proj" / SHA1[:7] /
                           ".sync-meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["paths"], ["docs/"])

    def test_rerun_same_manifest_skips(self):
        tmp, script, stub, repo = self._setup(["docs/"])
        run_sync(tmp, script, stub, repo, SHA1)
        r = run_sync(tmp, script, stub, repo, SHA1)
        self.assertIn(f"SKIPPED proj (sha {SHA1[:7]} already snapshotted)", r.stdout)
        self.assertNotIn("CREATED", r.stdout)

    def test_widened_paths_create_r2(self):
        tmp, script, stub, repo = self._setup(["docs/"])
        run_sync(tmp, script, stub, repo, SHA1)
        base = tmp / "raw/repos/proj" / SHA1[:7]
        before = sorted(str(p.relative_to(base)) for p in base.rglob("*"))
        write_manifest(tmp, ["docs/", "plans/"])
        r = run_sync(tmp, script, stub, repo, SHA1)
        self.assertIn(f"CREATED raw/repos/proj/{SHA1[:7]}-r2", r.stdout)
        self.assertIn("perimeter changed", r.stderr)
        r2 = tmp / "raw/repos/proj" / f"{SHA1[:7]}-r2"
        self.assertTrue((r2 / "plans" / "roadmap.md").is_file())
        meta = json.loads((r2 / ".sync-meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["paths"], ["docs/", "plans/"])
        after = sorted(str(p.relative_to(base)) for p in base.rglob("*"))
        self.assertEqual(before, after)  # base snapshot untouched

    def test_next_change_creates_r3(self):
        tmp, script, stub, repo = self._setup(["docs/"])
        run_sync(tmp, script, stub, repo, SHA1)
        write_manifest(tmp, ["docs/", "plans/"])
        run_sync(tmp, script, stub, repo, SHA1)
        write_manifest(tmp, ["plans/"])
        r = run_sync(tmp, script, stub, repo, SHA1)
        self.assertIn(f"CREATED raw/repos/proj/{SHA1[:7]}-r3", r.stdout)

    def test_reordered_paths_skip(self):
        tmp, script, stub, repo = self._setup(["docs/", "plans/"])
        run_sync(tmp, script, stub, repo, SHA1)
        write_manifest(tmp, ["plans/", "docs/"])
        r = run_sync(tmp, script, stub, repo, SHA1)
        self.assertIn("SKIPPED", r.stdout)
        self.assertNotIn("CREATED", r.stdout)

    def test_meta_without_paths_skips_with_note(self):
        tmp, script, stub, repo = self._setup(["docs/"])
        run_sync(tmp, script, stub, repo, SHA1)
        meta_p = tmp / "raw/repos/proj" / SHA1[:7] / ".sync-meta.json"
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        del meta["paths"]
        meta_p.write_text(json.dumps(meta), encoding="utf-8")
        write_manifest(tmp, ["docs/", "plans/"])
        r = run_sync(tmp, script, stub, repo, SHA1)
        self.assertIn("SKIPPED", r.stdout)
        self.assertIn("cannot compare perimeter", r.stderr)
        self.assertNotIn("CREATED", r.stdout)

    def test_new_sha_creates_plain_base(self):
        tmp, script, stub, repo = self._setup(["docs/"])
        run_sync(tmp, script, stub, repo, SHA1)
        write_manifest(tmp, ["docs/", "plans/"])
        r = run_sync(tmp, script, stub, repo, SHA2)
        self.assertIn(f"CREATED raw/repos/proj/{SHA2[:7]}", r.stdout)
        self.assertNotIn("-r2", r.stdout)

    def test_rerun_after_revision_compares_latest(self):
        tmp, script, stub, repo = self._setup(["docs/"])
        run_sync(tmp, script, stub, repo, SHA1)
        write_manifest(tmp, ["docs/", "plans/"])
        run_sync(tmp, script, stub, repo, SHA1)
        r = run_sync(tmp, script, stub, repo, SHA1)  # manifest unchanged now
        self.assertIn("SKIPPED", r.stdout)
        self.assertNotIn("CREATED", r.stdout)


if __name__ == "__main__":
    unittest.main()
