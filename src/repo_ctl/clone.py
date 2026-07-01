"""
clone.py - the repo-ctl `clone-local` pull-agent.

Runs on a workstation (osiris/ares/raven). Polls infra_ctl.repo_clone_jobs for a
pending job addressed to this host, atomically claims it, and git-clones the
GitHub repo into its `core-v5/<slug>` home -- but ONLY when that is genuinely
safe (dest absent-or-empty AND the GitHub repo really exists). On success it
re-scans the slug so the repo_alignment row flips uncloned->aligned immediately.
Every attempt is recorded in repo_clone_log and reflected back on the job row.

Strictly additive: db.py schema is untouched; only its existing helpers
(`connect`, `upsert`) are called. Registry/scan/gh_remote are used read-only.
"""

import os
import re
import shutil
import socket
import subprocess
import tempfile
from datetime import datetime, timezone

from . import registry
from . import scan as scanmod
from . import db as dbmod
from .gh_remote import ls_remote_head
from .registry import CORE_V5


# `git clone` hard timeout (seconds).
CLONE_TIMEOUT = 300

# Valid slug charset (also used to reject path-traversal / option-injection).
_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# log status (success|failed|skipped) -> job status (done|failed|skipped).
_JOB_STATUS = {"success": "done", "failed": "failed", "skipped": "skipped"}

_DT_FMT = "%Y-%m-%d %H:%M:%S"


def short_host(host=None):
    """Short, lowercased hostname used as host identity / claimed_by."""
    h = host or socket.gethostname()
    return h.split(".")[0].strip().lower()


def _now():
    return datetime.now(timezone.utc)


def _dir_is_empty(path):
    try:
        return len(os.listdir(path)) == 0
    except OSError:
        return False


def _first_line(text, limit=400):
    if not text:
        return ""
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line[:limit]


def claim_job(conn, host):
    """
    Atomically claim ONE pending job for `host`.

    Selects the oldest pending job, then guards the UPDATE with
    `status='pending'` and only proceeds when exactly one row changed -- so two
    concurrent poll cycles can never both win the same job. Returns (id, slug)
    or None when there is nothing to do (or another cycle claimed it first).
    claimed_by is this machine's short hostname.
    """
    claimer = short_host()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, slug FROM repo_clone_jobs "
            "WHERE host=%s AND status='pending' ORDER BY id LIMIT 1",
            (host,),
        )
        job = cur.fetchone()
        if not job:
            return None
        cur.execute(
            "UPDATE repo_clone_jobs SET status='running', claimed_by=%s, "
            "claimed_at=NOW() WHERE id=%s AND status='pending'",
            (claimer, job["id"]),
        )
        if cur.rowcount != 1:
            # Lost the race to another poller -- treat as "nothing claimed".
            return None
    return job["id"], job["slug"]


def resolve_dest(slug):
    """
    Resolve (dest_path, clone_url) for a slug with hard path-containment checks.

    Rejects unsafe slugs (leading '-', anything outside [A-Za-z0-9._-]) and
    asserts the destination lives strictly under core-v5, so a poisoned
    registry/slug can never cause a write outside the HQ. Raises ValueError on
    any violation.
    """
    if not slug or slug.startswith("-") or not _SLUG_RE.match(slug):
        raise ValueError(f"unsafe slug: {slug!r}")
    r = registry.resolve(slug)
    dest = r["local_final"]
    clone_url = r["github_ssh"]
    core_root = os.path.realpath(str(CORE_V5)) + os.sep
    if not os.path.realpath(dest).startswith(core_root):
        raise ValueError(f"dest {dest!r} escapes core-v5 ({core_root!r})")
    return dest, clone_url


def _log_and_finish(conn, job_id, slug, outcome, started, message, host,
                    error=None):
    """Write a repo_clone_log row and flip the job to its terminal status."""
    finished = _now()
    duration = round((finished - started).total_seconds(), 2)
    job_status = _JOB_STATUS[outcome]
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO repo_clone_log "
            "(slug, started_at, finished_at, duration_sec, status, error_msg, host) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (slug, started.strftime(_DT_FMT), finished.strftime(_DT_FMT),
             duration, outcome, error, host),
        )
        cur.execute(
            "UPDATE repo_clone_jobs SET status=%s, finished_at=NOW(), message=%s "
            "WHERE id=%s",
            (job_status, (message or "")[:2000], job_id),
        )


