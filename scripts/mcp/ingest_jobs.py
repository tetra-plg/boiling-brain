#!/usr/bin/env python3
"""ingest_jobs.py — async job manager for headless ingest runs (#124).

Dependency-free (stdlib + wiki_core): mcp-wiki.py wraps start/status/cancel as
the ingest_start / ingest_status / ingest_cancel MCP tools, keeping the sync
ingest() unchanged. Design constraints:

- One job at a time: a headless run owns wiki/log.md, the radar and the index;
  two concurrent runs would interleave their journaling writes.
- State survives across tool calls in cache/ingest-jobs/<job_id>.json; the
  in-process _PROCS registry is the only liveness signal. A "running" job
  whose job_id is missing from _PROCS (MCP server restart) is a restart
  orphan: its exit code is unrecoverable and its persisted pid may already
  have been recycled by an unrelated process, so it is never signaled — it
  is finalized as an error with an explicit "check wiki/log.md" note instead.
- Child stdout/stderr go to <job_id>.out / <job_id>.err files (no PIPE: nobody
  drains it, a chatty child would deadlock on a full pipe buffer).
- Exit code 0 is not the whole success contract (#145): a run whose `## Pages`
  block lists pages must also have journaled its source in wiki/log.md. The
  count of mentions of the raw path is taken at start and re-checked at the
  end; no new mention stamps the report `DEGRADED — journal entry missing`
  (journal_gap, shared with the sync ingest() in mcp-wiki.py).
"""
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wiki_core  # noqa: E402

TIMEOUT_S = 600  # same bound as the sync ingest()

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_JOB_ID_RE = re.compile(r"^[0-9a-f]{12}$")
_STDERR_EXCERPT_CHARS = 2000

_PROCS = {}  # job_id -> subprocess.Popen (this server process's own spawns)


def jobs_dir() -> Path:
    return wiki_core.CACHE_DIR / "ingest-jobs"


def validate_request(path: str, domain_hint: str = ""):
    """Shared input validation for ingest() and ingest_start().
    Returns (prompt, None) on success, (None, error_message) on failure.
    Error strings are byte-identical to the historical sync ingest() ones."""
    if domain_hint and not _SLUG_RE.match(domain_hint):
        return None, (f"Error: invalid domain_hint: \"{domain_hint}\" — expected a slug "
                      f"(lowercase, digits, hyphens). See list_domains() for valid values.")

    if any(c.isspace() for c in path) or any(part.startswith("-") for part in path.split("/")):
        return None, (f"Error: invalid path: \"{path}\" — must not contain a space or a "
                      f"segment starting with \"-\" (flag-injection risk in the built command).")

    try:
        target = (wiki_core.WIKI_PATH / path).resolve()
        if not str(target).startswith(str(wiki_core.RAW_DIR.resolve())):
            return None, "Error: invalid path (path traversal detected)."
    except Exception as e:
        return None, f"Path validation error: {e}"

    if not target.exists():
        return None, f"Error: file not found: {path}."

    prompt = f"/ingest {path} --headless"
    if domain_hint:
        prompt += f" --domain-hint={domain_hint}"
    return prompt, None


def journal_mentions(path: str) -> int:
    """Occurrences of the raw path in wiki/log.md (0 if the log is absent)."""
    log = wiki_core.WIKI_PATH / "wiki" / "log.md"
    try:
        return log.read_text(encoding="utf-8", errors="replace").count(path)
    except OSError:
        return 0


def _pages_listed(report: str) -> int:
    """Number of `- ` lines in the report's last `## Pages` block."""
    lines = report.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == "## Pages"]
    if not starts:
        return 0
    count = 0
    for line in lines[starts[-1] + 1:]:
        if line.startswith("#"):
            break
        if line.lstrip().startswith("- "):
            count += 1
    return count


def journal_gap(path: str, mentions_before: int, report: str):
    """Degradation reason when the run reported pages but wiki/log.md gained no
    mention of its source; None otherwise. An empty `## Pages` block is a
    deferral to needs-human-triage: no journal entry is expected."""
    if _pages_listed(report) == 0 or journal_mentions(path) > mentions_before:
        return None
    return (f"DEGRADED — journal entry missing: wiki/log.md gained no entry for "
            f"{path} during this run. Run the journaling step "
            f"(scripts/wiki-maint/journal-ingest.py) or check the run.")


def _job_file(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.json"


def _load_job_file(f: Path):
    """Read+parse a state file, tolerating a partial write or corruption from
    a concurrent MCP server process. Returns None on any failure."""
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_job(job_id: str):
    if not _JOB_ID_RE.match(job_id):
        return None
    f = _job_file(job_id)
    if not f.exists():
        return None
    return _load_job_file(f)


def _write_job(job: dict):
    final = _job_file(job["job_id"])
    tmp = final.parent / f"{final.name}.tmp"
    tmp.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, final)


def _running_job():
    """The currently running job dict, or None (stale entries resolved first)."""
    if not jobs_dir().is_dir():
        return None
    for f in sorted(jobs_dir().glob("*.json")):
        job = _load_job_file(f)
        if job is None or job.get("state") != "running":
            continue
        proc = _PROCS.get(job["job_id"])
        if proc is None:
            # Restart orphan: no in-process handle to trust, and the
            # persisted pid may already be a recycled, unrelated process —
            # never signal it. Finalize as error and free the slot.
            _finalize(job, None)
            continue
        if proc.poll() is None:
            return job
        _finalize(job, proc)
    return None


