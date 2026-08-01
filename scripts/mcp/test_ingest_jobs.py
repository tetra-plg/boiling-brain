#!/usr/bin/env python3
"""unittest suite for ingest_jobs.py — real short-lived child processes
(sh/sleep) instead of mocks: also exercises the reaping logic.

Run: cd scripts/mcp && python3 -m unittest test_ingest_jobs
Requires NO fastmcp.
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ingest_jobs
import wiki_core


class IngestJobsBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        vault = Path(self._tmp.name)
        (vault / "raw" / "notes").mkdir(parents=True)
        (vault / "raw" / "notes" / "a.md").write_text("x", encoding="utf-8")
        self._saved = (wiki_core.WIKI_PATH, wiki_core.RAW_DIR, wiki_core.CACHE_DIR)
        wiki_core.WIKI_PATH = vault
        wiki_core.RAW_DIR = vault / "raw"
        wiki_core.CACHE_DIR = vault / "cache"
        self._saved_timeout = ingest_jobs.TIMEOUT_S
        ingest_jobs._PROCS.clear()

    def tearDown(self):
        for proc in ingest_jobs._PROCS.values():
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        ingest_jobs._PROCS.clear()
        ingest_jobs.TIMEOUT_S = self._saved_timeout
        wiki_core.WIKI_PATH, wiki_core.RAW_DIR, wiki_core.CACHE_DIR = self._saved
        self._tmp.cleanup()

    def poll_until_final(self, job_id, deadline_s=10):
        end = time.monotonic() + deadline_s
        while time.monotonic() < end:
            out = ingest_jobs.status(job_id)
            if "running" not in out:
                return out
            time.sleep(0.05)
        self.fail(f"job {job_id} still running after {deadline_s}s")

    @staticmethod
    def job_id_of(report):
        # "Job <id> started for <path>. ..."
        return report.split()[1]


class TestValidate(IngestJobsBase):
    def test_valid_request_builds_prompt(self):
        prompt, err = ingest_jobs.validate_request("raw/notes/a.md", "demo")
        self.assertIsNone(err)
        self.assertEqual(prompt, "/ingest raw/notes/a.md --headless --domain-hint=demo")

    def test_bad_domain_hint(self):
        prompt, err = ingest_jobs.validate_request("raw/notes/a.md", "Bad Slug!")
        self.assertIsNone(prompt)
        self.assertIn("invalid domain_hint", err)

    def test_flag_injection_rejected(self):
        for path in ("raw/notes/a b.md", "raw/-evil/a.md"):
            with self.subTest(path=path):
                prompt, err = ingest_jobs.validate_request(path)
                self.assertIsNone(prompt)
                self.assertIn("invalid path", err)

    def test_traversal_rejected(self):
        prompt, err = ingest_jobs.validate_request("raw/../wiki/x.md")
        self.assertIsNone(prompt)
        self.assertIn("path traversal", err)

    def test_missing_file_rejected(self):
        prompt, err = ingest_jobs.validate_request("raw/notes/absent.md")
        self.assertIsNone(prompt)
        self.assertIn("not found", err)


class TestStart(IngestJobsBase):
    def test_start_returns_job_id_and_persists_state(self):
        report = ingest_jobs.start(["sleep", "30"], "raw/notes/a.md")
        self.assertIn("started for raw/notes/a.md", report)
        job_id = self.job_id_of(report)
        state_file = wiki_core.CACHE_DIR / "ingest-jobs" / f"{job_id}.json"
        self.assertTrue(state_file.exists())
        self.assertIn('"state": "running"', state_file.read_text(encoding="utf-8"))

    def test_second_start_refused_while_running(self):
        first = ingest_jobs.start(["sleep", "30"], "raw/notes/a.md")
        second = ingest_jobs.start(["sleep", "30"], "raw/notes/a.md")
        self.assertIn("already running", second)
        self.assertIn(self.job_id_of(first), second)


if __name__ == "__main__":
    unittest.main()
