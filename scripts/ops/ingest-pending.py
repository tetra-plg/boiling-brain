#!/usr/bin/env python3
"""ingest-pending.py — batch ingestion of the pending queue (#154).

Reads cache/.pending-ingest and ingests its entries one by one, each through
the exact guarded headless command the MCP ingest tools spawn
(`claude -p "/ingest <path> --headless[ --domain-hint=<slug>]" --settings
<guard>`, plus `--permission-mode $MCP_INGEST_PERMISSION_MODE` when set —
built by ingest_jobs.build_ingest_cmd). Sequential by design: a headless run
owns wiki/log.md, the radar and the index. Used by the ingest_pending MCP
tool, by `/ingest --pending --headless` and by the schedule installed with
scripts/ops/schedule-ingest.sh.

Per entry (`<path>` or `<path>\t<hint>`; the entry hint wins, --domain-hint
is the fallback):
- ok              the run succeeded and journaled its source; entry removed.
- degraded        the run listed pages but wiki/log.md gained no entry for
                  its source (ingest_jobs.journal_gap); entry removed.
- failed          invalid entry, non-zero exit, timeout or no `claude` CLI;
                  entry kept so the next run retries it — except a path no
                  longer on disk (stale), which is dropped.
- skipped-no-hint the run deferred the file to needs-human-triage (empty
                  `## Pages`); entry kept, as /ingest itself does.
One failure never stops the batch. Entries are removed one at a time through
scripts/wiki-maint/purge-pending-ingest.sh (the manifest's only remover), so
an interrupted batch leaves every unprocessed entry in place.

cache/ingest.lock is held for the whole batch (ingest_jobs.acquire_lock):
an MCP ingest job never spawns meanwhile, and the batch waits up to
--lock-wait seconds for a running one before giving up (exit 3).

Outcome: ops/ingest/last-batch.json (atomic write, schema in
scripts/ops/fixtures/last-batch.example.json) and, when the vault keeps a
run ledger (ops/metrics/ledger.config.json), one run event appended to
ops/metrics/runs.jsonl. Stdout: a consolidated report, one block per file.

Usage: ingest-pending.py [--root <vault>] [--domain-hint <slug>]
                         [--max-files N] [--claude <exe>] [--timeout S]
                         [--lock-wait S] [--trigger manual|scheduled]
Exit 0 once the batch ran (whatever the per-file statuses), 2 on bad
arguments, 3 when another ingestion holds the lock, 143 when interrupted.
"""
import argparse
import datetime
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mcp"))
import ingest_jobs  # noqa: E402
import wiki_core  # noqa: E402

PURGE = HERE.parent / "wiki-maint" / "purge-pending-ingest.sh"
OUTCOME_REL = "ops/ingest/last-batch.json"
STATUSES = ("ok", "degraded", "failed", "skipped-no-hint")
_DETAIL_CHARS = 2000
_LOCK_POLL_S = 5
_PAGE_RE = re.compile(r"^- (\S+)(?: \(([^,()]+), (new|updated)\))?")


class Interrupted(Exception):
    pass


def _on_signal(signum, frame):
    raise Interrupted()


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def read_queue(root: Path):
    """[(path, hint)] in manifest order, first occurrence of a path wins (a
    later line may still supply the hint it lacked)."""
    pending = root / "cache" / ".pending-ingest"
    try:
        lines = pending.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    entries, index = [], {}
    for line in lines:
        if not line.strip():
            continue
        path, _, hint = line.partition("\t")
        path, hint = path.strip(), hint.strip()
        if path in index:
            if hint and not entries[index[path]][1]:
                entries[index[path]] = (path, hint)
            continue
        index[path] = len(entries)
        entries.append((path, hint))
    return entries


def purge(root: Path, path: str):
    subprocess.run(["bash", str(PURGE), path], cwd=str(root),
                   capture_output=True, text=True)


def parse_pages(report: str):
    """Entries of the report's last `## Pages` block."""
    lines = report.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == "## Pages"]
    if not starts:
        return []
    pages = []
    for line in lines[starts[-1] + 1:]:
        if line.startswith("#"):
            break
        m = _PAGE_RE.match(line.strip())
        if m:
            pages.append({"path": m.group(1), "type": m.group(2), "change": m.group(3)})
    return pages


def triage_excerpt(report: str) -> str:
    lines = report.splitlines()
    for i, line in enumerate(lines):
        if "needs-human-triage" in line:
            block = [line.lstrip("# ").strip()]
            for nxt in lines[i + 1:]:
                if nxt.startswith("## Pages"):
                    break
                if nxt.strip():
                    block.append(nxt.strip())
            return "deferred to " + " ".join(block)[:_DETAIL_CHARS]
    return "deferred to needs-human-triage"


def tail(text: str) -> str:
    text = (text or "").strip()
    return text[-_DETAIL_CHARS:] if text else "no detail on stderr."


