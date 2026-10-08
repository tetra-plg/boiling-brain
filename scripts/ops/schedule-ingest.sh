#!/usr/bin/env bash
# schedule-ingest.sh — run the pending-queue batch (ingest-pending.py) every
# day at a fixed time, locally, with the operator's own Claude Code login (#154).
#
# Usage:
#   bash scripts/ops/schedule-ingest.sh install --at HH:MM [--domain-hint <slug>]
#                                       [--permission-mode <mode>] [--root <vault>]
#   bash scripts/ops/schedule-ingest.sh uninstall [--root <vault>]
#   bash scripts/ops/schedule-ingest.sh status [--root <vault>]
#
# Backends:
#   macOS  → user LaunchAgent ~/Library/LaunchAgents/<label>.plist with
#            StartCalendarInterval (a run missed while the machine slept starts
#            at wake), loaded with `launchctl bootstrap gui/$UID` (fallback
#            `launchctl load`).
#   Linux  → systemd user <unit>.service + <unit>.timer under
#            ~/.config/systemd/user/ (Persistent=true: a missed run starts at
#            the next boot), enabled with `systemctl --user enable --now`. When
#            the systemd user instance is unavailable, a crontab line tagged
#            `# <unit>` instead (cron does not catch up missed runs).
#   Windows → not supported yet (Task Scheduler): clear message, exit 1.
#
# The job runs `<python> <vault>/scripts/ops/ingest-pending.py --root <vault>
# --trigger scheduled --claude <claude> [--domain-hint <slug>]`, appends its
# output to <vault>/ops/ingest/scheduled.log, and gets a PATH holding the
# directories of `claude` (and `node`) captured at install time — launchd,
# systemd and cron all start jobs with a minimal PATH. --permission-mode sets
# MCP_INGEST_PERMISSION_MODE for the job, as for the MCP server (see the
# ingest() tool description): without it, an unattended run may be denied the
# journaling writes.
#
# Label and unit names carry a short hash of the vault path, so several vaults
# can each have their own schedule. `uninstall` removes every file `install`
# created (the empty ops/ingest/ directory included; run outputs stay).
#
# Test hooks (env): SCHEDULE_INGEST_OS (uname -s override), LAUNCHCTL,
# SYSTEMCTL, CRONTAB (binaries), LAUNCH_AGENTS_DIR, SYSTEMD_USER_DIR,
# CLAUDE_BIN, PYTHON_BIN. HOME is honoured for every default path.
#
# Exit codes: 0 success (status: installed), 1 environment error (status: not
# installed), 2 usage error.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VAULT="$(cd "$SCRIPT_DIR/../.." && pwd)"

LAUNCHCTL="${LAUNCHCTL:-launchctl}"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
CRONTAB="${CRONTAB:-crontab}"

die()   { printf 'Error: %s\n' "$*" >&2; exit 1; }
usage() {
  [ $# -gt 0 ] && printf 'Error: %s\n' "$*" >&2
  sed -n '5,9p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit 2
}

# --- arguments ---
[ $# -ge 1 ] || usage "missing command"
CMD="$1"; shift
AT=""; HINT=""; PERM=""
while [ $# -gt 0 ]; do
  case "$1" in
    --at)              [ $# -ge 2 ] || usage "--at needs a value"; AT="$2"; shift 2 ;;
    --domain-hint)     [ $# -ge 2 ] || usage "--domain-hint needs a value"; HINT="$2"; shift 2 ;;
    --permission-mode) [ $# -ge 2 ] || usage "--permission-mode needs a value"; PERM="$2"; shift 2 ;;
    --root)            [ $# -ge 2 ] || usage "--root needs a value"; VAULT="$(cd "$2" && pwd)" || exit 1; shift 2 ;;
    *) usage "unknown argument: $1" ;;
  esac
done
case "$CMD" in
  install|uninstall|status) ;;
  *) usage "unknown command: $CMD" ;;
