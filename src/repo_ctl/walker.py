"""
walker.py - read-only local git state + RAG metadata for a path.

Pure read-only: rev-parse / status / rev-list / log. Never fetches, never writes.
ahead/behind are computed against the local upstream (@{u}) if present, so they
reflect last-known remote refs (good enough for a quick alignment snapshot).

Also resolves a repo's RAG file (name, GitHub blob link, "Last updated:" date,
filesystem mtime, and first-commit/published date). Prefers the core-v5 copy,
then a stray local copy, else constructs the GitHub blob link from the
rag-index conventions (branch + filename exceptions, mars-status-hosted RAGs).
"""

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

GH_BASE = "https://github.com/k4rlski/"

# Repos whose RAG lives on a non-main default branch (rag-index conventions).
RAG_BRANCH = {
    "bkup-ctl": "master",
    "claw-ctl": "master",
    "core-v5": "master",
    "site-ctl": "master",
    "espo-crm": "release-mode",
}

# slug -> (repo, branch, filename) full override: RAG hosted in another repo
# and/or under a non-canonical filename (rag-index filename/location exceptions).
# NOTE: when a RAG is hosted in the mars-status repo, the branch is mars-status's
# default ("main"), NOT the tool's own RAG_BRANCH exception.
RAG_OVERRIDE = {
    # RAGs hosted in the mars-status repo (not the tool's own repo).
    "mars-status": ("mars-status", "main", "MARS-CTL-RAG.md"),
    "dropbox-ctl": ("mars-status", "main", "DROPBOX-CTL-RAG.md"),
    "pay-ctl": ("mars-status", "main", "PAY-CTL-RAG.md"),
    "access-ctl": ("mars-status", "main", "ACCESS-CTL-RAG.md"),
    "quote-ctl": ("mars-status", "main", "quote-ctl-rag.md"),
    "media-ctl": ("mars-status", "main", "media-ctl-rag.md"),
    "site-ctl": ("mars-status", "main", "site-ctl-rag.md"),
    "adctl": ("mars-status", "main", "adctl-rag.md"),
    # Filename-only exceptions (RAG in the tool's own repo, non-canonical name).
    "diagram-ctl": ("diagram-ctl", "main", "diagram-ctl-rag.md"),
    "cnx-ctl": ("cnx-ctl", "main", "map-stack-rag.md"),
    "espo-crm": ("espo-crm", "release-mode", "ESPO-CTL-RAG.md"),
}


def _git(path, *args, timeout=15):
    try:
        r = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        if r.returncode != 0:
            return None
        return r.stdout.strip()
    except Exception:
        return None


