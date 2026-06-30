"""
walker.py - read-only local git state for a path (used for Local-final + Local-current).

Pure read-only: rev-parse / status / rev-list. Never fetches, never writes.
ahead/behind are computed against the local upstream (@{u}) if present, so they
reflect last-known remote refs (good enough for a quick alignment snapshot).
"""

import subprocess
from pathlib import Path


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


def probe_local(path):
    """Return a dict of git state for a local path. Tolerant of missing/non-git."""
    p = Path(path) if path else None
    state = {
        "path": str(path) if path else None,
        "exists": bool(p and p.exists()),
        "is_git": False,
        "branch": None,
        "head_sha": None,
        "dirty": None,
        "ahead": None,
        "behind": None,
    }
    if not state["exists"]:
        return state
    if not (p / ".git").exists():
        return state

    state["is_git"] = True
    state["branch"] = _git(p, "rev-parse", "--abbrev-ref", "HEAD")
    head = _git(p, "rev-parse", "HEAD")
    state["head_sha"] = head[:40] if head else None

    porcelain = _git(p, "status", "--porcelain")
    if porcelain is not None:
        state["dirty"] = len([l for l in porcelain.splitlines() if l.strip()])

    counts = _git(p, "rev-list", "--left-right", "--count", "HEAD...@{u}")
    if counts:
        parts = counts.split()
        if len(parts) == 2:
            state["ahead"], state["behind"] = int(parts[0]), int(parts[1])
    return state
