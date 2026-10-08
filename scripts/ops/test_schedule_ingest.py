#!/usr/bin/env python3
"""unittest suite for schedule-ingest.sh (#154). HOME, the target
directories and the launchctl / systemctl / crontab binaries are overridden
through the environment, so no test ever touches the real user schedule:
the fakes only log their arguments (and the fake crontab keeps its table in
a temp file).

Run: python3 -m unittest discover -s scripts/ops -p "test_*.py"
"""
import os
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "schedule-ingest.sh"

FAKE_LOGGER = """#!/bin/sh
echo "$(basename "$0") $*" >> "$FAKE_LOG"
"""
FAKE_SYSTEMCTL = """#!/bin/sh
echo "systemctl $*" >> "$FAKE_LOG"
if [ "$2" = "show-environment" ] && [ -n "$FAKE_NO_SYSTEMD" ]; then exit 1; fi
exit 0
"""
FAKE_CRONTAB = """#!/bin/sh
echo "crontab $*" >> "$FAKE_LOG"
case "$1" in
  -l) [ -f "$FAKE_CRONTAB_FILE" ] || { echo "no crontab for user" >&2; exit 1; }
      cat "$FAKE_CRONTAB_FILE" ;;
  -r) rm -f "$FAKE_CRONTAB_FILE" ;;
  -) cat > "$FAKE_CRONTAB_FILE" ;;
esac
"""


class ScheduleBase(unittest.TestCase):
    OS = "Darwin"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name).resolve()
        self.home = tmp / "home"
        self.home.mkdir()
        self.vault = tmp / "my vault"
        (self.vault / "scripts" / "ops").mkdir(parents=True)
        self.bin = tmp / "bin"
        self.bin.mkdir()
        for name, body in (("launchctl", FAKE_LOGGER), ("systemctl", FAKE_SYSTEMCTL),
                           ("crontab", FAKE_CRONTAB), ("claude", "#!/bin/sh\n")):
            (self.bin / name).write_text(body, encoding="utf-8")
            (self.bin / name).chmod(0o755)
        self.log = tmp / "calls.log"
        self.crontab_file = tmp / "crontab.txt"

    def tearDown(self):
        self._tmp.cleanup()

    def run_script(self, *args, os_name=None, **env):
        full = dict(os.environ)
        full.update({
            "HOME": str(self.home),
            "SCHEDULE_INGEST_OS": os_name or self.OS,
            "LAUNCHCTL": str(self.bin / "launchctl"),
            "SYSTEMCTL": str(self.bin / "systemctl"),
            "CRONTAB": str(self.bin / "crontab"),
            "CLAUDE_BIN": str(self.bin / "claude"),
            "FAKE_LOG": str(self.log),
            "FAKE_CRONTAB_FILE": str(self.crontab_file),
        })
        full.pop("XDG_CONFIG_HOME", None)
        full.update(env)
        return subprocess.run(["bash", str(SCRIPT), *args, "--root", str(self.vault)],
                              capture_output=True, text=True, env=full, timeout=60)

    def calls(self):
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def files_under_home(self):
        return sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*") if p.is_file())


class TestArguments(ScheduleBase):
    def test_at_format(self):
        for bad in ("25:00", "7:5", "12:60", "noon", ""):
            with self.subTest(at=bad):
                r = self.run_script("install", "--at", bad)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("HH:MM", r.stderr)
        self.assertEqual(self.files_under_home(), [])

    def test_domain_hint_slug(self):
        r = self.run_script("install", "--at", "02:00", "--domain-hint", "Not A Slug")
        self.assertEqual(r.returncode, 2)
        self.assertIn("domain-hint", r.stderr)

    def test_at_required_and_unknown_command(self):
        self.assertEqual(self.run_script("install").returncode, 2)
        self.assertEqual(self.run_script("frobnicate").returncode, 2)

    def test_windows_is_out_of_scope(self):
        r = self.run_script("install", "--at", "02:00", os_name="MINGW64_NT-10.0")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Task Scheduler", r.stderr)
        self.assertEqual(self.files_under_home(), [])

    def test_claude_must_be_found(self):
        r = self.run_script("install", "--at", "02:00",
                            CLAUDE_BIN="", PATH="/usr/bin:/bin")
        self.assertEqual(r.returncode, 1)
        self.assertIn("claude", r.stderr)


