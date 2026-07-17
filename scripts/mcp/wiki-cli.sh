#!/usr/bin/env bash
# wiki-cli.sh — portable wrapper over wiki-cli.py.
# Resolves a functional Python interpreter the same way scan-raw.sh does
# (Windows ships only python.exe, and bare "python3" may resolve to the
# non-functional Microsoft Store stub), then execs the CLI with all args.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  fi
fi
if [ -z "$PYTHON_BIN" ] || ! "$PYTHON_BIN" -c "import sys" >/dev/null 2>&1; then
  echo "ERROR: no functional Python interpreter found (python3/python missing or unusable — Windows Store stub?)." >&2
  echo "       wiki-cli.sh needs it to run wiki-cli.py. Install Python 3, or set \$PYTHON_BIN." >&2
  exit 1
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/wiki-cli.py" "$@"
