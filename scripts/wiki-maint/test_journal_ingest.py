#!/usr/bin/env python3
"""unittest suite for journal-ingest.py — drives the CLI on temp fixture vaults.

Run: cd scripts/wiki-maint && python3 -m unittest test_journal_ingest
"""
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "journal-ingest.py"

LOG = textwrap.dedent("""\
    ---
    type: log
    ---

    # Log

    > Chronological journal.
    """)

RADAR = textwrap.dedent("""\
    ---
    type: radar
    updated: 2026-01-01
    ---

    # Radar

    ---

    ## To verify (facts to confirm)

    <!-- Items to confirm. -->

    ## To research (gaps to fill)

    <!-- Concepts heard. -->

    ## To watch (weak signals)

    <!-- Trends. -->
    """)

REPORT = textwrap.dedent("""\
    ---
    source: raw/notes/2026-10-08-my-note.md
    title: My Note: a subtitle
    agent: tech-expert
    mode: headless
    hint: tech
    date: 2026-10-08
    ---

    ## Ingest summary

    - Pages created: [[wiki/sources/my-note]], [[wiki/concepts/foo]]
    - Pages updated: [[wiki/domains/tech]]

    ## Radar items

    - [verify] Exact value of X in the vendor doc.
    - [watch] Feature Y is in preview.
    - Something with no tag.

    ## Evolution suggestions

    - N/A
    """)


class JournalBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "wiki").mkdir()
        (self.root / "cache" / "ingest-reports").mkdir(parents=True)
        (self.root / "wiki" / "log.md").write_text(LOG, encoding="utf-8")
        (self.root / "wiki" / "radar.md").write_text(RADAR, encoding="utf-8")
        self.report = self.root / "cache" / "ingest-reports" / "2026-10-08-my-note.md"
        self.report.write_text(REPORT, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def run_script(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root), *args],
            capture_output=True, text=True)

    def log(self):
        return (self.root / "wiki" / "log.md").read_text(encoding="utf-8")

    def radar(self):
        return (self.root / "wiki" / "radar.md").read_text(encoding="utf-8")


class TestLogEntry(JournalBase):
    def test_headless_entry_format(self):
        r = self.run_script(str(self.report))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(
            "## [2026-10-08] ingest | My Note: a subtitle "
            "(agent: tech-expert, mode: headless, hint: tech)\n", self.log())
        self.assertIn("- Source: `raw/notes/2026-10-08-my-note.md`", self.log())
        self.assertIn("- Pages created: [[wiki/sources/my-note]]", self.log())
        self.assertIn("log=appended", r.stdout)

    def test_interactive_entry_has_no_mode(self):
        self.report.write_text(
            REPORT.replace("mode: headless\n", "mode: interactive\n")
                  .replace("hint: tech\n", ""), encoding="utf-8")
        r = self.run_script(str(self.report))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("## [2026-10-08] ingest | My Note: a subtitle (agent: tech-expert)\n",
                      self.log())

    def test_headless_without_hint_says_none(self):
        self.report.write_text(REPORT.replace("hint: tech\n", ""), encoding="utf-8")
        self.run_script(str(self.report))
        self.assertIn("(agent: tech-expert, mode: headless, hint: none)", self.log())

    def test_idempotent_same_source_same_date(self):
        self.run_script(str(self.report))
        r = self.run_script(str(self.report))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.log().count("ingest | My Note"), 1)
        self.assertEqual(self.radar().count("Exact value of X"), 1)
        self.assertIn("log=skipped", r.stdout)

    def test_creates_log_when_absent(self):
        (self.root / "wiki" / "log.md").unlink()
        r = self.run_script(str(self.report))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ingest | My Note", self.log())

    def test_missing_required_key_is_an_error(self):
        self.report.write_text(REPORT.replace("agent: tech-expert\n", ""), encoding="utf-8")
        r = self.run_script(str(self.report))
        self.assertEqual(r.returncode, 2)
        self.assertIn("agent", r.stderr)
        self.assertNotIn("ingest |", self.log())


class TestRadar(JournalBase):
    def test_tagged_items_go_to_matching_section(self):
        self.run_script(str(self.report))
        radar = self.radar()
        verify = radar.index("## To verify")
        research = radar.index("## To research")
        watch = radar.index("## To watch")
        item_x = radar.index("- [ ] **[tech · 2026-10-08]** Exact value of X")
        item_y = radar.index("- [ ] **[tech · 2026-10-08]** Feature Y")
        self.assertTrue(verify < item_x < research)
        self.assertTrue(watch < item_y)

    def test_untagged_item_goes_to_triage_at_top(self):
        r = self.run_script(str(self.report))
        radar = self.radar()
        triage = radar.index("## Triage")
        self.assertLess(triage, radar.index("## To verify"))
        self.assertGreater(radar.index("Something with no tag."), triage)
        self.assertLess(radar.index("Something with no tag."), radar.index("## To verify"))
        self.assertIn("radar=3", r.stdout)
        self.assertIn("triage=1", r.stdout)

    def test_updated_date_bumped(self):
        self.run_script(str(self.report))
        self.assertIn("updated: 2026-10-08", self.radar())

    def test_na_radar_block_writes_nothing(self):
        self.report.write_text(
            REPORT.split("## Radar items")[0] + "## Radar items\n\n- N/A\n", encoding="utf-8")
        before = self.radar()
        r = self.run_script(str(self.report))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.radar(), before)
        self.assertIn("radar=0", r.stdout)

    def test_unknown_tag_goes_to_triage_verbatim(self):
        self.report.write_text(
            REPORT.split("## Radar items")[0] + "## Radar items\n\n- [foo] Odd tag.\n",
            encoding="utf-8")
        r = self.run_script(str(self.report))
        self.assertIn("triage=1", r.stdout)
        self.assertGreater(self.radar().index("[foo] Odd tag."), self.radar().index("## Triage"))

    def test_existing_triage_section_is_reused(self):
        self.run_script(str(self.report))
        other = self.root / "cache" / "ingest-reports" / "other.md"
        other.write_text(REPORT.replace("2026-10-08-my-note.md", "other.md")
                               .replace("Something with no tag.", "Second untagged."),
                         encoding="utf-8")
        self.run_script(str(other))
        radar = self.radar()
        self.assertEqual(radar.count("## Triage"), 1)
        self.assertLess(radar.index("Second untagged."), radar.index("## To verify"))

    def test_absent_radar_is_reported_not_created(self):
        (self.root / "wiki" / "radar.md").unlink()
        r = self.run_script(str(self.report))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.root / "wiki" / "radar.md").exists())
        self.assertIn("radar.md is absent", r.stderr)
        self.assertIn("log=appended", r.stdout)

    def test_unreadable_report_is_an_error(self):
        r = self.run_script(str(self.root / "cache" / "ingest-reports" / "absent.md"))
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("ingest |", self.log())


if __name__ == "__main__":
    unittest.main()
