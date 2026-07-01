"""
scan.py - assemble a repo_alignment row for a slug across all four planes.

Read-only. Combines registry resolution + gh_remote (ls-remote) + walker
(local) + ssh_probe (server) into one dict matching db.COLUMNS.
"""

from datetime import datetime, timezone

from . import registry
from . import tool_pages
from .gh_remote import ls_remote_head
from .walker import probe_local, resolve_rag
from .ssh_probe import probe_server
from .db import compute_status


_EMPTY = {"path": None, "exists": False, "is_git": False, "branch": None,
          "head_sha": None, "head_date": None, "dirty": None,
          "ahead": None, "behind": None}


def _now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def build_row(slug, skip_server=False):
    r = registry.resolve(slug)
    gh = ls_remote_head(r["github_ssh"])
    lf = probe_local(r["local_final"])
    lc = probe_local(r["local_current"]) if r["local_current"] else dict(_EMPTY)
    if r["server_host"] and not skip_server:
        srv = probe_server(r["server_host"], r["server_path"], r["ssh_user"])
    else:
        srv = dict(_EMPTY, host=r["server_host"], path=r["server_path"])

    repo = f"k4rlski/{r['repo']}"
    row = {
        "slug": slug,
        "repo": repo,
        "name": repo.split("/")[-1],
        "github_link": "https://github.com/" + repo,
        "gh_default_branch": gh["default_branch"],
        "gh_head_sha": gh["head_sha"],
        "gh_head_date": None,
        "gh_pushed_at": None,

        "lf_path": lf["path"],
        "lf_exists": 1 if lf["exists"] else 0,
        "lf_is_git": 1 if lf["is_git"] else 0,
        "lf_branch": lf["branch"],
        "lf_head_sha": lf["head_sha"],
        "lf_head_date": lf.get("head_date"),
        "lf_dirty": lf["dirty"],
        "lf_ahead": lf["ahead"],
        "lf_behind": lf["behind"],

        "lc_path": lc["path"],
        "lc_exists": 1 if lc["exists"] else 0,
        "lc_is_git": 1 if lc["is_git"] else 0,
        "lc_branch": lc["branch"],
        "lc_head_sha": lc["head_sha"],
        "lc_head_date": lc.get("head_date"),
        "lc_dirty": lc["dirty"],
        "lc_ahead": lc["ahead"],
        "lc_behind": lc["behind"],

        "server_host": srv["host"],
        "server_path": srv["path"],
        "srv_exists": 1 if srv["exists"] else 0,
        "srv_is_git": 1 if srv["is_git"] else 0,
        "srv_branch": srv["branch"],
        "srv_head_sha": srv["head_sha"],
        "srv_head_date": srv.get("head_date"),
        "srv_dirty": srv["dirty"],
        "srv_ahead": srv["ahead"],
        "srv_behind": srv["behind"],

        "scanned_at": _now_utc(),
    }

    # Non-persisted helper: did the GitHub probe get a definitive answer this
    # scan? Used by compute_status to avoid a false `aligned` when ls-remote
    # failed transiently (network) — see db.compute_status. Not a DB column.
    row["_gh_probe_ok"] = bool(gh.get("probe_ok", True))

    rag = resolve_rag(slug, r["repo"], local_final=r["local_final"],
                      local_current=r["local_current"],
                      default_branch=gh.get("default_branch"))
    row.update(rag)
    row["tool_page_link"] = tool_pages.page_link(slug)

    status, notes = compute_status(row)
    row["alignment_status"] = status
    row["notes"] = notes
    return row


def build_metadata_row(slug):
    """
    Build only the RAG / tool-page / date metadata for a slug (no git re-probe).

    Used by `refresh-alignment --metadata-only` for a fast post-CRUD refresh.
    Reads only the local RAG file(s) (a single cheap git-log for the published
    date) and the static tool-page map — no ls-remote, no server SSH.
    """
    r = registry.resolve(slug)
    rag = resolve_rag(slug, r["repo"], local_final=r["local_final"],
                      local_current=r["local_current"])
    row = {"slug": slug, "tool_page_link": tool_pages.page_link(slug),
           "scanned_at": _now_utc()}
    row.update(rag)
    return row