class TestLaunchAgent(ScheduleBase):
    OS = "Darwin"

    def plist(self):
        found = list((self.home / "Library" / "LaunchAgents").glob("*.plist"))
        self.assertEqual(len(found), 1)
        return found[0]

    def test_install_writes_a_valid_plist(self):
        r = self.run_script("install", "--at", "02:30", "--domain-hint", "work",
                            "--permission-mode", "auto")
        self.assertEqual(r.returncode, 0, r.stderr)
        path = self.plist()
        if shutil.which("plutil"):
            lint = subprocess.run(["plutil", "-lint", str(path)], capture_output=True, text=True)
            self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)
        with open(path, "rb") as f:
            plist = plistlib.load(f)
        self.assertEqual(path.name, plist["Label"] + ".plist")
        self.assertEqual(plist["StartCalendarInterval"], {"Hour": 2, "Minute": 30})
        args = plist["ProgramArguments"]
        self.assertEqual(args[1], str(self.vault / "scripts" / "ops" / "ingest-pending.py"))
        self.assertEqual(args[2:], ["--root", str(self.vault), "--trigger", "scheduled",
                                    "--claude", str(self.bin / "claude"),
                                    "--domain-hint", "work"])
        self.assertTrue(plist["EnvironmentVariables"]["PATH"].startswith(str(self.bin) + ":"))
        self.assertEqual(plist["EnvironmentVariables"]["MCP_INGEST_PERMISSION_MODE"], "auto")
        log = str(self.vault / "ops" / "ingest" / "scheduled.log")
        self.assertEqual(plist["StandardOutPath"], log)
        self.assertEqual(plist["StandardErrorPath"], log)
        self.assertEqual(plist["WorkingDirectory"], str(self.vault))
        self.assertTrue((self.vault / "ops" / "ingest").is_dir())
        self.assertTrue(any(c.startswith(f"launchctl bootstrap gui/{os.getuid()} ")
                            for c in self.calls()), self.calls())

    def test_uninstall_leaves_nothing(self):
        self.run_script("install", "--at", "02:30")
        r = self.run_script("uninstall")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.files_under_home(), [])
        self.assertFalse((self.vault / "ops").exists())
        self.assertTrue(any(c.startswith("launchctl bootout") for c in self.calls()))

    def test_reinstall_replaces_and_status_reports(self):
        self.run_script("install", "--at", "02:30")
        self.run_script("install", "--at", "06:15")
        with open(self.plist(), "rb") as f:
            self.assertEqual(plistlib.load(f)["StartCalendarInterval"],
                             {"Hour": 6, "Minute": 15})
        r = self.run_script("status")
        self.assertEqual(r.returncode, 0)
        self.assertIn("installed", r.stdout)
        self.assertIn("06:15", r.stdout)

    def test_status_when_not_installed(self):
        r = self.run_script("status")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not installed", r.stdout)

    def test_label_differs_per_vault(self):
        self.run_script("install", "--at", "02:30")
        other = self.vault.parent / "other"
        (other / "scripts" / "ops").mkdir(parents=True)
        env = {"HOME": str(self.home)}
        r = subprocess.run(["bash", str(SCRIPT), "install", "--at", "03:00", "--root", str(other)],
                           capture_output=True, text=True,
                           env={**os.environ, **env, "SCHEDULE_INGEST_OS": "Darwin",
                                "LAUNCHCTL": str(self.bin / "launchctl"),
                                "CLAUDE_BIN": str(self.bin / "claude"),
                                "FAKE_LOG": str(self.log)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(list((self.home / "Library" / "LaunchAgents").glob("*.plist"))), 2)

    def test_bootstrap_falls_back_to_load(self):
        (self.bin / "launchctl").write_text(
            '#!/bin/sh\necho "launchctl $*" >> "$FAKE_LOG"\n'
            '[ "$1" = "bootstrap" ] && exit 5\nexit 0\n', encoding="utf-8")
        r = self.run_script("install", "--at", "02:30")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(any(c.startswith("launchctl load ") for c in self.calls()))


class TestSystemdTimer(ScheduleBase):
    OS = "Linux"

    def units(self):
        return sorted((self.home / ".config" / "systemd" / "user").glob("boilingbrain-ingest-*"))

    def test_install_writes_service_and_timer(self):
        r = self.run_script("install", "--at", "02:30", "--domain-hint", "work")
        self.assertEqual(r.returncode, 0, r.stderr)
        service, timer = self.units()
        self.assertEqual(service.suffix, ".service")
        self.assertEqual(timer.suffix, ".timer")
        svc = service.read_text(encoding="utf-8")
        self.assertIn("Type=oneshot", svc)
        self.assertIn(f'"{self.vault}/scripts/ops/ingest-pending.py" "--root" "{self.vault}"', svc)
        self.assertIn('"--domain-hint" "work"', svc)
        self.assertIn(f"append:{self.vault}/ops/ingest/scheduled.log", svc)
        self.assertIn(f'Environment="PATH={self.bin}:', svc)
        tim = timer.read_text(encoding="utf-8")
        self.assertIn("OnCalendar=*-*-* 02:30:00", tim)
        self.assertIn("Persistent=true", tim)
        self.assertIn(f"Unit={service.name}", tim)
        self.assertIn(f"systemctl --user enable --now {timer.name}", self.calls())
        if shutil.which("systemd-analyze"):
            # --user verify needs a runtime dir (absent in containers / CI).
            runtime = Path(self._tmp.name) / "runtime"
            runtime.mkdir(mode=0o700)
            env = dict(os.environ)
            env.setdefault("XDG_RUNTIME_DIR", str(runtime))
            verify = subprocess.run(["systemd-analyze", "--user", "verify", str(service),
                                     str(timer)], capture_output=True, text=True, env=env)
            self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)

    def test_uninstall_leaves_nothing(self):
        self.run_script("install", "--at", "02:30")
        r = self.run_script("uninstall")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.units(), [])
        self.assertEqual(self.files_under_home(), [])
        self.assertTrue(any(c.startswith("systemctl --user disable --now") for c in self.calls()))

    def test_percent_in_path_is_escaped(self):
        vault = self.vault.parent / "100%"
        (vault / "scripts" / "ops").mkdir(parents=True)
        self.vault = vault
        self.run_script("install", "--at", "02:30")
        svc = self.units()[0].read_text(encoding="utf-8")
        self.assertIn("100%%/scripts/ops/ingest-pending.py", svc)


