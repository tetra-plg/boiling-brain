#!/usr/bin/env python3
"""unittest suite for ingest-pending.py — the batch runner of the pending
queue (#154). Real short-lived processes, no mocks: the `claude` CLI is a
fake executable (written per test) whose behaviour is keyed on the raw path
it is asked to ingest, so no test ever reaches the real CLI.

Run: python3 -m unittest discover -s scripts/ops -p "test_*.py"
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "ingest-pending.py"
FIXTURE = HERE / "fixtures" / "last-batch.example.json"
STATUSES = {"ok", "degraded", "failed", "skipped-no-hint"}

# Fake `claude -p "/ingest <path> --headless[ --domain-hint=<slug>]" ...`:
# records its argv, then behaves according to the path's name.
FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
prompt = sys.argv[sys.argv.index("-p") + 1]
path = prompt.split()[1]
with open("calls.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
stem = Path(path).stem
if "fail" in stem:
    sys.stderr.write("could not read " + path + "\n")
    sys.exit(3)
if "slow" in stem:
    time.sleep(30)
if "triage" in stem:
    print("## needs-human-triage\n\n- " + path + ": no single high-confidence expert\n"
          "Fix: retry with ingest_start(path, domain_hint=<slug>)\n\n## Pages")
    sys.exit(0)
if "nojournal" not in stem:
    with open("wiki/log.md", "a", encoding="utf-8") as f:
        f.write("\n## [2026-10-08] ingest | " + stem + " (agent: x, mode: headless)\n\n"
                "- Source: `" + path + "`\n")
print("1 new\n\n## Pages\n- wiki/sources/" + stem + ".md (source, new)\n"
      "- wiki/concepts/shared.md (concept, updated)")
'''


def check_outcome_schema(test, doc):
    """The last-batch.json contract (see fixtures/last-batch.example.json)."""
    test.assertEqual(set(doc), {"schema_version", "started_at", "ended_at", "trigger",
                                "domain_hint", "interrupted", "files", "counts",
                                "remaining"})
    test.assertEqual(doc["schema_version"], 1)
    for key in ("started_at", "ended_at"):
        # ISO 8601 with an explicit offset
        parsed = __import__("datetime").datetime.fromisoformat(doc[key])
        test.assertIsNotNone(parsed.tzinfo, key)
    test.assertIn(doc["trigger"], ("manual", "scheduled"))
    test.assertIsInstance(doc["interrupted"], bool)
    test.assertIsInstance(doc["remaining"], int)
    test.assertTrue(doc["domain_hint"] is None or isinstance(doc["domain_hint"], str))
    for entry in doc["files"]:
        test.assertEqual(set(entry), {"path", "status", "hint", "pages", "detail"})
        test.assertIn(entry["status"], STATUSES)
        test.assertTrue(entry["hint"] is None or isinstance(entry["hint"], str))
        test.assertTrue(entry["detail"] is None or isinstance(entry["detail"], str))
        for page in entry["pages"]:
            test.assertEqual(set(page), {"path", "type", "change"})
    counts = doc["counts"]
    test.assertEqual(set(counts), STATUSES | {"total"})
    test.assertEqual(counts["total"], len(doc["files"]))
    for status in STATUSES:
        test.assertEqual(counts[status],
                         sum(1 for e in doc["files"] if e["status"] == status))


class RunnerBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name).resolve()
        (self.vault / "raw" / "notes").mkdir(parents=True)
        (self.vault / "wiki").mkdir()
        (self.vault / "cache").mkdir()
        (self.vault / "wiki" / "log.md").write_text("# Log\n", encoding="utf-8")
        self.claude = self.vault / "fake-claude"
        self.claude.write_text(FAKE_CLAUDE, encoding="utf-8")
        self.claude.chmod(0o755)

    def tearDown(self):
        self._tmp.cleanup()

    def queue(self, *lines):
        for line in lines:
            path = line.split("\t")[0]
            f = self.vault / path
            if "gone" not in f.name:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text("x\n", encoding="utf-8")
        (self.vault / "cache" / ".pending-ingest").write_text(
            "".join(line + "\n" for line in lines), encoding="utf-8")

    def args(self, *extra):
        return [sys.executable, str(RUNNER), "--root", str(self.vault),
                "--claude", str(self.claude), *extra]

    def run_batch(self, *extra, env=None):
        return subprocess.run(self.args(*extra), capture_output=True, text=True,
                              cwd=self.vault, timeout=60,
                              env=env if env is not None else self.env())

    @staticmethod
    def env(**kw):
        env = dict(os.environ)
        env.pop("MCP_INGEST_PERMISSION_MODE", None)
        env.update(kw)
        return env

    def pending(self):
        p = self.vault / "cache" / ".pending-ingest"
        return p.read_text(encoding="utf-8").splitlines() if p.exists() else []

    def outcome(self):
        return json.loads((self.vault / "ops" / "ingest" / "last-batch.json")
                          .read_text(encoding="utf-8"))

    def calls(self):
        p = self.vault / "calls.jsonl"
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]

    def statuses(self):
        return {e["path"]: e["status"] for e in self.outcome()["files"]}


class TestBatch(RunnerBase):
    def test_three_drops_one_run(self):
        # Acceptance 1 + 6: one run, empty queue, three entries, three journal entries.
        self.queue("raw/notes/a.md", "raw/notes/b.md\tdemo", "raw/notes/c.md")
        r = self.run_batch()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.pending(), [])
        self.assertFalse((self.vault / "cache" / ".pending-ingest").exists())
        doc = self.outcome()
        self.assertEqual([e["path"] for e in doc["files"]],
                         ["raw/notes/a.md", "raw/notes/b.md", "raw/notes/c.md"])
        self.assertEqual(set(self.statuses().values()), {"ok"})
        self.assertEqual(doc["files"][0]["pages"][0],
                         {"path": "wiki/sources/a.md", "type": "source", "change": "new"})
        log = (self.vault / "wiki" / "log.md").read_text(encoding="utf-8")
        self.assertEqual(log.count("] ingest |"), 3)
        self.assertEqual(len(self.calls()), 3)

    def test_spawns_the_guarded_headless_command(self):
        self.queue("raw/notes/a.md")
        self.run_batch(env=self.env(MCP_INGEST_PERMISSION_MODE="auto"))
        argv = self.calls()[0]
        self.assertEqual(argv[:2], ["-p", "/ingest raw/notes/a.md --headless"])
        self.assertEqual(argv[2], "--settings")
        settings = json.loads(argv[3])
        self.assertEqual(settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"],
                         str(self.vault / "scripts" / "mcp" / "ingest-headless-guard.sh"))
        self.assertEqual(argv[4:], ["--permission-mode", "auto"])

    def test_failure_does_not_stop_the_batch(self):
        # Acceptance 3: the failed file is reported and kept; the others go through.
        self.queue("raw/notes/a.md", "raw/pdfs/fail.pdf", "raw/notes/c.md")
        r = self.run_batch()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.statuses(), {"raw/notes/a.md": "ok",
                                           "raw/pdfs/fail.pdf": "failed",
                                           "raw/notes/c.md": "ok"})
        failed = self.outcome()["files"][1]
        self.assertIn("exit code 3", failed["detail"])
        self.assertIn("could not read raw/pdfs/fail.pdf", failed["detail"])
        self.assertEqual(self.pending(), ["raw/pdfs/fail.pdf"])
        self.assertIn("raw/pdfs/fail.pdf — failed", r.stdout)
        self.assertIn("next run retries it", r.stdout)

    def test_hint_resolution(self):
        self.queue("raw/notes/a.md\tentry", "raw/notes/b.md", "raw/notes/c.md")
        self.run_batch("--domain-hint", "batch")
        prompts = [argv[1] for argv in self.calls()]
        self.assertEqual(prompts, [
            "/ingest raw/notes/a.md --headless --domain-hint=entry",
            "/ingest raw/notes/b.md --headless --domain-hint=batch",
            "/ingest raw/notes/c.md --headless --domain-hint=batch",
        ])
        self.assertEqual([e["hint"] for e in self.outcome()["files"]],
                         ["entry", "batch", "batch"])

    def test_no_hint_at_all(self):
        self.queue("raw/notes/a.md")
        self.run_batch()
        self.assertEqual(self.calls()[0][1], "/ingest raw/notes/a.md --headless")
        self.assertIsNone(self.outcome()["files"][0]["hint"])

    def test_deferred_to_triage_stays_queued(self):
        self.queue("raw/notes/triage.md", "raw/notes/b.md")
        r = self.run_batch()
        self.assertEqual(self.statuses()["raw/notes/triage.md"], "skipped-no-hint")
        self.assertIn("needs-human-triage", self.outcome()["files"][0]["detail"])
        self.assertEqual(self.pending(), ["raw/notes/triage.md"])
        self.assertIn("domain_hint", r.stdout)

    def test_missing_journal_entry_is_degraded(self):
        self.queue("raw/notes/nojournal.md")
        self.run_batch()
        entry = self.outcome()["files"][0]
        self.assertEqual(entry["status"], "degraded")
        self.assertIn("journal entry missing", entry["detail"])
        self.assertEqual(self.pending(), [])

    def test_stale_entry_is_failed_and_dropped(self):
        self.queue("raw/notes/gone.md", "raw/notes/b.md")
        self.run_batch()
        entry = self.outcome()["files"][0]
        self.assertEqual(entry["status"], "failed")
        self.assertIn("file not found", entry["detail"])
        self.assertEqual(self.pending(), [])
        self.assertEqual(len(self.calls()), 1)

    def test_invalid_entry_is_failed_and_kept(self):
        self.queue("raw/notes/a.md\tBad Slug")
        self.run_batch()
        entry = self.outcome()["files"][0]
        self.assertEqual(entry["status"], "failed")
        self.assertIn("invalid domain_hint", entry["detail"])
        self.assertEqual(self.pending(), ["raw/notes/a.md\tBad Slug"])
        self.assertEqual(self.calls(), [])

    def test_max_files(self):
        self.queue("raw/notes/a.md", "raw/notes/b.md\tdemo", "raw/notes/c.md")
        self.run_batch("--max-files", "1")
        self.assertEqual(list(self.statuses()), ["raw/notes/a.md"])
        self.assertEqual(self.pending(), ["raw/notes/b.md\tdemo", "raw/notes/c.md"])
        self.assertEqual(self.outcome()["remaining"], 2)

    def test_per_file_timeout(self):
        self.queue("raw/notes/slow.md", "raw/notes/b.md")
        r = self.run_batch("--timeout", "0.5")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.statuses(), {"raw/notes/slow.md": "failed",
                                           "raw/notes/b.md": "ok"})
        self.assertIn("timeout", self.outcome()["files"][0]["detail"])
        self.assertEqual(self.pending(), ["raw/notes/slow.md"])

    def test_claude_not_found(self):
        self.queue("raw/notes/a.md")
        r = subprocess.run([sys.executable, str(RUNNER), "--root", str(self.vault)],
                           capture_output=True, text=True, cwd=self.vault,
                           env=self.env(PATH=str(self.vault / "empty-bin")), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        entry = self.outcome()["files"][0]
        self.assertEqual(entry["status"], "failed")
        self.assertIn("`claude` CLI not found", entry["detail"])
        self.assertEqual(self.pending(), ["raw/notes/a.md"])

    def test_empty_queue(self):
        r = self.run_batch()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Nothing pending", r.stdout)
        self.assertEqual(self.outcome()["files"], [])

    def test_report_states_outcome_path(self):
        self.queue("raw/notes/a.md")
        r = self.run_batch()
        self.assertIn("ops/ingest/last-batch.json", r.stdout)
        self.assertIn("Summary: 1 ok · 0 degraded · 0 failed · 0 skipped-no-hint", r.stdout)

    def test_bad_arguments(self):
        for extra in (["--domain-hint", "Not A Slug"], ["--max-files", "-1"]):
            with self.subTest(extra=extra):
                r = self.run_batch(*extra)
                self.assertEqual(r.returncode, 2)
                self.assertFalse((self.vault / "ops").exists())


class TestInterrupt(RunnerBase):
    def test_interrupted_batch_leaves_unprocessed_entries(self):
        self.queue("raw/notes/a.md", "raw/notes/slow.md", "raw/notes/c.md")
        proc = subprocess.Popen(self.args(), cwd=self.vault, env=self.env(),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        end = time.monotonic() + 20
        while len(self.calls()) < 2 and time.monotonic() < end:
            time.sleep(0.05)
        self.assertEqual(len(self.calls()), 2)
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=30)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.pending(), ["raw/notes/slow.md", "raw/notes/c.md"])
        doc = self.outcome()
        self.assertTrue(doc["interrupted"])
        self.assertEqual(self.statuses(), {"raw/notes/a.md": "ok",
                                           "raw/notes/slow.md": "failed"})
        self.assertFalse((self.vault / "cache" / "ingest.lock").exists())


class TestLock(RunnerBase):
    def test_busy_lock_means_no_run(self):
        holder = subprocess.Popen(["sleep", "30"])
        self.addCleanup(holder.wait)
        self.addCleanup(holder.kill)
        (self.vault / "cache" / "ingest.lock").write_text(
            json.dumps({"pid": holder.pid, "owner": "mcp job x", "started_at": time.time()}),
            encoding="utf-8")
        self.queue("raw/notes/a.md")
        r = self.run_batch("--lock-wait", "0")
        self.assertEqual(r.returncode, 3)
        self.assertIn("cache/ingest.lock", r.stderr)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.pending(), ["raw/notes/a.md"])
        self.assertFalse((self.vault / "ops" / "ingest" / "last-batch.json").exists())

    def test_lock_released_after_the_run(self):
        self.queue("raw/notes/a.md")
        self.run_batch()
        self.assertFalse((self.vault / "cache" / "ingest.lock").exists())


class TestOutcomeFile(RunnerBase):
    def test_fixture_matches_the_schema(self):
        check_outcome_schema(self, json.loads(FIXTURE.read_text(encoding="utf-8")))

    def test_written_outcome_matches_the_schema(self):
        self.queue("raw/notes/a.md", "raw/pdfs/fail.pdf", "raw/notes/triage.md",
                   "raw/notes/nojournal.md")
        self.run_batch("--trigger", "scheduled")
        doc = self.outcome()
        check_outcome_schema(self, doc)
        self.assertEqual(doc["trigger"], "scheduled")
        self.assertEqual(doc["counts"], {"total": 4, "ok": 1, "degraded": 1,
                                         "failed": 1, "skipped-no-hint": 1})
        self.assertEqual(doc["remaining"], 2)
        leftovers = [p.name for p in (self.vault / "ops" / "ingest").iterdir()]
        self.assertEqual(leftovers, ["last-batch.json"])  # atomic: no temp file


class TestLedgerEvent(RunnerBase):
    REQUIRED = {"schema_version", "event_type", "run_id", "client_id", "pipeline_id",
                "pipeline_version", "trigger", "started_at", "ended_at", "duration_ms",
                "status", "error", "substrate", "provider", "usage", "cost", "units"}

    def test_no_ledger_config_no_event(self):
        self.queue("raw/notes/a.md")
        self.run_batch()
        self.assertFalse((self.vault / "ops" / "metrics").exists())

    def test_one_event_per_batch(self):
        metrics = self.vault / "ops" / "metrics"
        metrics.mkdir(parents=True)
        (metrics / "ledger.config.json").write_text(
            json.dumps({"client_id": "demo-vault", "pipeline_id": "ingest"}), encoding="utf-8")
        self.queue("raw/notes/a.md", "raw/pdfs/fail.pdf")
        self.run_batch("--trigger", "scheduled")
        lines = (metrics / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        ev = json.loads(lines[0])
        self.assertTrue(self.REQUIRED <= set(ev))
        self.assertEqual(ev["schema_version"], "1.1")
        self.assertEqual(ev["event_type"], "run")
        self.assertEqual(ev["client_id"], "demo-vault")
        self.assertEqual(ev["pipeline_id"], "ingest-pending")
        self.assertEqual(ev["trigger"], "scheduled")
        self.assertEqual(ev["status"], "partial")
        self.assertEqual(ev["error"]["type"], "batch_failures")
        # The runner itself calls no model: the per-file claude runs are
        # captured by the vault's own ledger hooks, if any.
        self.assertEqual(ev["substrate"], "deterministic")
        self.assertEqual(ev["provider"], "none")
        self.assertEqual(ev["usage"]["models"], [])
        self.assertEqual(ev["cost"], {"type": "none", "amount_usd": 0})
        self.assertEqual(ev["units"], [{"kind": "source", "count": 2}])
        self.assertIn({"kind": "failed", "count": 1}, ev["outcomes"])
        self.assertRegex(ev["started_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


if __name__ == "__main__":
    unittest.main()
