"""
db.py - dbx/infra_ctl connection + repo_alignment upsert + alignment computation.

Connection modes (from config `dbx:`):
  - via_claw_tunnel: true  -> open `ssh -L <local_port>:127.0.0.1:3307 <tunnel_host> -N`
                              and connect 127.0.0.1:<local_port> (osiris path).
  - via_claw_tunnel: false -> connect host/port directly (rodan path; needs a host grant).

Read-write only to the `repo_alignment` table. No schema mutations here
(apply schema.sql once out-of-band).
"""

import subprocess
import time
import contextlib
import socket

import pymysql


COLUMNS = [
    "slug", "repo",
    "gh_default_branch", "gh_head_sha", "gh_head_date", "gh_pushed_at",
    "lf_path", "lf_exists", "lf_is_git", "lf_branch", "lf_head_sha",
    "lf_dirty", "lf_ahead", "lf_behind",
    "lc_path", "lc_exists", "lc_is_git", "lc_branch", "lc_head_sha",
    "lc_dirty", "lc_ahead", "lc_behind",
    "server_host", "server_path", "srv_exists", "srv_is_git", "srv_branch",
    "srv_head_sha", "srv_dirty", "srv_ahead", "srv_behind",
    "alignment_status", "notes", "scanned_at",
]


@contextlib.contextmanager
def _maybe_tunnel(cfg):
    """Open an ssh -L forward to claw if configured; yield (host, port)."""
    if not cfg.get("via_claw_tunnel"):
        yield cfg.get("host", "dbx.auto-ops.net"), int(cfg.get("port", 3306))
        return

    local_port = int(cfg.get("local_port", 13307))
    tunnel_host = cfg.get("tunnel_host", "root@claw.auto-ctl.io")
    proc = subprocess.Popen(
        ["ssh", "-N", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
         "-o", "ExitOnForwardFailure=yes",
         "-L", f"{local_port}:127.0.0.1:3307", tunnel_host],
        stdin=subprocess.DEVNULL,
    )
    try:
        # wait for the local forward to accept connections
        for _ in range(40):
            with contextlib.suppress(OSError):
                with socket.create_connection(("127.0.0.1", local_port), timeout=1):
                    break
            time.sleep(0.25)
        yield "127.0.0.1", local_port
    finally:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)


@contextlib.contextmanager
def connect(cfg):
    """Yield a pymysql connection to infra_ctl (opening a tunnel first if needed)."""
    with _maybe_tunnel(cfg) as (host, port):
        conn = pymysql.connect(
            host=host, port=port,
            user=cfg.get("user", "perm_ctl"),
            password=cfg.get("password", ""),
            database=cfg.get("database", "infra_ctl"),
            connect_timeout=8, autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            yield conn
        finally:
            conn.close()


def compute_status(row):
    """Derive alignment_status + a human notes string from a row dict."""
    gh = row.get("gh_head_sha")
    lf = row.get("lf_head_sha") if row.get("lf_is_git") else None
    srv = row.get("srv_head_sha") if row.get("srv_is_git") else None
    server_expected = bool(row.get("server_host"))
    dirty_any = any((row.get(k) or 0) > 0 for k in ("lf_dirty", "lc_dirty", "srv_dirty"))

    notes = []
    # Missing planes
    if not row.get("lf_is_git"):
        notes.append("no core-v5 git home")
    if server_expected and not row.get("srv_is_git"):
        notes.append("server path missing/not-git")

    status = "unknown"
    present = [s for s in (gh, lf, srv) if s]
    if not row.get("lf_is_git") or (server_expected and not row.get("srv_is_git")):
        status = "missing"
    elif present and len(set(present)) == 1 and not dirty_any:
        status = "aligned"
    elif present:
        status = "drift"
        if gh and lf and gh != lf:
            notes.append("core-v5 != github")
        if gh and srv and gh != srv:
            notes.append("server != github")
        if dirty_any:
            d = []
            if (row.get("srv_dirty") or 0) > 0:
                d.append(f"srv {row['srv_dirty']} dirty")
            if (row.get("lf_dirty") or 0) > 0:
                d.append(f"core-v5 {row['lf_dirty']} dirty")
            notes.append("; ".join(d))

    return status, "; ".join(notes)


def upsert(conn, row):
    """Idempotent upsert of one repo_alignment row (dict keyed by COLUMNS)."""
    cols = [c for c in COLUMNS]
    placeholders = ", ".join(["%s"] * len(cols))
    updates = ", ".join(f"{c}=VALUES({c})" for c in cols if c != "slug")
    sql = (
        f"INSERT INTO repo_alignment ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )
    values = [row.get(c) for c in cols]
    with conn.cursor() as cur:
        cur.execute(sql, values)