class TestCronFallback(ScheduleBase):
    OS = "Linux"

    def test_install_and_uninstall_crontab_line(self):
        self.crontab_file.write_text("0 1 * * * echo keep\n", encoding="utf-8")
        r = self.run_script("install", "--at", "02:30", FAKE_NO_SYSTEMD="1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("crontab", r.stdout)
        lines = self.crontab_file.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "0 1 * * * echo keep")
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith("30 2 * * * "))
        self.assertIn("ingest-pending.py", lines[1])
        self.assertIn("# boilingbrain-ingest-", lines[1])
        self.assertEqual(self.files_under_home(), [])
        # Re-install: still one line.
        self.run_script("install", "--at", "04:00", FAKE_NO_SYSTEMD="1")
        lines = self.crontab_file.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith("0 4 * * * "))
        self.run_script("uninstall", FAKE_NO_SYSTEMD="1")
        self.assertEqual(self.crontab_file.read_text(encoding="utf-8"), "0 1 * * * echo keep\n")

    def test_uninstall_removes_a_crontab_it_emptied(self):
        self.run_script("install", "--at", "02:30", FAKE_NO_SYSTEMD="1")
        self.run_script("uninstall", FAKE_NO_SYSTEMD="1")
        self.assertFalse(self.crontab_file.exists())

    def test_single_quote_in_path_is_refused(self):
        vault = self.vault.parent / "it's"
        (vault / "scripts" / "ops").mkdir(parents=True)
        self.vault = vault
        r = self.run_script("install", "--at", "02:30", FAKE_NO_SYSTEMD="1")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(self.crontab_file.exists())


if __name__ == "__main__":
    unittest.main()
