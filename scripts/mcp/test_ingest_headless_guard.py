#!/usr/bin/env python3
"""unittest suite for ingest-headless-guard.sh — runs the hook as a subprocess
with synthetic PreToolUse payloads and asserts allow (exit 0) / deny (exit 2).

Run: cd scripts/mcp && python3 -m unittest test_ingest_headless_guard
Requires NO fastmcp (pure bash + stdlib).

Pins the tool vocabulary the headless /ingest workflow depends on: an upstream
tool rename (Task -> Agent, #125) must show up here as a red test, not as a
silently degraded ingest run.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parent / "ingest-headless-guard.sh"


def run_guard(payload, vault):
    env = dict(os.environ, VAULT_PATH=str(vault))
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        ["bash", str(GUARD)], input=stdin,
        capture_output=True, text=True, env=env)


class TestIngestHeadlessGuard(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def assert_allowed(self, payload):
        r = run_guard(payload, self.vault)
        self.assertEqual(r.returncode, 0, f"expected allow, got: {r.stderr}")

    def assert_denied(self, payload, fragment=""):
        r = run_guard(payload, self.vault)
        self.assertEqual(r.returncode, 2, f"expected deny, got rc={r.returncode}")
        if fragment:
            self.assertIn(fragment, r.stderr)

    # --- Tool vocabulary (pinned): a rename upstream must turn this red ---

    def test_subagent_spawn_tools_allowed(self):
        for name in ("Task", "Agent"):
            with self.subTest(tool=name):
                self.assert_allowed({"tool_name": name, "tool_input": {}})

    def test_read_side_tools_allowed(self):
        for name in ("Read", "Glob", "Grep", "ToolSearch", "TodoWrite"):
            with self.subTest(tool=name):
                self.assert_allowed({"tool_name": name, "tool_input": {}})

    def test_unknown_tool_denied_loudly(self):
        r = run_guard({"tool_name": "WebSearch", "tool_input": {}}, self.vault)
        self.assertEqual(r.returncode, 2)
        self.assertIn("not explicitly allowed", r.stderr)
        self.assertIn("DEGRADED", r.stderr)  # loud-fail wording (#125)

    # --- Write scope ---

    def test_write_wiki_page_allowed(self):
        self.assert_allowed({"tool_name": "Write", "tool_input": {
            "file_path": str(self.vault / "wiki" / "concepts" / "x.md")}})

    def test_write_agent_memory_allowed(self):
        self.assert_allowed({"tool_name": "Write", "tool_input": {
            "file_path": str(self.vault / ".claude" / "agent-memory" / "demo-expert" / "MEMORY.md")}})

    def test_write_expert_suggestions_allowed(self):
        self.assert_allowed({"tool_name": "Edit", "tool_input": {
            "file_path": str(self.vault / ".claude" / "agents" / "demo-expert.suggestions.md")}})

    def test_write_outside_scope_denied(self):
        self.assert_denied({"tool_name": "Write", "tool_input": {
            "file_path": str(self.vault / ".claude" / "settings.json")}},
            "write outside the allowed scope")

    # --- Bash ---

    def test_bash_allowlisted_command_allowed(self):
        self.assert_allowed({"tool_name": "Bash", "tool_input": {
            "command": "shasum -a 256 raw/notes/x.md"}})

    def test_bash_unlisted_command_denied(self):
        self.assert_denied({"tool_name": "Bash", "tool_input": {
            "command": "rm -rf wiki"}}, "not in allowlist")

    # --- Robustness ---

    def test_invalid_json_denied(self):
        r = run_guard("not json at all", self.vault)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
