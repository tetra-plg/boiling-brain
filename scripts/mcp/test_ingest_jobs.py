#!/usr/bin/env python3
"""unittest suite for ingest_jobs.py — real short-lived child processes
(sh/sleep) instead of mocks: also exercises the reaping logic.

Run: cd scripts/mcp && python3 -m unittest test_ingest_jobs
Requires NO fastmcp.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

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
        self._saved_tick = ingest_jobs.TICK_S
        ingest_jobs.TICK_S = 0.05
        ingest_jobs._PROCS.clear()

    def tearDown(self):
        # Stop the promotion thread first: it must never act on the real
        # vault once the paths below are restored.
        ingest_jobs._stop_ticker()
        for proc in ingest_jobs._PROCS.values():
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        ingest_jobs._PROCS.clear()
        ingest_jobs.TIMEOUT_S = self._saved_timeout
        ingest_jobs.TICK_S = self._saved_tick
        wiki_core.WIKI_PATH, wiki_core.RAW_DIR, wiki_core.CACHE_DIR = self._saved
        self._tmp.cleanup()

    def poll_until_final(self, job_id, deadline_s=10):
        end = time.monotonic() + deadline_s
        while time.monotonic() < end:
            out = ingest_jobs.status(job_id)
            if "running" not in out and "queued" not in out:
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


class TestBuildCmd(IngestJobsBase):
    """#154: the guarded headless command is built in one place, shared by the
    MCP tools and the batch runner (scripts/ops/ingest-pending.py)."""

    def test_command_shape(self):
        cmd = ingest_jobs.build_ingest_cmd("/ingest raw/notes/a.md --headless",
                                           claude_exe="/opt/bin/claude")
        self.assertEqual(cmd[:4], ["/opt/bin/claude", "-p",
                                   "/ingest raw/notes/a.md --headless", "--settings"])
        self.assertEqual(len(cmd), 5)
        settings = json.loads(cmd[4])
        pretool = settings["hooks"]["PreToolUse"]
        self.assertEqual(pretool[0]["matcher"], "")
        self.assertEqual(pretool[0]["hooks"][0]["command"],
                         str(wiki_core.WIKI_PATH / "scripts" / "mcp" / "ingest-headless-guard.sh"))

    def test_permission_mode_appended(self):
        cmd = ingest_jobs.build_ingest_cmd("/ingest x --headless", "auto",
                                           claude_exe="claude")
        self.assertEqual(cmd[-2:], ["--permission-mode", "auto"])

    def test_resolves_claude_with_shutil_which(self):
        with patch("shutil.which", return_value="/opt/npm/claude.CMD"):
            cmd = ingest_jobs.build_ingest_cmd("/ingest x --headless")
        self.assertEqual(cmd[0], "/opt/npm/claude.CMD")
        with patch("shutil.which", return_value=None):
            self.assertIsNone(ingest_jobs.build_ingest_cmd("/ingest x --headless"))


class TestStart(IngestJobsBase):
    def test_start_returns_job_id_and_persists_state(self):
        report = ingest_jobs.start(["sleep", "30"], "raw/notes/a.md")
        self.assertIn("started for raw/notes/a.md", report)
        job_id = self.job_id_of(report)
        state_file = wiki_core.CACHE_DIR / "ingest-jobs" / f"{job_id}.json"
        self.assertTrue(state_file.exists())
        self.assertIn('"state": "running"', state_file.read_text(encoding="utf-8"))

    def test_second_start_is_queued_while_running(self):
        # #154: no error any more — the job waits for the slot.
        ingest_jobs.start(["sleep", "30"], "raw/notes/a.md")
        second = ingest_jobs.start(["sleep", "30"], "raw/notes/a.md")
        self.assertNotIn("Error", second)
        self.assertIn("queued", second)
        self.assertIn("position 1", second)
        job_id = self.job_id_of(second)
        self.assertIn("queued (position 1", ingest_jobs.status(job_id))


class TestLock(IngestJobsBase):
    """#154: cache/ingest.lock keeps the MCP jobs and the scheduled batch
    runner (another process) from running two headless ingests at once."""

    def setUp(self):
        super().setUp()
        wiki_core.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.holder = subprocess.Popen(["sleep", "30"])
        self.addCleanup(self._kill_holder)

    def _kill_holder(self):
        if self.holder.poll() is None:
            self.holder.kill()
        self.holder.wait()

    def test_acquire_release(self):
        self.assertTrue(ingest_jobs.acquire_lock(owner="test"))
        holder = ingest_jobs.lock_holder()
        self.assertEqual(holder["pid"], os.getpid())
        self.assertEqual(holder["owner"], "test")
        self.assertIn("started_at", holder)
        # Re-entrant for the same pid.
        self.assertTrue(ingest_jobs.acquire_lock())
        ingest_jobs.release_lock()
        self.assertIsNone(ingest_jobs.lock_holder())
        self.assertFalse(ingest_jobs.lock_path().exists())

    def test_live_foreign_holder_blocks(self):
        self.assertTrue(ingest_jobs.acquire_lock(pid=self.holder.pid))
        self.assertFalse(ingest_jobs.acquire_lock())
        self.assertEqual(ingest_jobs.lock_holder()["pid"], self.holder.pid)
        # Only the holder's pid releases it.
        ingest_jobs.release_lock()
        self.assertTrue(ingest_jobs.lock_path().exists())
        ingest_jobs.release_lock(pid=self.holder.pid)
        self.assertFalse(ingest_jobs.lock_path().exists())

    def test_stale_lock_is_taken_over(self):
        self.assertTrue(ingest_jobs.acquire_lock(pid=self.holder.pid))
        self._kill_holder()
        self.assertIsNone(ingest_jobs.lock_holder())
        self.assertTrue(ingest_jobs.acquire_lock())
        self.assertEqual(ingest_jobs.lock_holder()["pid"], os.getpid())

    def test_unreadable_lock_is_stale_once_old(self):
        ingest_jobs.lock_path().write_text("garbage", encoding="utf-8")
        self.assertIsNotNone(ingest_jobs.lock_holder())  # maybe mid-write
        old = time.time() - 3600
        os.utime(ingest_jobs.lock_path(), (old, old))
        self.assertIsNone(ingest_jobs.lock_holder())

    def test_running_job_holds_the_lock_until_it_ends(self):
        report = ingest_jobs.start(["/bin/sh", "-c", "sleep 0.3"], "raw/notes/a.md")
        job_id = self.job_id_of(report)
        self.assertEqual(ingest_jobs.lock_holder()["pid"], ingest_jobs._PROCS[job_id].pid)
        self.poll_until_final(job_id)
        self.assertIsNone(ingest_jobs.lock_holder())

    def test_job_stays_queued_while_another_process_holds_the_lock(self):
        self.assertTrue(ingest_jobs.acquire_lock(pid=self.holder.pid, owner="batch"))
        marker = wiki_core.WIKI_PATH / "ran"
        report = ingest_jobs.start(["/bin/sh", "-c", f"touch {marker}"], "raw/notes/a.md")
        self.assertIn("queued", report)
        job_id = self.job_id_of(report)
        time.sleep(0.3)
        self.assertIn("queued (position 1", ingest_jobs.status(job_id))
        self.assertFalse(marker.exists())
        self._kill_holder()  # the foreign batch ends: its lock goes stale
        self.poll_until_final(job_id)
        self.assertTrue(marker.exists())


class TestQueue(IngestJobsBase):
    """#154: a job started while another runs is queued (FIFO) and promoted
    automatically when the slot frees — by a tool call or by the background
    thread, whichever comes first."""

    def _order_job(self, name, delay=0.0):
        order = wiki_core.WIKI_PATH / "order"
        script = f"sleep {delay}; echo {name} >> {order}"
        return self.job_id_of(ingest_jobs.start(["/bin/sh", "-c", script], "raw/notes/a.md"))

    def _wait_for(self, predicate, deadline_s=10):
        end = time.monotonic() + deadline_s
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.05)
        self.fail("condition not reached")

    def test_fifo_order_and_positions(self):
        self._order_job("first", 0.3)
        second = self._order_job("second")
        third = self._order_job("third")
        self.assertIn("queued (position 1", ingest_jobs.status(second))
        self.assertIn("queued (position 2", ingest_jobs.status(third))
        self.poll_until_final(third)
        order = (wiki_core.WIKI_PATH / "order").read_text(encoding="utf-8").split()
        self.assertEqual(order, ["first", "second", "third"])

    def test_promoted_without_any_tool_call(self):
        self._order_job("first", 0.2)
        self._order_job("second")
        order = wiki_core.WIKI_PATH / "order"
        self._wait_for(lambda: order.exists() and "second" in order.read_text(encoding="utf-8"))

    def test_queued_job_report_is_the_normal_report(self):
        ingest_jobs.start(["sleep", "0.2"], "raw/notes/a.md")
        report = ingest_jobs.start(
            ["/bin/sh", "-c", "printf 'needs-human-triage\\n\\n## Pages\\n'"], "raw/notes/a.md")
        final = self.poll_until_final(self.job_id_of(report))
        self.assertIn("## Pages", final)

    def test_cancel_queued_job_removes_it(self):
        ingest_jobs.start(["sleep", "0.3"], "raw/notes/a.md")
        second = self._order_job("second")
        out = ingest_jobs.cancel(second)
        self.assertIn("cancelled", out)
        self.assertIn("cancelled", ingest_jobs.status(second))
        time.sleep(0.6)
        self.assertFalse((wiki_core.WIKI_PATH / "order").exists())

    def test_journal_mentions_taken_when_the_job_starts(self):
        # A queued job's baseline is read at spawn time, after the previous
        # job journaled: an earlier run mentioning the same path must not
        # count as this run's entry.
        (wiki_core.WIKI_PATH / "wiki").mkdir()
        log = wiki_core.WIKI_PATH / "wiki" / "log.md"
        log.write_text("# Log\n", encoding="utf-8")
        journal = f"printf -- '- Source: raw/notes/a.md\\n' >> {log}; "
        pages = "printf '## Pages\\n- wiki/sources/a.md (source, new)\\n'"
        ingest_jobs.start(["/bin/sh", "-c", "sleep 0.2; " + journal + pages], "raw/notes/a.md")
        second = ingest_jobs.start(["/bin/sh", "-c", pages], "raw/notes/a.md")
        final = self.poll_until_final(self.job_id_of(second))
        self.assertTrue(final.startswith("DEGRADED"), final)


class TestBatchKind(IngestJobsBase):
    """#154: a batch job (the ingest_pending runner) journals per file itself:
    no journal check on its consolidated report, no single-run watchdog."""

    def test_no_journal_check_on_batch_report(self):
        report = ingest_jobs.start(
            ["/bin/sh", "-c", "printf '## Pages\\n- wiki/x.md (concept, new)\\n'"],
            "cache/.pending-ingest", kind="batch")
        final = self.poll_until_final(self.job_id_of(report))
        self.assertNotIn("DEGRADED", final)

    def test_no_single_run_watchdog(self):
        ingest_jobs.TIMEOUT_S = 0.1
        report = ingest_jobs.start(["/bin/sh", "-c", "sleep 0.4; echo done"],
                                   "cache/.pending-ingest", kind="batch")
        final = self.poll_until_final(self.job_id_of(report))
        self.assertNotIn("timeout", final)
        self.assertIn("done", final)


class TestStatus(IngestJobsBase):
    def test_unknown_and_malformed_job_id(self):
        self.assertIn("unknown job_id", ingest_jobs.status("deadbeef0000"))
        self.assertIn("unknown job_id", ingest_jobs.status("../../etc"))

    def test_running_then_done_returns_report(self):
        report = ingest_jobs.start(
            ["/bin/sh", "-c", "sleep 0.2; printf '## Pages\\n- wiki/x.md\\n'"],
            "raw/notes/a.md")
        job_id = self.job_id_of(report)
        self.assertIn("running", ingest_jobs.status(job_id))
        final = self.poll_until_final(job_id)
        self.assertIn("## Pages", final)
        # A later poll returns the same report (state persisted).
        self.assertIn("## Pages", ingest_jobs.status(job_id))

    def test_child_failure_surfaces_stderr(self):
        report = ingest_jobs.start(
            ["/bin/sh", "-c", "echo boom >&2; exit 3"], "raw/notes/a.md")
        final = self.poll_until_final(self.job_id_of(report))
        self.assertIn("failed", final)
        self.assertIn("boom", final)
        self.assertIn("exit code 3", final)

    def test_timeout_kills_and_reports(self):
        ingest_jobs.TIMEOUT_S = 0.1
        report = ingest_jobs.start(["sleep", "30"], "raw/notes/a.md")
        job_id = self.job_id_of(report)
        time.sleep(0.2)
        final = ingest_jobs.status(job_id)
        self.assertIn("timeout", final)
        proc = ingest_jobs._PROCS[job_id]
        proc.wait(timeout=5)
        self.assertIsNotNone(proc.poll())


class TestJournalCheck(IngestJobsBase):
    """#145: a successful run whose ## Pages lists pages but which left no
    wiki/log.md entry for its source is stamped DEGRADED."""

    PAGES = "printf 'done\\n\\n## Pages\\n- wiki/sources/a.md (source, new)\\n'"

    def setUp(self):
        super().setUp()
        (wiki_core.WIKI_PATH / "wiki").mkdir()
        (wiki_core.WIKI_PATH / "wiki" / "log.md").write_text(
            "# Log\n\n## [2026-10-01] ingest | Older (agent: x)\n\n"
            "- Source: `raw/notes/b.md`\n", encoding="utf-8")

    def run_job(self, script):
        report = ingest_jobs.start(["/bin/sh", "-c", script], "raw/notes/a.md")
        return self.poll_until_final(self.job_id_of(report))

    def test_pages_without_journal_entry_is_degraded(self):
        final = self.run_job(self.PAGES)
        self.assertTrue(final.startswith("DEGRADED — journal entry missing"), final)
        self.assertIn("raw/notes/a.md", final.splitlines()[0])
        self.assertIn("journal-ingest.py", final)
        # The original report follows, so ## Pages stays parseable at the end.
        self.assertTrue(final.rstrip().endswith("- wiki/sources/a.md (source, new)"))

    def test_pages_with_journal_entry_is_clean(self):
        final = self.run_job(
            "printf '\\n## [2026-10-08] ingest | A (agent: x)\\n\\n"
            "- Source: `raw/notes/a.md`\\n' >> wiki/log.md; " + self.PAGES)
        self.assertNotIn("DEGRADED", final)
        self.assertIn("## Pages", final)

    def test_empty_pages_is_not_degraded(self):
        final = self.run_job("printf 'needs-human-triage\\n\\n## Pages\\n'")
        self.assertNotIn("DEGRADED", final)

    def test_journal_helpers(self):
        self.assertEqual(ingest_jobs.journal_mentions("raw/notes/b.md"), 1)
        self.assertEqual(ingest_jobs.journal_mentions("raw/notes/a.md"), 0)
        self.assertIsNone(ingest_jobs.journal_gap("raw/notes/a.md", 0, "## Pages\n"))
        self.assertIsNotNone(ingest_jobs.journal_gap(
            "raw/notes/a.md", 0, "## Pages\n- wiki/x.md (concept, new)\n"))
        (wiki_core.WIKI_PATH / "wiki" / "log.md").unlink()
        self.assertEqual(ingest_jobs.journal_mentions("raw/notes/b.md"), 0)


class TestCorruptState(IngestJobsBase):
    def test_corrupt_state_file_is_skipped(self):
        jobs_dir = wiki_core.CACHE_DIR / "ingest-jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)
        (jobs_dir / "deadbeef0001.json").write_text("not json", encoding="utf-8")
        report = ingest_jobs.start(["sleep", "30"], "raw/notes/a.md")
        self.assertIn("started for raw/notes/a.md", report)
        self.assertIn("unknown job_id", ingest_jobs.status("deadbeef0001"))


class TestRestartOrphan(IngestJobsBase):
    def test_status_reports_restart_orphan_and_frees_slot(self):
        report = ingest_jobs.start(["sleep", "30"], "raw/notes/a.md")
        job_id = self.job_id_of(report)
        proc = ingest_jobs._PROCS.pop(job_id)
        try:
            out = ingest_jobs.status(job_id)
            self.assertIn("server restarted", out)
            # Slot freed: a new job can start.
            self.assertIn("started", ingest_jobs.start(["sleep", "30"], "raw/notes/a.md"))
        finally:
            proc.kill()
            proc.wait()

    def test_cancel_restart_orphan_does_not_signal(self):
        report = ingest_jobs.start(["sleep", "30"], "raw/notes/a.md")
        job_id = self.job_id_of(report)
        proc = ingest_jobs._PROCS.pop(job_id)
        try:
            out = ingest_jobs.cancel(job_id)
            self.assertIn("nothing to cancel", out)
            # Never signaled: the leaked process is still alive.
            self.assertIsNone(proc.poll())
        finally:
            proc.kill()
            proc.wait()


class TestCancel(IngestJobsBase):
    def test_cancel_after_exit_not_finalized_keeps_report(self):
        report = ingest_jobs.start(
            ["/bin/sh", "-c", "printf '## Pages\\n'"], "raw/notes/a.md")
        job_id = self.job_id_of(report)
        proc = ingest_jobs._PROCS[job_id]
        proc.wait(timeout=5)
        out = ingest_jobs.cancel(job_id)
        self.assertIn("already finished (done)", out)
        self.assertIn("## Pages", ingest_jobs.status(job_id))

    def test_cancel_running_job(self):
        report = ingest_jobs.start(["sleep", "30"], "raw/notes/a.md")
        job_id = self.job_id_of(report)
        out = ingest_jobs.cancel(job_id)
        self.assertIn("cancelled", out)
        proc = ingest_jobs._PROCS[job_id]
        proc.wait(timeout=5)
        self.assertIsNotNone(proc.poll())
        self.assertIn("cancelled", ingest_jobs.status(job_id))
        # Slot freed: a new job can start.
        self.assertIn("started", ingest_jobs.start(["sleep", "30"], "raw/notes/a.md"))

    def test_cancel_finished_job_is_idempotent(self):
        report = ingest_jobs.start(["/bin/sh", "-c", "true"], "raw/notes/a.md")
        job_id = self.job_id_of(report)
        self.poll_until_final(job_id)
        out = ingest_jobs.cancel(job_id)
        self.assertIn("already finished", out)
        self.assertIn("done", out)

    def test_cancel_unknown_job_id(self):
        self.assertIn("unknown job_id", ingest_jobs.cancel("deadbeef0000"))


if __name__ == "__main__":
    unittest.main()
