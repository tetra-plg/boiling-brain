#!/usr/bin/env python3
"""wiki-cli.py — headless CLI over a BoilingBrain vault, no MCP client required.

Reuses wiki_core (no fastmcp dependency). Markdown by default; --json emits the
stable machine-readable shape. Exit codes: 0 on success or legitimate empty
result, 2 on lookup error (message on stderr).

Examples:
  python3 wiki-cli.py search "model context protocol" --limit 5
  python3 wiki-cli.py scan-domain ia --json
  python3 wiki-cli.py scan-concepts ia --query rag --top 10
  python3 wiki-cli.py preview wiki/concepts/foo.md
  WIKI_PATH=/path/to/vault python3 wiki-cli.py read wiki/sources/x.md

JSON shapes are documented in wiki_core.py (the <tool>_data() return values).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wiki_core  # noqa: E402

_SCAN_TYPES = {
    "scan-concepts": "concept", "scan-entities": "entity",
    "scan-decisions": "decision", "scan-syntheses": "synthesis",
    "scan-cheatsheets": "cheatsheet", "scan-diagrams": "diagram",
}


def _emit(data, md_fn, as_json):
    print(wiki_core.to_json(data) if as_json else md_fn(data))


def _build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true",
                        help="Emit JSON instead of markdown.")
    common.add_argument("--wiki-path",
                        help="Vault root (overrides the WIKI_PATH env var).")

    parser = argparse.ArgumentParser(
        prog="wiki-cli",
        description="Query a BoilingBrain vault without an MCP client.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("scan-domain", parents=[common])
    sp.add_argument("domain")

    for name in _SCAN_TYPES:
        sp = sub.add_parser(name, parents=[common])
        sp.add_argument("domain")
        sp.add_argument("--query", default="")
        sp.add_argument("--top", type=int, default=20)

    sp = sub.add_parser("scan-sources", parents=[common])
    sp.add_argument("domain")
    sp.add_argument("--query", default="")
    sp.add_argument("--top", type=int, default=20)

    sp = sub.add_parser("preview", parents=[common])
    sp.add_argument("page_path")

    sp = sub.add_parser("read", parents=[common])
    sp.add_argument("page_path")

    sp = sub.add_parser("search", parents=[common])
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)

    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.wiki_path:
        wiki_core.configure(args.wiki_path)
    try:
        if args.cmd == "scan-domain":
            _emit(wiki_core.scan_domain_data(args.domain),
                  wiki_core.scan_domain_md, args.json)
        elif args.cmd in _SCAN_TYPES:
            _emit(wiki_core.scan_type_data(args.domain, _SCAN_TYPES[args.cmd],
                                           args.query, args.top),
                  wiki_core.scan_type_md, args.json)
        elif args.cmd == "scan-sources":
            _emit(wiki_core.scan_sources_data(args.domain, args.query, args.top),
                  wiki_core.scan_type_md, args.json)
        elif args.cmd == "preview":
            _emit(wiki_core.preview_page_data(args.page_path),
                  wiki_core.preview_page_md, args.json)
        elif args.cmd == "read":
            _emit(wiki_core.read_page_data(args.page_path),
                  wiki_core.read_page_md, args.json)
        elif args.cmd == "search":
            _emit(wiki_core.search_wiki_data(args.query, args.limit),
                  wiki_core.search_wiki_md, args.json)
    except wiki_core.WikiLookupError as e:
        print(str(e), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
