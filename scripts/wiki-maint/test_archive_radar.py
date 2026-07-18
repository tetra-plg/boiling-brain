#!/usr/bin/env python3
"""unittest suite for archive-radar.py — drives the CLI on temp fixture vaults.

Run: cd scripts/wiki-maint && python3 -m unittest test_archive_radar
"""
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "archive-radar.py"
VALIDATE = Path(__file__).resolve().parent / "validate-wiki.py"

RADAR_FM = textwrap.dedent("""\
    ---
    type: radar
    domains: [demo]
    created: 2026-01-01
    updated: 2026-01-01
    summary_l0: "Open questions — 1 active."
    summary_l1: |
      Active radar.
    ---
    """)

ARCHIVE_FM = textwrap.dedent("""\
    ---
    type: reference
    domains: [meta]
    created: 2026-01-01
    updated: 2026-01-01
    summary_l0: "Archived radar entries."
    summary_l1: |
      Archive.
    ---
    """)


def write_vault(tmp, radar=None, archive=None):
    (tmp / "wiki").mkdir(parents=True, exist_ok=True)
    if radar is not None:
        (tmp / "wiki" / "radar.md").write_text(radar, encoding="utf-8")
    if archive is not None:
        (tmp / "wiki" / "radar-archive.md").write_text(archive, encoding="utf-8")


def run(tmp, date="2026-07-18"):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp), "--date", date],
        capture_output=True, text=True,
    )


def read(tmp, name):
    return (tmp / "wiki" / name).read_text(encoding="utf-8")


class MoveHappyPathTest(unittest.TestCase):
    def test_moves_checked_entry_to_matching_section(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            radar = RADAR_FM + textwrap.dedent("""\

                # Radar

                ## Section A

                - [ ] open one
                - [x] done one **TRAITE 2026-07-01**

                ## Section B

                - [ ] open two
                """)
            archive = ARCHIVE_FM + textwrap.dedent("""\

                # Archive

                ## Section A

                - [x] old archived one
                """)
            write_vault(tmp, radar=radar, archive=archive)
            r = run(tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            radar_out = read(tmp, "radar.md")
            archive_out = read(tmp, "radar-archive.md")
            # removed from radar
            self.assertNotIn("done one", radar_out)
            # open entries untouched
            self.assertIn("- [ ] open one", radar_out)
            self.assertIn("- [ ] open two", radar_out)
            # moved into archive Section A, after existing entry
            self.assertIn("- [x] done one", archive_out)
            self.assertIn("old archived one", archive_out)
            self.assertLess(archive_out.index("old archived one"),
                            archive_out.index("done one"))

    def test_preserves_resolution_text(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            entry = "- [x] fix parser **TRAITE 2026-07-01** details -> outcome"
            radar = RADAR_FM + "\n# Radar\n\n## Section A\n\n" + entry + "\n"
            archive = ARCHIVE_FM + "\n# Archive\n\n## Section A\n\n- [x] prior\n"
            write_vault(tmp, radar=radar, archive=archive)
            r = run(tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn(entry, read(tmp, "radar-archive.md"))

    def test_reports_archived_count(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            radar = RADAR_FM + "\n# Radar\n\n## Section A\n\n- [x] a\n- [x] b\n"
            archive = ARCHIVE_FM + "\n# Archive\n\n## Section A\n\n- [x] prior\n"
            write_vault(tmp, radar=radar, archive=archive)
            r = run(tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("archived=2", r.stdout)


class SectionRoutingTest(unittest.TestCase):
    def test_creates_matching_section_when_absent(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            radar = RADAR_FM + "\n# Radar\n\n## New Topic\n\n- [x] resolved thing\n"
            archive = ARCHIVE_FM + "\n# Archive\n\n## Other\n\n- [x] prior\n"
            write_vault(tmp, radar=radar, archive=archive)
            r = run(tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            archive_out = read(tmp, "radar-archive.md")
            self.assertIn("## New Topic", archive_out)
            self.assertIn("- [x] resolved thing", archive_out)
            self.assertIn("## Other", archive_out)  # existing kept

    def test_headerless_entry_goes_to_generic_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            # [x] appears before any level-2 header
            radar = RADAR_FM + "\n# Radar\n\n- [x] loose entry\n\n## Section A\n\n- [ ] open\n"
            archive = ARCHIVE_FM + "\n# Archive\n"
            write_vault(tmp, radar=radar, archive=archive)
            r = run(tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            archive_out = read(tmp, "radar-archive.md")
            self.assertIn("## Handled", archive_out)
            self.assertIn("- [x] loose entry", archive_out)
            self.assertIn("section:Handled=1", r.stdout)


if __name__ == "__main__":
    unittest.main()