esac
if [ "$CMD" = install ]; then
  [[ "$AT" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || usage "--at expects HH:MM (24h), got \"$AT\""
  if [ -n "$HINT" ] && ! [[ "$HINT" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    usage "--domain-hint expects a slug (lowercase, digits, hyphens), got \"$HINT\""
  fi
  if [ -n "$PERM" ] && ! [[ "$PERM" =~ ^[A-Za-z]+$ ]]; then
    usage "--permission-mode expects a Claude Code permission mode name, got \"$PERM\""
  fi
  HOUR=$((10#${AT%%:*})); MINUTE=$((10#${AT##*:}))
fi

OS="${SCHEDULE_INGEST_OS:-$(uname -s)}"
case "$OS" in
  Darwin|Linux) ;;
  MINGW*|MSYS*|CYGWIN*|Windows*)
    die "scheduling on Windows (Task Scheduler) is not supported yet. Run 'python scripts/ops/ingest-pending.py' from a scheduled task of your own, or call the ingest_pending MCP tool." ;;
  *) die "unsupported platform: $OS (macOS and Linux only)." ;;
esac

# --- shared values ---
PYTHON="${PYTHON_BIN:-$(command -v python3 || true)}"
[ -n "$PYTHON" ] || die "python3 not found on PATH (or set PYTHON_BIN)."
HASH="$(printf '%s' "$VAULT" | "$PYTHON" -c 'import hashlib, sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest()[:8])')"
LABEL="com.boilingbrain.ingest-pending.$HASH"
UNIT="boilingbrain-ingest-$HASH"
RUNNER="$VAULT/scripts/ops/ingest-pending.py"
LOG_DIR="$VAULT/ops/ingest"
LOG="$LOG_DIR/scheduled.log"
PLIST="${LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}/$LABEL.plist"
UNIT_DIR="${SYSTEMD_USER_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
SERVICE="$UNIT_DIR/$UNIT.service"
TIMER="$UNIT_DIR/$UNIT.timer"

resolve_claude() {
  CLAUDE="${CLAUDE_BIN-}"
  [ -n "$CLAUDE" ] || CLAUDE="$(command -v claude || true)"
  [ -n "$CLAUDE" ] && [ -x "$CLAUDE" ] || die "claude CLI not found on PATH (install Claude Code, or set CLAUDE_BIN)."
  JOB_PATH="$(dirname "$CLAUDE")"
  local node
  node="$(command -v node || true)"
  [ -n "$node" ] && JOB_PATH="$JOB_PATH:$(dirname "$node")"
  JOB_PATH="$JOB_PATH:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
  JOB_ARGS=("$PYTHON" "$RUNNER" --root "$VAULT" --trigger scheduled --claude "$CLAUDE")
  [ -z "$HINT" ] || JOB_ARGS+=(--domain-hint "$HINT")
}

remove_log_dir_if_empty() {
  rmdir "$LOG_DIR" 2>/dev/null || true
  rmdir "$VAULT/ops" 2>/dev/null || true
}

# --- macOS: LaunchAgent ---
launchd_install() {
  mkdir -p "$(dirname "$PLIST")" "$LOG_DIR"
  PLIST_OUT="$PLIST" LABEL="$LABEL" HOUR="$HOUR" MINUTE="$MINUTE" VAULT="$VAULT" \
    LOG="$LOG" JOB_PATH="$JOB_PATH" PERM="$PERM" "$PYTHON" - "${JOB_ARGS[@]}" <<'PYEOF'
import os, plistlib, sys
env = {"PATH": os.environ["JOB_PATH"]}
if os.environ["PERM"]:
    env["MCP_INGEST_PERMISSION_MODE"] = os.environ["PERM"]
plist = {
    "Label": os.environ["LABEL"],
    "ProgramArguments": sys.argv[1:],
    "WorkingDirectory": os.environ["VAULT"],
    "EnvironmentVariables": env,
    "StartCalendarInterval": {"Hour": int(os.environ["HOUR"]),
                              "Minute": int(os.environ["MINUTE"])},
    "StandardOutPath": os.environ["LOG"],
    "StandardErrorPath": os.environ["LOG"],
    "RunAtLoad": False,
}
with open(os.environ["PLIST_OUT"], "wb") as f:
    plistlib.dump(plist, f)
PYEOF
  local domain="gui/$(id -u)"
  "$LAUNCHCTL" bootout "$domain/$LABEL" >/dev/null 2>&1 || true
  if ! "$LAUNCHCTL" bootstrap "$domain" "$PLIST" >/dev/null 2>&1; then
    "$LAUNCHCTL" load "$PLIST" >/dev/null 2>&1 || die "launchctl could not load $PLIST"
  fi
  printf 'Installed LaunchAgent %s: daily at %02d:%02d (missed runs start at wake).\n' "$LABEL" "$HOUR" "$MINUTE"
  printf '  %s\n  log: %s\n' "$PLIST" "$LOG"
}

launchd_uninstall() {
  if [ -f "$PLIST" ]; then
    "$LAUNCHCTL" bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 \
      || "$LAUNCHCTL" unload "$PLIST" >/dev/null 2>&1 || true
    rm -f "$PLIST"
    echo "Removed LaunchAgent $LABEL ($PLIST)."
  else
    echo "No LaunchAgent installed for $VAULT."
  fi
}

launchd_status() {
  [ -f "$PLIST" ] || return 1
  "$PYTHON" - "$PLIST" <<'PYEOF'
import plistlib, sys
with open(sys.argv[1], "rb") as f:
    p = plistlib.load(f)
t = p["StartCalendarInterval"]
print(f"installed: LaunchAgent {p['Label']}, daily at {t['Hour']:02d}:{t['Minute']:02d}")
print(f"  {sys.argv[1]}")
PYEOF
}

# --- Linux: systemd user timer, crontab fallback ---
systemd_available() {
  command -v "$SYSTEMCTL" >/dev/null 2>&1 && "$SYSTEMCTL" --user show-environment >/dev/null 2>&1
}

# systemd unit values: % is a specifier (escape as %%); " and \ would break
# the quoting of ExecStart= and Environment= — refused.
unit_quote() {
  case "$1" in *'"'*|*'\'*|*$'\n'*) die "path not supported in a systemd unit: $1" ;; esac
  printf '"%s"' "${1//%/%%}"
}

systemd_install() {
  mkdir -p "$UNIT_DIR" "$LOG_DIR"
  local exec="" arg
  for arg in "${JOB_ARGS[@]}"; do exec="$exec $(unit_quote "$arg")"; done
  local env_perm=""
  [ -z "$PERM" ] || env_perm="Environment=\"MCP_INGEST_PERMISSION_MODE=$PERM\""
  cat > "$SERVICE" <<EOF
[Unit]
Description=BoilingBrain pending-queue ingestion (${VAULT//%/%%})

[Service]
Type=oneshot
WorkingDirectory=${VAULT//%/%%}
Environment=$(unit_quote "PATH=$JOB_PATH")
$env_perm
ExecStart=${exec# }
StandardOutput=append:${LOG//%/%%}
StandardError=append:${LOG//%/%%}
EOF
  cat > "$TIMER" <<EOF
[Unit]
Description=Daily BoilingBrain pending-queue ingestion (${VAULT//%/%%})

[Timer]
OnCalendar=*-*-* $(printf '%02d:%02d' "$HOUR" "$MINUTE"):00
Persistent=true
Unit=$UNIT.service

[Install]
WantedBy=timers.target
EOF
  "$SYSTEMCTL" --user daemon-reload
  "$SYSTEMCTL" --user enable --now "$UNIT.timer"
  printf 'Installed systemd user timer %s: daily at %02d:%02d (Persistent=true: a missed run starts at the next boot).\n' "$UNIT.timer" "$HOUR" "$MINUTE"
  printf '  %s\n  %s\n  log: %s\n' "$SERVICE" "$TIMER" "$LOG"
}

cron_quote() {
  case "$1" in *"'"*|*%*|*$'\n'*) die "path not supported in a crontab line: $1" ;; esac
  printf "'%s'" "$1"
}

cron_lines_without_ours() {
  "$CRONTAB" -l 2>/dev/null | grep -vF "# $UNIT" || true
}

cron_install() {
  local cmd="" arg
  for arg in "${JOB_ARGS[@]}"; do cmd="$cmd $(cron_quote "$arg")"; done
  local env="PATH=$(cron_quote "$JOB_PATH")"
  [ -z "$PERM" ] || env="$env MCP_INGEST_PERMISSION_MODE=$PERM"
  local line="$MINUTE $HOUR * * * cd $(cron_quote "$VAULT") && $env$cmd >> $(cron_quote "$LOG") 2>&1 # $UNIT"
  mkdir -p "$LOG_DIR"
  # Read the table fully before writing it back.
  local rest
  rest="$(cron_lines_without_ours)"
  { [ -z "$rest" ] || printf '%s\n' "$rest"; printf '%s\n' "$line"; } | "$CRONTAB" -
  printf 'Installed crontab line tagged "# %s": daily at %02d:%02d (systemd user instance unavailable; cron does not catch up missed runs).\n' "$UNIT" "$HOUR" "$MINUTE"
  printf '  log: %s\n' "$LOG"
}

cron_has_ours() {
  "$CRONTAB" -l 2>/dev/null | grep -qF "# $UNIT"
}

linux_uninstall() {
  local removed=0
  if [ -f "$SERVICE" ] || [ -f "$TIMER" ]; then
    if systemd_available; then
      "$SYSTEMCTL" --user disable --now "$UNIT.timer" >/dev/null 2>&1 || true
    fi
    rm -f "$SERVICE" "$TIMER"
    systemd_available && "$SYSTEMCTL" --user daemon-reload >/dev/null 2>&1 || true
    echo "Removed systemd user timer $UNIT ($UNIT_DIR)."
    removed=1
  fi
  if command -v "$CRONTAB" >/dev/null 2>&1 && cron_has_ours; then
    local rest
    rest="$(cron_lines_without_ours)"
    if [ -n "$rest" ]; then
      printf '%s\n' "$rest" | "$CRONTAB" -
    else
      "$CRONTAB" -r
    fi
    echo "Removed crontab line tagged \"# $UNIT\"."
    removed=1
  fi
  [ "$removed" = 1 ] || echo "No schedule installed for $VAULT."
}

linux_status() {
  if [ -f "$TIMER" ]; then
    printf 'installed: systemd user timer %s, daily at %s\n' "$UNIT.timer" \
      "$(sed -n 's/^OnCalendar=\*-\*-\* \([0-9][0-9]:[0-9][0-9]\):00$/\1/p' "$TIMER")"
    printf '  %s\n' "$TIMER"
    return 0
  fi
  if command -v "$CRONTAB" >/dev/null 2>&1 && cron_has_ours; then
    "$CRONTAB" -l | grep -F "# $UNIT" | awk -v unit="$UNIT" \
      '{ printf "installed: crontab line \"# %s\", daily at %02d:%02d\n", unit, $2, $1 }'
    return 0
  fi
  return 1
}

last_batch_summary() {
  local outcome="$VAULT/ops/ingest/last-batch.json"
  [ -f "$outcome" ] || { echo "last batch: none yet"; return; }
  "$PYTHON" - "$outcome" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
c = d["counts"]
print(f"last batch: ended {d['ended_at']} ({d['trigger']}) — {c['ok']} ok, "
      f"{c['degraded']} degraded, {c['failed']} failed, {c['skipped-no-hint']} "
      f"skipped-no-hint; {d['remaining']} left in the queue")
PYEOF
}

# --- dispatch ---
case "$OS:$CMD" in
  Darwin:install)
    resolve_claude; launchd_install ;;
  Darwin:uninstall)
    launchd_uninstall; remove_log_dir_if_empty ;;
  Linux:install)
    resolve_claude
    # Re-install on a machine whose backend changed: never leave two schedules.
    if systemd_available; then
      if command -v "$CRONTAB" >/dev/null 2>&1 && cron_has_ours; then
        rest="$(cron_lines_without_ours)"
        if [ -n "$rest" ]; then printf '%s\n' "$rest" | "$CRONTAB" -; else "$CRONTAB" -r; fi
      fi
      systemd_install
    else
      command -v "$CRONTAB" >/dev/null 2>&1 \
        || die "neither a systemd user instance nor crontab is available."
      cron_install
    fi ;;
  Linux:uninstall)
    linux_uninstall; remove_log_dir_if_empty ;;
  *:status)
    if { [ "$OS" = Darwin ] && launchd_status; } || { [ "$OS" = Linux ] && linux_status; }; then
      printf '  log: %s\n' "$LOG"
      last_batch_summary
    else
      echo "not installed for $VAULT"
      exit 1
    fi ;;
esac