class Batch:
    def __init__(self, root: Path, args):
        self.root = root
        self.args = args
        self.child = None
        self.files = []

    def run_one(self, path: str, hint: str, claude_exe):
        entry = {"path": path, "status": "failed", "hint": hint or None,
                 "pages": [], "detail": None}
        self.files.append(entry)
        prompt, err = ingest_jobs.validate_request(path, hint)
        if err:
            entry["detail"] = err
            if err.startswith("Error: file not found"):
                entry["detail"] += " Stale entry dropped from the queue."
                purge(self.root, path)
            return
        cmd = ingest_jobs.build_ingest_cmd(
            prompt, os.environ.get("MCP_INGEST_PERMISSION_MODE", ""), claude_exe)
        if cmd is None:
            entry["detail"] = "`claude` CLI not found (pass --claude or fix PATH)."
            return
        before = ingest_jobs.journal_mentions(path)
        try:
            self.child = subprocess.Popen(cmd, cwd=str(self.root), stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True,
                                          encoding="utf-8", errors="replace")
        except OSError as e:
            entry["detail"] = f"cannot spawn {cmd[0]!r} ({e})"
            return
        try:
            out, errout = self.child.communicate(timeout=self.args.timeout)
        except subprocess.TimeoutExpired:
            self.kill_child()
            entry["detail"] = f"aborted after {self.args.timeout:g}s (timeout)."
            return
        except Interrupted:
            self.kill_child()
            entry["detail"] = "batch interrupted while this file was being ingested."
            raise
        finally:
            rc = self.child.returncode if self.child else None
            self.child = None
        if rc != 0:
            entry["detail"] = f"exit code {rc}: {tail(errout or out)}"
            return
        entry["pages"] = parse_pages(out)
        if not entry["pages"] and "needs-human-triage" in out:
            entry["status"] = "skipped-no-hint"
            entry["detail"] = triage_excerpt(out)
            return
        gap = ingest_jobs.journal_gap(path, before, out)
        entry["status"] = "degraded" if gap else "ok"
        entry["detail"] = gap
        purge(self.root, path)

    def kill_child(self):
        child = self.child
        if child is None or child.poll() is not None:
            return
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def outcome_doc(batch, started_at, interrupted, remaining):
    counts = {s: sum(1 for f in batch.files if f["status"] == s) for s in STATUSES}
    counts["total"] = len(batch.files)
    return {
        "schema_version": 1,
        "started_at": started_at,
        "ended_at": now_iso(),
        "trigger": batch.args.trigger,
        "domain_hint": batch.args.domain_hint or None,
        "interrupted": interrupted,
        "files": batch.files,
        "counts": counts,
        "remaining": remaining,
    }


def write_outcome(root: Path, doc: dict):
    final = root / OUTCOME_REL
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.parent / f"{final.name}.tmp"
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, final)


