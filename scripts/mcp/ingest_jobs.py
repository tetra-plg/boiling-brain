#!/usr/bin/env python3
"""ingest_jobs.py — async job manager for headless ingest runs (#124).

Dependency-free (stdlib + wiki_core): mcp-wiki.py wraps start/status/cancel as
the ingest_start / ingest_status / ingest_cancel MCP tools, keeping the sync
ingest() unchanged. Design constraints:

- One job at a time: a headless run owns wiki/log.md, the radar and the index;
  two concurrent runs would interleave their journaling writes.
- State survives across tool calls in cache/ingest-jobs/<job_id>.json; the
  in-process _PROCS registry is the primary handle (exit codes, clean reaping)
  and the persisted pid is the fallback after an MCP server restart, where the
  exit code is unrecoverable — such a job is reported as an error with an
  explicit "check wiki/log.md" note rather than guessed at.
- Child stdout/stderr go to <job_id>.out / <job_id>.err files (no PIPE: nobody
  drains it, a chatty child would deadlock on a full pipe buffer).
"""
import json
import os
import re
import signal
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


def _job_file(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.json"


def _read_job(job_id: str):
    if not _JOB_ID_RE.match(job_id):
        return None
    f = _job_file(job_id)
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def _write_job(job: dict):
    _job_file(job["job_id"]).write_text(
        json.dumps(job, indent=2) + "\n", encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _running_job():
    """The currently running job dict, or None (stale entries resolved first)."""
    if not jobs_dir().is_dir():
        return None
    for f in sorted(jobs_dir().glob("*.json")):
        job = json.loads(f.read_text(encoding="utf-8"))
        if job.get("state") != "running":
            continue
        proc = _PROCS.get(job["job_id"])
        alive = proc.poll() is None if proc is not None else _pid_alive(job["pid"])
        if alive:
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
    """SIGTERM, 5s grace, SIGKILL. Tolerates an already-gone child."""
    try:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        else:
            os.kill(job["pid"], signal.SIGTERM)
            time.sleep(0.2)
            if _pid_alive(job["pid"]):
                os.kill(job["pid"], signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _final_report(job: dict) -> str:
    state = job["state"]
    if state == "done":
        out = jobs_dir() / f"{job['job_id']}.out"
        return out.read_text(encoding="utf-8", errors="replace")
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
                "started_at": time.time(), "state": "running"})
    return f"Job {job_id} started for {path}. Poll ingest_status(\"{job_id}\")."


def status(job_id: str) -> str:
    job = _read_job(job_id)
    if job is None:
        return f"Error: unknown job_id: {job_id}."
    if job["state"] == "running":
        proc = _PROCS.get(job_id)
        alive = proc.poll() is None if proc is not None else _pid_alive(job["pid"])
        if alive:
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
