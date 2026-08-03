#!/usr/bin/env python3
"""register-desktop-config.py — merge the boiling-brain-wiki MCP server entry
into Claude Desktop / Cowork's claude_desktop_config.json (#133).

Called by setup-mcp.sh after the Claude Code registration: the Desktop app and
Cowork read claude_desktop_config.json — never ~/.claude.json (Claude Code
CLI) — so `claude mcp add` alone leaves them without the connector.

Stdlib only. Content-preserving merge: every other mcpServers entry and every
other top-level key survives the round-trip byte-for-byte at the data level;
formatting is normalized to 2-space indent (the style the Desktop app itself
writes). Atomic write (tmp + os.replace). An existing file that is not valid
JSON is left untouched and reported (exit 2) — never overwritten.

Exit codes: 0 = created/updated/unchanged (stdout says which),
2 = existing file is not valid JSON, argparse's own exit on bad usage.
"""
import argparse
import json
import sys
from pathlib import Path


def merge_entry(config_path: Path, server_name: str, command: str,
                script: str, wiki_path: str) -> str:
    """Merge the server entry into config_path.
    Returns 'created' | 'updated' | 'unchanged'. Raises json.JSONDecodeError
    if the file exists but does not parse — caller reports, file untouched."""
    entry = {"command": command, "args": [script], "env": {"WIKI_PATH": wiki_path}}
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        status = None
    else:
        config = {}
        status = "created"
    servers = config.setdefault("mcpServers", {})
    if status is None:
        status = "unchanged" if servers.get(server_name) == entry else "updated"
    if status != "unchanged":
        servers[server_name] = entry
        tmp = config_path.with_name(config_path.name + ".tmp")
        tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        tmp.replace(config_path)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge an MCP server entry into claude_desktop_config.json.")
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--server-name", required=True)
    parser.add_argument("--command", required=True,
                        help="interpreter able to import fastmcp (resolved by setup-mcp.sh)")
    parser.add_argument("--script", required=True, help="absolute path to mcp-wiki.py")
    parser.add_argument("--wiki-path", required=True, help="vault root, becomes WIKI_PATH")
    args = parser.parse_args()

    config_path = Path(args.config_path)
    try:
        status = merge_entry(config_path, args.server_name, args.command,
                             args.script, args.wiki_path)
    except json.JSONDecodeError as e:
        print(f"ERROR: {config_path} exists but is not valid JSON ({e}); "
              f"left untouched — fix or remove it, then re-run.", file=sys.stderr)
        return 2
    print(f"✅ {config_path} {status} ('{args.server_name}' entry for Desktop/Cowork).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
