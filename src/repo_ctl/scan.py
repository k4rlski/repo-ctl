"""
scan.py - assemble a repo_alignment row for a slug across all four planes.

Read-only. Combines registry resolution + gh_remote (ls-remote) + walker
(local) + ssh_probe (server) into one dict matching db.COLUMNS.
"""

from datetime import datetime, timezone

from . import registry
from .gh_remote import ls_remote_head
from .walker import probe_local
from .ssh_probe import probe_server
from .db import compute_status


_EMPTY = {"path": None, "exists": False, "is_git": False, "branch": None,
          "head_sha": None, "dirty": None, "ahead": None, "behind": None}


def build_row(slug, skip_server=False):
    r = registry.resolve(slug)
    gh = ls_remote_head(r["github_ssh"])
    lf = probe_local(r["local_final"])
    lc = probe_local(r["local_current"]) if r["local_current"] else dict(_EMPTY)
    if r["server_host"] and not skip_server:
        srv = probe_server(r["server_host"], r["server_path"], r["ssh_user"])
    else:
        srv = dict(_EMPTY, host=r["server_host"], path=r["server_path"])

    row = {
        "slug": slug,
        "repo": f"k4rlski/{r['repo']}",
        "gh_default_branch": gh["default_branch"],
        "gh_head_sha": gh["head_sha"],
        "gh_head_date": None,
        "gh_pushed_at": None,

        "lf_path": lf["path"],
        "lf_exists": 1 if lf["exists"] else 0,
        "lf_is_git": 1 if lf["is_git"] else 0,
        "lf_branch": lf["branch"],
        "lf_head_sha": lf["head_sha"],
        "lf_dirty": lf["dirty"],
        "lf_ahead": lf["ahead"],
        "lf_behind": lf["behind"],

        "lc_path": lc["path"],
        "lc_exists": 1 if lc["exists"] else 0,
        "lc_is_git": 1 if lc["is_git"] else 0,
        "lc_branch": lc["branch"],
        "lc_head_sha": lc["head_sha"],
        "lc_dirty": lc["dirty"],
        "lc_ahead": lc["ahead"],
        "lc_behind": lc["behind"],

        "server_host": srv["host"],
        "server_path": srv["path"],
        "srv_exists": 1 if srv["exists"] else 0,
        "srv_is_git": 1 if srv["is_git"] else 0,
        "srv_branch": srv["branch"],
        "srv_head_sha": srv["head_sha"],
        "srv_dirty": srv["dirty"],
        "srv_ahead": srv["ahead"],
        "srv_behind": srv["behind"],

        "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }
    status, notes = compute_status(row)
    row["alignment_status"] = status
    row["notes"] = notes
    return row