def _process_job(conn, job_id, slug, host):
    """Guard, clone, re-scan and record one claimed job. Returns a summary dict.

    B2 safety net: the entire body (everything after the job is claimed) runs
    inside a try/except so that ANY unexpected failure -- os.makedirs,
    tempfile.mkdtemp, os.rmdir, os.replace raising OSError, etc. -- still drives
    the job to a terminal 'failed' status via the normal finalize path. Without
    this a mid-flight exception would propagate out of run_poller and leave the
    row stuck 'running' forever (claim_job only selects 'pending', so it would
    never be retried). `finalized` guards against a double-finalize when done()
    already ran on a normal return path.
    """
    started = _now()
    result = {"ok": False, "action": None, "slug": slug, "job_id": job_id,
              "message": ""}
    finalized = False

    def done(outcome, message, error=None):
        nonlocal finalized
        finalized = True
        _log_and_finish(conn, job_id, slug, outcome, started, message, host,
                        error=error)
        result.update(ok=(outcome != "failed"), action=outcome, message=message)
        return result

    try:
        try:
            dest, clone_url = resolve_dest(slug)
        except ValueError as e:
            return done("failed", str(e), error=str(e))

        # Guardrail (a): dest must be absent OR an empty directory.
        if os.path.exists(dest):
            if not os.path.isdir(dest) or not _dir_is_empty(dest):
                return done("skipped", "dest non-empty -- manual consolidation")

        # Guardrail (b): re-probe the remote. A transient/ambiguous probe
        # failure (probe_ok=False) must be retryable -> 'failed', NOT terminal
        # 'skipped'. Only a *definitive* absent answer (probe_ok=True and no
        # head_sha) means there is genuinely no repo to clone.
        gh = ls_remote_head(clone_url)
        if not gh.get("probe_ok"):
            return done("failed", "remote probe failed",
                        error="ls_remote_head probe_ok=False (transient)")
        if not gh.get("head_sha"):
            return done("skipped", "no GitHub repo to clone")

        # Clone into a temp dir SIBLING of dest (same parent -> same filesystem,
        # so the final os.replace is an atomic rename), then move it into place.
        parent = os.path.dirname(dest)
        os.makedirs(parent, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix=f".clone-{slug}-", dir=parent)
        try:
            env = dict(os.environ)
            env["GIT_TERMINAL_PROMPT"] = "0"
            env["GIT_SSH_COMMAND"] = (
                "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new")
            try:
                proc = subprocess.run(
                    ["git", "clone", clone_url, tmp],
                    capture_output=True, text=True, timeout=CLONE_TIMEOUT,
                    env=env, stdin=subprocess.DEVNULL,
                )
            except subprocess.TimeoutExpired:
                return done("failed", f"clone timed out after {CLONE_TIMEOUT}s",
                            error=f"timeout after {CLONE_TIMEOUT}s")

            if proc.returncode != 0:
                err = _first_line(proc.stderr) or _first_line(proc.stdout) \
                    or f"git clone exit {proc.returncode}"
                return done("failed", err, error=(proc.stderr or proc.stdout))

            # Success: swap the freshly-cloned tree into its home atomically.
            if os.path.isdir(dest) and _dir_is_empty(dest):
                os.rmdir(dest)
            os.replace(tmp, dest)
            tmp = None  # consumed by os.replace; don't clean up below
        finally:
            if tmp and os.path.isdir(tmp):
                shutil.rmtree(tmp, ignore_errors=True)

        # Post-clone: re-scan so the row flips uncloned->aligned immediately.
        # Best-effort: a scan/DB hiccup must NOT lose the good clone.
        rescan_note = ""
        try:
            row = scanmod.build_row(slug)
            dbmod.upsert(conn, row)
        except Exception as e:  # noqa: BLE001 - best-effort, keep the clone
            rescan_note = f" (rescan warning: {e})"

        sha = (gh.get("head_sha") or "")[:7]
        msg = f"cloned {sha} into core-v5/{slug}{rescan_note}"
        return done("success", msg)
    except Exception as e:  # noqa: BLE001 - never leave a claimed job 'running'
        # Any failure after claim that wasn't already finalized above must
        # still reach a terminal status (and be logged, not swallowed).
        if not finalized:
            return done("failed", str(e), error=str(e))
        raise


def run_poller(cfg, host):
    """
    Open one dbx connection, claim + process ONE job, return a summary dict.

    One job per invocation keeps the agent simple and safe under a 2-minute
    cron; the flock wrapper prevents overlapping runs. Summary dict keys:
    ok(bool), action(noop|success|skipped|failed|error), slug, job_id, message.
    """
    dbx = cfg.get("dbx")
    if not dbx:
        return {"ok": False, "action": "error", "message": "no dbx config"}
    with dbmod.connect(dbx) as conn:
        claim = claim_job(conn, host)
        if not claim:
            return {"ok": True, "action": "noop", "message": "no pending jobs"}
        job_id, slug = claim
        return _process_job(conn, job_id, slug, host)
