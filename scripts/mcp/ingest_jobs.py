#!/usr/bin/env python3
"""ingest_jobs.py — async job manager for headless ingest runs (#124).

Dependency-free (stdlib + wiki_core): mcp-wiki.py wraps start/status/cancel as
the ingest_start / ingest_status / ingest_cancel MCP tools, keeping the sync
ingest() unchanged. Design constraints:

- One job at a time: a headless run owns wiki/log.md, the radar and the index;
  two concurrent runs would interleave their journaling writes. A job started
  while another runs is persisted as `queued` and promoted FIFO when the slot
  frees (#154): by any later tool call, or by a daemon thread that waits on
  the running child (it also enforces the watchdog with nobody polling).
- Cross-process exclusion: cache/ingest.lock (O_CREAT|O_EXCL, JSON holder
  {pid, owner, started_at}) is held for the whole life of a running job —
  stamped with the child's pid — and by the scheduled batch runner
  (scripts/ops/ingest-pending.py, outside any MCP server). A job never spawns
  while another live process holds it; a lock whose pid is gone is stale and
  taken over.
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
import shutil
import subprocess
import sys
import threading
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

TICK_S = 5  # promotion-thread poll while the slot is held by another process
_LOCK_GRACE_S = 10  # an unreadable lock younger than this may be mid-write
_LOCK_MAX_AGE_S = 24 * 3600  # a lock older than this is stale whatever its pid
_MUTEX = threading.RLock()  # serializes tool calls and the promotion thread
_TICKER = None
_TICKER_STOP = threading.Event()


def jobs_dir() -> Path:
    return wiki_core.CACHE_DIR / "ingest-jobs"


def validate_hint(domain_hint: str = ""):
    """Error message for a malformed domain_hint, None when empty or valid.
    Shared by the ingest tools and the deposit tools (#154)."""
    if domain_hint and not _SLUG_RE.match(domain_hint):
        return (f"Error: invalid domain_hint: \"{domain_hint}\" — expected a slug "
                f"(lowercase, digits, hyphens). See list_domains() for valid values.")
    return None


def validate_request(path: str, domain_hint: str = ""):
    """Shared input validation for ingest() and ingest_start().
    Returns (prompt, None) on success, (None, error_message) on failure.
    Error strings are byte-identical to the historical sync ingest() ones."""
    err = validate_hint(domain_hint)
    if err:
        return None, err

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


def ingest_settings_json():
    """Build a --settings JSON that scopes a PreToolUse allowlist hook to just
    the claude -p session spawned for one headless ingest. Verified
    empirically to merge with (not replace) the vault's own
    .claude/settings.json, and to apply to subagent tool calls, not just the
    main context. The matcher covers every tool (empty string, this codebase's
    established "match all" convention — see setup-mcp.sh's Stop hook
    registration) so the guard script's own per-tool dispatch — including its
    default-deny for anything it doesn't explicitly recognize — actually runs
    for every tool call, not just Write/Edit/Bash."""
    guard = str(wiki_core.WIKI_PATH / "scripts" / "mcp" / "ingest-headless-guard.sh")
    hook = {"type": "command", "command": guard, "timeout": 3000}
    return json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "", "hooks": [hook]},
    ]}})


def build_ingest_cmd(prompt: str, permission_mode: str = "", claude_exe=None):
    """The guarded headless command for one validated prompt, or None when the
    `claude` CLI cannot be resolved. Single source for the ingest /
    ingest_start tools and the batch runner (#154).

    The CLI is resolved with shutil.which: on Windows it ships as a claude.CMD
    shim and CreateProcess (shell=False) does NOT consult PATHEXT, so a bare
    "claude" raises FileNotFoundError even when it is on PATH. shutil.which
    honours PATHEXT and returns the full path (also correct on POSIX);
    shell=False is preserved, so no command-injection surface is
    reintroduced. (#84)"""
    if claude_exe is None:
        claude_exe = shutil.which("claude")
    if claude_exe is None:
        return None
    cmd = [claude_exe, "-p", prompt, "--settings", ingest_settings_json()]
    if permission_mode:
        cmd += ["--permission-mode", permission_mode]
    return cmd


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


