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
    "slug", "repo", "name", "github_link",
    "gh_default_branch", "gh_head_sha", "gh_head_date", "gh_pushed_at",
    "lf_path", "lf_exists", "lf_is_git", "lf_branch", "lf_head_sha",
    "lf_head_date", "lf_dirty", "lf_ahead", "lf_behind",
    "lc_path", "lc_exists", "lc_is_git", "lc_branch", "lc_head_sha",
    "lc_head_date", "lc_dirty", "lc_ahead", "lc_behind",
    "server_host", "server_path", "srv_exists", "srv_is_git", "srv_branch",
    "srv_head_sha", "srv_head_date", "srv_dirty", "srv_ahead", "srv_behind",
    "rag_name", "rag_link", "rag_last_updated", "rag_published_date",
    "rag_file_mtime", "tool_page_link",
    "alignment_status", "notes", "scanned_at",
]

# Columns refreshable without a full git re-probe (post-CRUD metadata refresh).
METADATA_COLUMNS = [
    "rag_name", "rag_link", "rag_last_updated", "rag_published_date",
    "rag_file_mtime", "tool_page_link", "scanned_at",
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
    """
    Derive alignment_status + a consolidation-checklist notes string from a row.

    Statuses:
      aligned  - core-v5 is a git checkout and all present planes agree on sha
      drift    - core-v5 is a git checkout but planes disagree (or are dirty)
      uncloned - a folder and/or GitHub repo exists, but core-v5 has no .git yet
                 (not yet consolidated as a git checkout)
      absent   - nothing anywhere (no folder on any plane and no GitHub repo)
      unknown  - GitHub was unreachable this scan, so alignment can't be confirmed
    """
    gh = row.get("gh_head_sha")
    lf = row.get("lf_head_sha") if row.get("lf_is_git") else None
    lc = row.get("lc_head_sha") if row.get("lc_is_git") else None
    srv = row.get("srv_head_sha") if row.get("srv_is_git") else None
    server_expected = bool(row.get("server_host"))
    lf_is_git = bool(row.get("lf_is_git"))
    folder_anywhere = any(row.get(k) for k in ("lf_exists", "lc_exists", "srv_exists"))
    gh_exists = bool(gh) or bool(row.get("gh_default_branch"))
    dirty_any = any((row.get(k) or 0) > 0 for k in ("lf_dirty", "lc_dirty", "srv_dirty"))
    # Transient GitHub failure: no definitive ls-remote answer AND no sha. We must
    # not treat GitHub as a legitimately-absent plane (would yield a false aligned).
    gh_unreachable = (not row.get("_gh_probe_ok", True)) and not gh

    notes = []

    # Not consolidated as a git checkout in core-v5 -> uncloned or absent.
    if not lf_is_git:
        if not gh_exists and not folder_anywhere:
            if gh_unreachable:
                notes.append("github unreachable this scan — cannot confirm repo absence")
                return "unknown", "; ".join(notes)
            notes.append("nothing on any plane — nothing to clone")
            return "absent", "; ".join(notes)

        if row.get("lf_exists"):
            notes.append("core-v5 folder exists but is NOT a git checkout — git init/clone here")
        else:
            notes.append("no core-v5 folder yet — clone into core-v5")
        if gh_exists:
            notes.append("GitHub repo available to clone")
        if row.get("lc_is_git") and row.get("lc_path"):
            notes.append(f"stray git clone at {row['lc_path']} — consolidate into core-v5")
        elif row.get("lc_exists") and row.get("lc_path"):
            notes.append(f"stray folder at {row['lc_path']}")
        if server_expected and row.get("srv_is_git"):
            notes.append("server is a git checkout (source of truth)")
        elif server_expected and not row.get("srv_is_git"):
            notes.append("server path missing/not-git")
        return "uncloned", "; ".join(notes)

    # core-v5 IS a git checkout -> aligned or drift across present planes.
    present = [s for s in (gh, lf, lc, srv) if s]
    if present and len(set(present)) == 1 and not dirty_any:
        if server_expected and not row.get("srv_is_git"):
            notes.append("server path missing/not-git (deploy needed)")
            return "drift", "; ".join(notes)
        if gh_unreachable:
            # All *reachable* planes agree, but we couldn't confirm GitHub —
            # don't claim aligned on incomplete evidence.
            notes.append("github unreachable this scan — cannot confirm alignment")
            return "unknown", "; ".join(notes)
        notes.append("all present planes agree")
        return "aligned", "; ".join(notes)

    status = "drift"
    if gh and lf and gh != lf:
        notes.append("core-v5 != github")
    if gh and srv and gh != srv:
        notes.append("server != github")
    if lf and srv and lf != srv:
        notes.append("core-v5 != server")
    # Stray local-current clone divergence (otherwise this case yields empty notes).
    if lc:
        ref_name, ref_sha = None, None
        if lf and lc != lf:
            ref_name, ref_sha = "core-v5", lf
        elif gh and lc != gh:
            ref_name, ref_sha = "github", gh
        elif srv and lc != srv:
            ref_name, ref_sha = "server", srv
        if ref_name:
            notes.append(
                f"stray local-current clone at {row.get('lc_path')} "
                f"diverges from {ref_name} @ {ref_sha[:7]}")
    if gh_unreachable:
        notes.append("github unreachable this scan")
    if server_expected and not row.get("srv_is_git"):
        notes.append("server path missing/not-git (deploy needed)")
    if dirty_any:
        d = []
        if (row.get("srv_dirty") or 0) > 0:
            d.append(f"srv {row['srv_dirty']} dirty")
        if (row.get("lf_dirty") or 0) > 0:
            d.append(f"core-v5 {row['lf_dirty']} dirty")
        if (row.get("lc_dirty") or 0) > 0:
            d.append(f"current {row['lc_dirty']} dirty")
        if d:
            notes.append("; ".join(d))
    return status, "; ".join(notes)


def upsert(conn, row):
    """
    Idempotent upsert of one repo_alignment row (dict keyed by COLUMNS).

    COLUMNS deliberately EXCLUDES the manually-curated fields (hidden, statrepo,
    rolerepo, statprod, tooltype): they are never inserted or updated by a scan,
    so DB defaults apply on first insert (hidden=0, statrepo/rolerepo/statprod/
    tooltype NULL) and manual values survive every subsequent scan.

    server_host / server_path use COALESCE-on-null so a scan only overwrites them
    when it actually computed a non-null value. Registry-defined slugs stay
    registry-authoritative; manual server edits for registry-less slugs survive.
    """
    cols = [c for c in COLUMNS]
    placeholders = ", ".join(["%s"] * len(cols))
    _coalesce = {"server_host", "server_path"}
    update_parts = []
    for c in cols:
        if c == "slug":
            continue
        if c in _coalesce:
            update_parts.append(f"{c}=COALESCE(VALUES({c}), {c})")
        else:
            update_parts.append(f"{c}=VALUES({c})")
    updates = ", ".join(update_parts)
    sql = (
        f"INSERT INTO repo_alignment ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )
    values = [row.get(c) for c in cols]
    with conn.cursor() as cur:
        cur.execute(sql, values)


# RAG date columns: only ever WRITE these when we actually parsed a value this
# run. If the local RAG file wasn't readable, omit them from the UPDATE SET so we
# don't null-out previously-populated values (leave existing DB values intact).
_RAG_DATE_COLUMNS = {"rag_last_updated", "rag_published_date", "rag_file_mtime"}


def update_metadata(conn, row):
    """
    Refresh only the metadata columns for one slug (post-CRUD refresh).

    Safe targeted UPDATE (does NOT touch git/sha/status columns), so it will not
    null-out an existing full row. RAG date fields are only written when actually
    parsed this run (omitted when None, so existing values survive).

    Returns 1 if an existing row was MATCHED (even if nothing changed), else 0.
    Uses an explicit existence SELECT because pymysql's rowcount counts CHANGED
    (not matched) rows by default — a no-op refresh of an existing row would
    otherwise look like "no row exists".
    """
    cols = [c for c in METADATA_COLUMNS
            if c not in _RAG_DATE_COLUMNS or row.get(c) is not None]
    assignments = ", ".join(f"{c}=%s" for c in cols)
    values = [row.get(c) for c in cols] + [row.get("slug")]
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM repo_alignment WHERE slug=%s LIMIT 1",
                    (row.get("slug"),))
        if cur.fetchone() is None:
            return 0
        cur.execute(f"UPDATE repo_alignment SET {assignments} WHERE slug=%s", values)
        return 1