def iso_to_mysql(iso):
    """Convert a git ISO-8601 (%cI) timestamp to a UTC 'YYYY-MM-DD HH:MM:SS' string."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.strip())
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def probe_local(path):
    """Return a dict of git state for a local path. Tolerant of missing/non-git."""
    p = Path(path) if path else None
    state = {
        "path": str(path) if path else None,
        "exists": bool(p and p.exists()),
        "is_git": False,
        "branch": None,
        "head_sha": None,
        "head_date": None,
        "dirty": None,
        "ahead": None,
        "behind": None,
    }
    if not state["exists"]:
        return state
    if not (p / ".git").exists():
        return state

    state["is_git"] = True
    br = _git(p, "rev-parse", "--abbrev-ref", "HEAD")
    state["branch"] = "(detached)" if br == "HEAD" else br
    head = _git(p, "rev-parse", "HEAD")
    state["head_sha"] = head[:40] if head else None
    state["head_date"] = iso_to_mysql(_git(p, "log", "-1", "--format=%cI"))

    porcelain = _git(p, "status", "--porcelain")
    if porcelain is not None:
        state["dirty"] = len([l for l in porcelain.splitlines() if l.strip()])

    counts = _git(p, "rev-list", "--left-right", "--count", "HEAD...@{u}")
    if counts:
        parts = counts.split()
        if len(parts) == 2:
            state["ahead"], state["behind"] = int(parts[0]), int(parts[1])
    return state


def _empty_rag():
    return {
        "rag_name": None,
        "rag_link": None,
        "rag_last_updated": None,
        "rag_published_date": None,
        "rag_file_mtime": None,
    }


def _rag_score(name, slug, preferred):
    """Lower is better. Prefer the override/known filename, then a slug match."""
    n = name.lower()
    if preferred and n == preferred.lower():
        return 0
    if n in (f"{slug.lower()}-rag.md", f"{slug.lower()}_rag.md"):
        return 1
    if n.startswith(slug.lower()):
        return 2
    return 3


def _find_local_rag(repo_path, slug):
    """
    Find the RAG file for `slug` under <repo>/rag (then <repo>/docs).

    A repo (notably mars-status) may host several tools' RAGs, so prefer the
    override filename, then a name matching the slug, before the shortest name.
    Returns Path or None.
    """
    if not repo_path:
        return None
    preferred = RAG_OVERRIDE[slug][2] if slug in RAG_OVERRIDE else None
    base = Path(repo_path)
    for sub in ("rag", "docs"):
        d = base / sub
        if not d.is_dir():
            continue
        cands = []
        try:
            for f in d.iterdir():
                if f.is_file() and f.name.lower().endswith("rag.md"):
                    cands.append(f)
        except OSError:
            continue
        if cands:
            cands.sort(key=lambda f: (_rag_score(f.name, slug, preferred),
                                      len(f.name), f.name.lower()))
            return cands[0]
    return None


def _parse_last_updated(text):
    if not text:
        return None
    m = re.search(r"Last updated[:*\s]+(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
    return m.group(1) if m else None


def _file_first_commit_date(repo_path, rag_file):
    """First-add (published) date of the RAG file via git log, or None."""
    rel = os.path.relpath(str(rag_file), str(repo_path))
    out = _git(repo_path, "log", "--reverse", "--format=%cI",
               "--diff-filter=A", "--", rel)
    if not out:
        out = _git(repo_path, "log", "--format=%cI", "--", rel)
    if not out:
        return None
    first = out.splitlines()[0].strip()
    mysql = iso_to_mysql(first)
    return mysql.split(" ")[0] if mysql else None


def rag_repo_branch(slug, repo, default_branch=None):
    """
    Single source of truth for (link_repo, branch) of a slug's RAG blob link.

    Applies the rag-index conventions in order:
      1. full override (RAG hosted in another repo and/or non-canonical name);
      2. branch exception for the slug's own repo (bkup-ctl/claw-ctl/core-v5/
         site-ctl -> master; espo-crm -> release-mode);
      3. the live default branch from ls-remote, else "main".
    """
    if slug in RAG_OVERRIDE:
        rrepo, branch, _ = RAG_OVERRIDE[slug]
        return rrepo, branch
    branch = RAG_BRANCH.get(slug) or default_branch or "main"
    return repo, branch


def _blob_link(link_repo, branch, sub, fname):
    return f"{GH_BASE}{link_repo}/blob/{branch}/{sub}/{fname}"


def _construct_blob_link(slug, repo, default_branch=None):
    """Build a GitHub blob link to the RAG using rag-index conventions (no local file)."""
    link_repo, branch = rag_repo_branch(slug, repo, default_branch)
    fname = RAG_OVERRIDE[slug][2] if slug in RAG_OVERRIDE else f"{repo.upper()}-RAG.md"
    return _blob_link(link_repo, branch, "rag", fname), fname


def resolve_rag(slug, repo, local_final=None, local_current=None, default_branch=None):
    """
    Resolve RAG metadata for a slug.

    Prefer the core-v5 copy (local_final), then a stray local copy (local_current);
    if neither has the file, construct the GitHub blob link + name from conventions
    (dates left NULL, as we do not fetch remote content here).
    """
    out = _empty_rag()
    for repo_path in (local_final, local_current):
        rag_file = _find_local_rag(repo_path, slug)
        if not rag_file:
            continue
        # Dates/mtime come from whatever local copy we found.
        try:
            mtime = datetime.fromtimestamp(rag_file.stat().st_mtime, tz=timezone.utc)
            out["rag_file_mtime"] = mtime.strftime("%Y-%m-%d %H:%M:%S")
        except OSError:
            pass
        try:
            out["rag_last_updated"] = _parse_last_updated(
                rag_file.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
        out["rag_published_date"] = _file_first_commit_date(repo_path, rag_file)
        # Canonical name + blob link follow the rag-index conventions. For a full
        # override (RAG authoritatively hosted elsewhere and/or under a fixed
        # filename), never let a stray local copy's name/subdir leak into the link
        # — use the override's canonical rag/<filename>. For non-override repos the
        # on-disk file IS canonical, so use its real name + subdir.
        link_repo, branch = rag_repo_branch(slug, repo, default_branch)
        if slug in RAG_OVERRIDE:
            fname = RAG_OVERRIDE[slug][2]
            sub = "rag"
        else:
            fname = rag_file.name
            sub = rag_file.parent.name  # rag or docs
        out["rag_name"] = fname
        out["rag_link"] = _blob_link(link_repo, branch, sub, fname)
        return out

    link, fname = _construct_blob_link(slug, repo, default_branch)
    out["rag_link"] = link
    out["rag_name"] = fname
    return out