def _stderr_excerpt(job_id: str) -> str:
    err = jobs_dir() / f"{job_id}.err"
    if not err.exists():
        return "no detail on stderr."
    text = err.read_text(encoding="utf-8", errors="replace").strip()
    return text[-_STDERR_EXCERPT_CHARS:] or "no detail on stderr."


def _finalize(job: dict, proc):
    """Transition a no-longer-alive 'running' job to done/error and persist."""
    rc = proc.poll() if proc is not None else None
    if proc is not None and rc == 0:
        job["state"] = "done"
        out = jobs_dir() / f"{job['job_id']}.out"
        report = out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""
        gap = journal_gap(job["path"], job.get("log_mentions", 0), report)
        if gap:
            job["degraded"] = gap
    elif proc is not None:
        job["state"] = "error"
        job["detail"] = f"exit code {rc}: {_stderr_excerpt(job['job_id'])}"
    else:
        # Spawned by a previous server process: the exit code died with it.
        job["state"] = "error"
        job["detail"] = ("the MCP server restarted while the job was running; "
                         "exit code unknown — check wiki/log.md for the run's "
                         "own account.")
    _write_job(job)


def _kill_child(job: dict, proc):
    """SIGTERM, 5s grace, SIGKILL. Tolerates an already-gone child.
    proc is always a real Popen handle of this server process's own spawn —
    restart orphans (no _PROCS entry) are never signaled, see _running_job."""
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    except (ProcessLookupError, PermissionError):
        pass


def _final_report(job: dict) -> str:
    state = job["state"]
    if state == "done":
        out = jobs_dir() / f"{job['job_id']}.out"
        report = out.read_text(encoding="utf-8", errors="replace")
        if job.get("degraded"):
            return f"{job['degraded']}\n\n{report}"
        return report
    if state == "error":
        return f"Error: ingestion of {job['path']} failed ({job.get('detail', 'no detail')})"
    if state == "timeout":
        return f"Error: ingestion of {job['path']} aborted after {TIMEOUT_S}s (timeout)."
    if state == "cancelled":
        return f"Job {job['job_id']} cancelled ({job['path']})."
    return f"Error: job {job['job_id']} in unexpected state: {state}."


def start(cmd, path: str) -> str:
    """Spawn cmd non-blocking; one job at a time."""
    jobs_dir().mkdir(parents=True, exist_ok=True)
    current = _running_job()
    if current is not None:
        return (f"Error: an ingest job is already running ({current['job_id']}, "
                f"{current['path']}). Poll or cancel it first.")
    job_id = uuid.uuid4().hex[:12]
    log_mentions = journal_mentions(path)
    out = open(jobs_dir() / f"{job_id}.out", "wb")
    err = open(jobs_dir() / f"{job_id}.err", "wb")
    try:
        proc = subprocess.Popen(cmd, stdout=out, stderr=err,
                                cwd=str(wiki_core.WIKI_PATH))
    except FileNotFoundError:
        return f"Error: cannot spawn {cmd[0]!r} (not found)."
    finally:
        out.close()
        err.close()
    _PROCS[job_id] = proc
    _write_job({"job_id": job_id, "path": path, "pid": proc.pid,
                "started_at": time.time(), "state": "running",
                "log_mentions": log_mentions})
    return f"Job {job_id} started for {path}. Poll ingest_status(\"{job_id}\")."


def status(job_id: str) -> str:
    job = _read_job(job_id)
    if job is None:
        return f"Error: unknown job_id: {job_id}."
    if job["state"] == "running":
        proc = _PROCS.get(job_id)
        if proc is None:
            # Restart orphan: never signaled, see _running_job / module docstring.
            _finalize(job, None)
        elif proc.poll() is None:
            elapsed = time.time() - job["started_at"]
            if elapsed > TIMEOUT_S:
                _kill_child(job, proc)
                job["state"] = "timeout"
                _write_job(job)
            else:
                return (f"Job {job_id} running "
                        f"({int(elapsed)}s elapsed, {job['path']}).")
        else:
            _finalize(job, proc)
    return _final_report(job)


def cancel(job_id: str) -> str:
    job = _read_job(job_id)
    if job is None:
        return f"Error: unknown job_id: {job_id}."
    if job["state"] != "running":
        return f"Job {job_id} already finished ({job['state']}); nothing to cancel."
    proc = _PROCS.get(job_id)
    if proc is None:
        # Restart orphan: never signaled, see _running_job / module docstring.
        _finalize(job, None)
        return f"Job {job_id} already finished ({job['state']}); nothing to cancel."
    if proc.poll() is not None:
        # Exited but never polled via status(): finalize instead of
        # discarding a completed report under a "cancelled" stamp.
        _finalize(job, proc)
        return f"Job {job_id} already finished ({job['state']}); nothing to cancel."
    _kill_child(job, proc)
    job["state"] = "cancelled"
    _write_job(job)
    return f"Job {job_id} cancelled ({job['path']})."
