#!/usr/bin/env python3
"""Smoke test for the MCP server tools against a real vault.

Usage:
  WIKI_PATH=/path/to/vault python3 scripts/mcp/smoke_test.py [domain]

Loads the MCP module (without starting the server), invokes each tool with a
canonical input, prints the result length in characters and an approximate
token count, and exits non-zero if any output exceeds the Phase 5 gate limits.

Default domain: 'ia' (matches the BoilingBrain reference). Override via argv.
"""
import os
import sys
import importlib.util
import pathlib

DEFAULT_DOMAIN = sys.argv[1] if len(sys.argv) > 1 else "ia"

if not os.environ.get("WIKI_PATH"):
    print("Error: WIKI_PATH env var required. Usage: WIKI_PATH=/path/to/vault python3 smoke_test.py [domain]", file=sys.stderr)
    sys.exit(1)

spec = importlib.util.spec_from_file_location(
    "mcp_wiki",
    str(pathlib.Path(__file__).parent / "mcp-wiki.py"),
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


GATES = [
    ("scan_domain", lambda: m.scan_domain(DEFAULT_DOMAIN), 1500),
    ("scan_concepts (query)", lambda: m.scan_concepts(DEFAULT_DOMAIN, query="alignement"), 800),
    ("scan_concepts (no query)", lambda: m.scan_concepts(DEFAULT_DOMAIN), 800),
    ("scan_entities (no query)", lambda: m.scan_entities(DEFAULT_DOMAIN), 800),
    ("scan_decisions (no query)", lambda: m.scan_decisions(DEFAULT_DOMAIN), 800),
    ("scan_sources (no query, must refuse)", lambda: m.scan_sources(DEFAULT_DOMAIN), 200),
    ("scan_sources (query)", lambda: m.scan_sources(DEFAULT_DOMAIN, query="alignement"), 800),
    ("search_wiki (mcp)", lambda: m.search_wiki("model context protocol"), 800),
]

failures = []
for name, fn, max_tokens in GATES:
    out = fn()
    chars = len(out)
    tokens = chars // 4
    status = "OK" if tokens <= max_tokens else "FAIL"
    print(f"[{status}] {name}: {chars} chars (~{tokens} tokens, cap {max_tokens})")
    if status == "FAIL":
        failures.append((name, tokens, max_tokens))

print()
if failures:
    print(f"{len(failures)} gate(s) failed:")
    for name, t, cap in failures:
        print(f"  - {name}: {t} > {cap}")
    sys.exit(1)
print("All gates passed.")