def _utc(iso: str) -> str:
    return (datetime.datetime.fromisoformat(iso).astimezone(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"))


def ledger_event(root: Path, doc: dict, duration_ms: int):
    """A run event in the vault ledger's format (run-event 1.1), or None when
    the vault keeps no ledger. The runner itself calls no model, so the event
    is `deterministic`: the per-file claude runs are captured, with their
    usage, by the ledger's own hooks when the vault has them."""
    config = root / "ops" / "metrics" / "ledger.config.json"
    try:
        client_id = json.loads(config.read_text(encoding="utf-8"))["client_id"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    counts = doc["counts"]
    failed = counts["failed"]
    if doc["interrupted"] or (failed and failed == counts["total"]):
        status = "failure"
    elif failed:
        status = "partial"
    else:
        status = "success"
    error = None
    if doc["interrupted"]:
        error = {"type": "batch_interrupted", "message": "the batch was interrupted"}
    elif failed:
        error = {"type": "batch_failures",
                 "message": f"{failed} of {counts['total']} file(s) failed"}
    try:
        version = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True).stdout.strip()
    except OSError:
        version = ""
    host_os = {"darwin": "macos", "linux": "linux", "win32": "windows"}.get(sys.platform)
    return {
        "schema_version": "1.1",
        "event_type": "run",
        "run_id": str(uuid.uuid4()),
        "client_id": client_id,
        "pipeline_id": "ingest-pending",
        "pipeline_version": version or "unknown",
        "trigger": doc["trigger"],
        "started_at": _utc(doc["started_at"]),
        "ended_at": _utc(doc["ended_at"]),
        "duration_ms": duration_ms,
        "status": status,
        "error": error,
        "substrate": "deterministic",
        "provider": "none",
        "host_os": host_os,
        "usage": {"requests": 0, "input_tokens": 0, "output_tokens": 0,
                  "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
                  "models": []},
        "cost": {"type": "none", "amount_usd": 0},
        "units": [{"kind": "source", "count": counts["total"]}],
        "outcomes": [{"kind": s.replace("-", "_"), "count": counts[s]} for s in STATUSES],
    }


def emit_ledger_event(root: Path, event):
    if event is None:
        return
    with open(root / "ops" / "metrics" / "runs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def render_report(doc: dict, queued: int) -> str:
    out = ["# Pending-queue batch ingest", "",
           f"Started: {doc['started_at']} · Ended: {doc['ended_at']}"]
    if not queued:
        out += ["", "Nothing pending: cache/.pending-ingest is empty.",
                f"Outcome file: {OUTCOME_REL}"]
        return "\n".join(out) + "\n"
    out += [f"Queue: {queued} entr{'y' if queued == 1 else 'ies'} read, "
            f"{len(doc['files'])} processed, {doc['remaining']} left in "
            f"cache/.pending-ingest",
            f"Outcome file: {OUTCOME_REL}"]
    if doc["interrupted"]:
        out.append("INTERRUPTED: the batch stopped early; unprocessed entries "
                   "stay in the queue.")
    for f in doc["files"]:
        out += ["", f"## {f['path']} — {f['status']}", f"- hint: {f['hint'] or 'none'}"]
        if f["pages"]:
            out.append("- pages:")
            for p in f["pages"]:
                kind = f" ({p['type']}, {p['change']})" if p["type"] else ""
                out.append(f"  - {p['path']}{kind}")
        if f["detail"]:
            out.append(f"- detail: {f['detail']}")
        if f["status"] == "failed" and "Stale entry" not in (f["detail"] or ""):
            out.append("- kept in cache/.pending-ingest: the next run retries it.")
        elif f["status"] == "skipped-no-hint":
            out.append("- kept in cache/.pending-ingest. Fix: give it a domain_hint "
                       "(ingest_start(path, domain_hint=<slug>), or "
                       "ingest_pending(domain_hint=<slug>)) — valid slugs via "
                       "list_domains().")
    c = doc["counts"]
    out += ["", f"Summary: {c['ok']} ok · {c['degraded']} degraded · "
                f"{c['failed']} failed · {c['skipped-no-hint']} skipped-no-hint"]
    return "\n".join(out) + "\n"


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="ingest-pending.py",
        description="Ingest the entries of cache/.pending-ingest, one headless run each.")
    parser.add_argument("--root", default=str(HERE.parents[1]),
                        help="vault root (default: this script's vault)")
    parser.add_argument("--domain-hint", default="",
                        help="fallback hint for entries that carry none")
    parser.add_argument("--max-files", type=int, default=0,
                        help="process at most N entries (0 = all)")
    parser.add_argument("--claude", default=os.environ.get("INGEST_CLAUDE_BIN") or None,
                        help="claude executable (default: $INGEST_CLAUDE_BIN, then PATH)")
    parser.add_argument("--timeout", type=float, default=ingest_jobs.TIMEOUT_S,
                        help="per-file timeout in seconds (default: %(default)s)")
    parser.add_argument("--lock-wait", type=float, default=1800,
                        help="seconds to wait for a running ingestion (default: %(default)s)")
    parser.add_argument("--trigger", choices=("manual", "scheduled"), default="manual")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    err = ingest_jobs.validate_hint(args.domain_hint)
    if err or args.max_files < 0:
        print(err or "Error: --max-files must be >= 0.", file=sys.stderr)
        return 2
    root = Path(args.root).resolve()
    wiki_core.configure(root)

    deadline = time.monotonic() + args.lock_wait
    while not ingest_jobs.acquire_lock(owner="ingest-pending batch"):
        if time.monotonic() >= deadline:
            holder = ingest_jobs.lock_holder() or {}
            print(f"Another ingestion holds cache/ingest.lock (pid {holder.get('pid')}, "
                  f"{holder.get('owner', 'unknown')}): nothing done, the queue is "
                  f"left for the next run.", file=sys.stderr)
            return 3
        time.sleep(min(_LOCK_POLL_S, max(0.0, deadline - time.monotonic())))

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    started_at, t0 = now_iso(), time.monotonic()
    batch = Batch(root, args)
    entries = read_queue(root)
    todo = entries[:args.max_files] if args.max_files else entries
    interrupted = False
    try:
        for path, hint in todo:
            # Keep the lock fresh: its age bounds how long it can be trusted.
            try:
                os.utime(ingest_jobs.lock_path())
            except OSError:
                pass
            batch.run_one(path, hint or args.domain_hint, args.claude)
    except Interrupted:
        interrupted = True
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        doc = outcome_doc(batch, started_at, interrupted, len(read_queue(root)))
        write_outcome(root, doc)
        emit_ledger_event(root, ledger_event(root, doc, int((time.monotonic() - t0) * 1000)))
        ingest_jobs.release_lock()
    sys.stdout.write(render_report(doc, len(entries)))
    return 143 if interrupted else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
