#!/usr/bin/env python3
"""unittest suite for register-desktop-config.py — drives the CLI via
subprocess on temp config files (#133).

Run: cd scripts/mcp && python3 -m unittest test_register_desktop_config
Requires NO fastmcp (stdlib only).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HELPER = Path(__file__).resolve().parent / "register-desktop-config.py"


def run_helper(config_path, name="boiling-brain-wiki",
               command="/opt/venv/bin/python", script="/vault/scripts/mcp/mcp-wiki.py",
               wiki_path="/vault"):
    return subprocess.run(
        [sys.executable, str(HELPER),
         "--config-path", str(config_path),
         "--server-name", name,
         "--command", command,
         "--script", script,
         "--wiki-path", wiki_path],
        capture_output=True, text=True)


EXPECTED_ENTRY = {
    "command": "/opt/venv/bin/python",
    "args": ["/vault/scripts/mcp/mcp-wiki.py"],
    "env": {"WIKI_PATH": "/vault"},
}


class TestRegisterDesktopConfig(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.config = Path(self._tmp.name) / "claude_desktop_config.json"

    def tearDown(self):
        self._tmp.cleanup()

    def read(self):
        return json.loads(self.config.read_text(encoding="utf-8"))

    def test_absent_file_created_with_entry(self):
        r = run_helper(self.config)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("created", r.stdout)
        self.assertEqual(self.read()["mcpServers"]["boiling-brain-wiki"], EXPECTED_ENTRY)

    def test_existing_servers_and_keys_preserved(self):
        self.config.write_text(json.dumps({
            "globalShortcut": "Cmd+Space",
            "mcpServers": {"other-server": {"command": "npx", "args": ["-y", "x"]}},
        }), encoding="utf-8")
        r = run_helper(self.config)
        self.assertEqual(r.returncode, 0, r.stderr)
        config = self.read()
        self.assertEqual(config["globalShortcut"], "Cmd+Space")
        self.assertEqual(config["mcpServers"]["other-server"],
                         {"command": "npx", "args": ["-y", "x"]})
        self.assertEqual(config["mcpServers"]["boiling-brain-wiki"], EXPECTED_ENTRY)

    def test_rerun_is_idempotent_unchanged(self):
        run_helper(self.config)
        before = self.config.read_text(encoding="utf-8")
        r = run_helper(self.config)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("unchanged", r.stdout)
        self.assertEqual(self.config.read_text(encoding="utf-8"), before)

    def test_stale_entry_updated_in_place(self):
        self.config.write_text(json.dumps({
            "mcpServers": {"boiling-brain-wiki": {
                "command": "/usr/bin/python3", "args": ["/old/mcp-wiki.py"],
                "env": {"WIKI_PATH": "/old"}}},
        }), encoding="utf-8")
        r = run_helper(self.config)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("updated", r.stdout)
        servers = self.read()["mcpServers"]
        self.assertEqual(list(servers), ["boiling-brain-wiki"])
        self.assertEqual(servers["boiling-brain-wiki"], EXPECTED_ENTRY)

    def test_invalid_json_left_untouched_exit_2(self):
        self.config.write_text("{not json", encoding="utf-8")
        r = run_helper(self.config)
        self.assertEqual(r.returncode, 2)
        self.assertIn("not valid JSON", r.stderr)
        self.assertEqual(self.config.read_text(encoding="utf-8"), "{not json")

    def test_missing_argument_fails(self):
        r = subprocess.run([sys.executable, str(HELPER), "--config-path", str(self.config)],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