def _all_jobs():
    if not jobs_dir().is_dir():
        return []
    jobs = (_load_job_file(f) for f in sorted(jobs_dir().glob("*.json")))
    return [j for j in jobs if j is not None]


def _queued_jobs():
    """Queued jobs in FIFO order."""
    queued = [j for j in _all_jobs() if j.get("state") == "queued"]
    return sorted(queued, key=lambda j: (j.get("queued_at", 0), j["job_id"]))


# ---- cross-process lock -------------------------------------------------
def lock_path() -> Path:
    return wiki_core.CACHE_DIR / "ingest.lock"


def pid_alive(pid) -> bool:
    """Best-effort liveness of a pid. Never signals anything: on Windows
    os.kill(pid, 0) would terminate the process, so the Win32 API is queried
    instead; when it cannot be, the pid is assumed alive (a held lock then
    expires through _LOCK_MAX_AGE_S instead of being stolen)."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
                return code.value == 259  # STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _write_lock(fd_or_path, holder: dict):
    data = (json.dumps(holder) + "\n").encode("utf-8")
    if isinstance(fd_or_path, int):
        try:
            os.write(fd_or_path, data)
        finally:
            os.close(fd_or_path)
        return
    tmp = fd_or_path.parent / f"{fd_or_path.name}.{os.getpid()}.tmp"
    tmp.write_bytes(data)
    os.replace(tmp, fd_or_path)


def lock_holder():
    """The live holder of cache/ingest.lock as a dict, or None. A lock whose
    pid is gone is stale and removed. An unreadable lock is treated as held
    (another process may be mid-write) until it is _LOCK_GRACE_S old; any
    lock older than _LOCK_MAX_AGE_S is stale whatever its pid says."""
    path = lock_path()
    try:
        raw = path.read_text(encoding="utf-8")
        age = time.time() - path.stat().st_mtime
    except OSError:
        return None
    try:
        holder = json.loads(raw)
        if not isinstance(holder, dict):
            raise ValueError
    except ValueError:
        holder = None
    if holder is None:
        stale = age > _LOCK_GRACE_S
    else:
        stale = age > _LOCK_MAX_AGE_S or not pid_alive(holder.get("pid"))
    if not stale:
        return holder if holder is not None else {"pid": None, "owner": "unknown"}
    # Re-read before unlinking: never remove a lock another process has just
    # (re)written in the meantime.
    try:
        if path.read_text(encoding="utf-8") == raw:
            path.unlink()
    except OSError:
        pass
    return None


def acquire_lock(pid=None, owner: str = "") -> bool:
    """Take cache/ingest.lock for pid (default: this process). True when the
    lock is now held by pid — including when it already was (re-entrant:
    a batch runner spawned by an MCP job inherits the lock under its own
    pid). False when another live process holds it."""
    pid = os.getpid() if pid is None else pid
    wiki_core.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    holder = {"pid": pid, "owner": owner, "started_at": time.time()}
    for _ in range(2):
        current = lock_holder()
        if current is not None:
            return current.get("pid") == pid
        try:
            fd = os.open(lock_path(), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            continue
        _write_lock(fd, holder)
        return True
    return False


def transfer_lock(to_pid: int, owner: str = "") -> bool:
    """Re-stamp a lock this process holds with another pid (its spawned
    child), so liveness follows the process that actually ingests."""
    current = lock_holder()
    if current is None or current.get("pid") != os.getpid():
        return False
    _write_lock(lock_path(), {"pid": to_pid, "owner": owner,
                              "started_at": current.get("started_at", time.time())})
    return True


def release_lock(pid=None):
    """Remove cache/ingest.lock if pid (default: this process) holds it."""
    pid = os.getpid() if pid is None else pid
    current = lock_holder()
    if current is not None and current.get("pid") == pid:
        try:
            lock_path().unlink()
        except OSError:
            pass


# ---- job lifecycle --------------------------------------------------------
def _is_foreign(job: dict) -> bool:
    """A running job spawned by another, still alive, MCP server process
    (e.g. Claude Desktop and Claude Code each run one on the same vault): not
    an orphan, just not ours to poll or signal."""
    owner = job.get("server_pid")
    return owner not in (None, os.getpid()) and pid_alive(owner)


def _expired(job: dict) -> bool:
    return (job.get("kind") != "batch"
            and time.time() - job["started_at"] > TIMEOUT_S)


def _running_job():
    """The currently running job dict, or None (stale entries resolved first:
    exited children finalized, timed-out ones killed, restart orphans
    closed)."""
    for job in _all_jobs():
        if job.get("state") != "running":
            continue
        proc = _PROCS.get(job["job_id"])
        if proc is None:
            if _is_foreign(job):
                return job
            # Restart orphan: no in-process handle to trust, and the
            # persisted pid may already be a recycled, unrelated process —
            # never signal it. Finalize as error and free the slot.
            _finalize(job, None)
            continue
        if proc.poll() is None:
            if not _expired(job):
                return job
            _kill_child(job, proc)
            job["state"] = "timeout"
            _close(job)
            continue
        _finalize(job, proc)
    return None


def _stderr_excerpt(job_id: str) -> str:
    err = jobs_dir() / f"{job_id}.err"
    if not err.exists():
        return "no detail on stderr."
    text = err.read_text(encoding="utf-8", errors="replace").strip()
    return text[-_STDERR_EXCERPT_CHARS:] or "no detail on stderr."


def _close(job: dict):
    """Persist a job that left the running state and free the lock it held."""
    _write_job(job)
    release_lock(job.get("pid"))
    release_lock()


def _finalize(job: dict, proc):
    """Transition a no-longer-alive 'running' job to done/error and persist."""
    rc = proc.poll() if proc is not None else None
    if proc is not None and rc == 0:
        job["state"] = "done"
        out = jobs_dir() / f"{job['job_id']}.out"
        report = out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""
        # A batch journals each file itself (scripts/ops/ingest-pending.py).
        gap = (None if job.get("kind") == "batch"
               else journal_gap(job["path"], job.get("log_mentions", 0), report))
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
    _close(job)


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


def _spawn(job: dict):
    """Start a queued job; the caller holds cache/ingest.lock. The journal
    baseline is read now, not at queue time: an earlier job of the queue may
    have journaled the same path."""
    job_id = job["job_id"]
    job["log_mentions"] = journal_mentions(job["path"])
    out = open(jobs_dir() / f"{job_id}.out", "wb")
    err = open(jobs_dir() / f"{job_id}.err", "wb")
    try:
        proc = subprocess.Popen(job["cmd"], stdout=out, stderr=err,
                                cwd=str(wiki_core.WIKI_PATH))
    except OSError as e:
        reason = "not found" if isinstance(e, FileNotFoundError) else str(e)
        job["state"] = "error"
        job["detail"] = f"cannot spawn {job['cmd'][0]!r} ({reason})"
        _close(job)
        return
    finally:
        out.close()
        err.close()
    _PROCS[job_id] = proc
    transfer_lock(proc.pid, owner=f"mcp job {job_id}")
    job.update({"pid": proc.pid, "server_pid": os.getpid(),
                "started_at": time.time(), "state": "running"})
    _write_job(job)


def _tick():
    """Resolve the running slot, then promote the oldest queued job if the
    slot and cache/ingest.lock are both free."""
    if _running_job() is not None:
        return
    while _queued_jobs():
        if not acquire_lock(owner="mcp server"):
            return  # another process (e.g. the scheduled batch) ingests
        queued = _queued_jobs()  # re-read under the lock
        if not queued:
            release_lock()
            return
        _spawn(queued[0])
        if _read_job(queued[0]["job_id"]).get("state") == "running":
            return


# ---- background promotion -------------------------------------------------
def _ticker_loop():
    """Promote queued jobs when the slot frees, even if no tool call comes:
    wait on our running child (wakes up as soon as it exits) or, when the
    slot is held elsewhere, poll every TICK_S. Exits once nothing is queued
    or running."""
    global _TICKER
    while not _TICKER_STOP.is_set():
        with _MUTEX:
            _tick()
            running = _running_job()
            proc = _PROCS.get(running["job_id"]) if running else None
            if running is None and not _queued_jobs():
                if _TICKER is threading.current_thread():
                    _TICKER = None
                return
        if proc is not None:
            try:
                proc.wait(timeout=TICK_S)
            except subprocess.TimeoutExpired:
                pass
        else:
            _TICKER_STOP.wait(TICK_S)
    with _MUTEX:
        if _TICKER is threading.current_thread():
            _TICKER = None


def _ensure_ticker():
    """Start the promotion thread if it is not running. Caller holds _MUTEX,
    so the thread cannot decide to exit between this check and the start."""
    global _TICKER
    if _TICKER is None:
        _TICKER_STOP.clear()
        _TICKER = threading.Thread(target=_ticker_loop, name="ingest-jobs-ticker",
                                   daemon=True)
        _TICKER.start()


def _stop_ticker():
    """Stop the promotion thread and wait for it (tests: before re-pointing
    wiki_core at another vault)."""
    with _MUTEX:
        thread = _TICKER
        _TICKER_STOP.set()
    if thread is not None:
        thread.join(timeout=10)


# ---- public API (wrapped as MCP tools by mcp-wiki.py) -----------------------
def _queue_position(job_id: str) -> int:
    ids = [j["job_id"] for j in _queued_jobs()]
    return ids.index(job_id) + 1 if job_id in ids else 0


def start(cmd, path: str, kind: str = "ingest") -> str:
    """Run cmd as a background job, or queue it (FIFO) behind the running one.
    kind "batch" marks the ingest_pending runner: no single-run watchdog, no
    journal check on its consolidated report."""
    with _MUTEX:
        jobs_dir().mkdir(parents=True, exist_ok=True)
        job_id = uuid.uuid4().hex[:12]
        _write_job({"job_id": job_id, "path": path, "kind": kind, "cmd": list(cmd),
                    "queued_at": time.time(), "state": "queued"})
        _tick()
        job = _read_job(job_id)
        if job["state"] == "running":
            _ensure_ticker()
            return f"Job {job_id} started for {path}. Poll ingest_status(\"{job_id}\")."
        if job["state"] == "queued":
            _ensure_ticker()
            return (f"Job {job_id} queued for {path} (position "
                    f"{_queue_position(job_id)}): another ingestion is running; "
                    f"it starts automatically when the slot frees. "
                    f"Poll ingest_status(\"{job_id}\").")
        return f"Error: {job.get('detail', 'job could not start')}."


def status(job_id: str) -> str:
    with _MUTEX:
        job = _read_job(job_id)
        if job is None:
            return f"Error: unknown job_id: {job_id}."
        if job["state"] in ("queued", "running"):
            _tick()
            job = _read_job(job_id)
        if job["state"] == "queued":
            _ensure_ticker()
            return (f"Job {job_id} queued (position {_queue_position(job_id)}, "
                    f"{job['path']}).")
        if job["state"] == "running":
            elapsed = time.time() - job["started_at"]
            return (f"Job {job_id} running "
                    f"({int(elapsed)}s elapsed, {job['path']}).")
        return _final_report(job)


def cancel(job_id: str) -> str:
    with _MUTEX:
        job = _read_job(job_id)
        if job is None:
            return f"Error: unknown job_id: {job_id}."
        if job["state"] == "queued":
            job["state"] = "cancelled"
            _write_job(job)
            return f"Job {job_id} cancelled before it started ({job['path']})."
        if job["state"] != "running":
            return f"Job {job_id} already finished ({job['state']}); nothing to cancel."
        proc = _PROCS.get(job_id)
        if proc is None:
            if _is_foreign(job):
                return (f"Job {job_id} belongs to another running MCP server "
                        f"process; cancel it from there.")
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
        _close(job)
        _tick()
        return f"Job {job_id} cancelled ({job['path']})."
