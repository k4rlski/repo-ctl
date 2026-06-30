"""
ssh_probe.py - read-only server git state over SSH (the Server/source-of-truth plane).

Runs a single batched remote command that prints git state for a path. Read-only:
rev-parse / status / rev-list. Tolerant of unreachable hosts and non-git paths.
"""

import subprocess


# One remote shell snippet; prints KEY=VALUE lines we parse back.
_REMOTE = (
    'p="{path}"; '
    'if [ ! -e "$p" ]; then echo EXISTS=0; exit 0; fi; '
    'echo EXISTS=1; '
    'if [ ! -e "$p/.git" ]; then echo ISGIT=0; exit 0; fi; '
    'echo ISGIT=1; '
    'echo "BRANCH=$(git -C "$p" rev-parse --abbrev-ref HEAD 2>/dev/null)"; '
    'echo "HEAD=$(git -C "$p" rev-parse HEAD 2>/dev/null)"; '
    'echo "DIRTY=$(git -C "$p" status --porcelain 2>/dev/null | grep -c .)"; '
    'echo "ABCNT=$(git -C "$p" rev-list --left-right --count HEAD...@{{u}} 2>/dev/null)"'
)


def probe_server(host, path, ssh_user="root", timeout=20):
    """Return a dict of git state for host:path. Tolerant of failures."""
    state = {
        "host": host, "path": path, "exists": False, "is_git": False,
        "branch": None, "head_sha": None, "dirty": None,
        "ahead": None, "behind": None, "reachable": False,
    }
    if not host or not path:
        return state
    remote = _REMOTE.format(path=path)
    try:
        r = subprocess.run(
            ["ssh", "-n", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
             "-o", "ConnectTimeout=8", f"{ssh_user}@{host}", remote],
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except Exception:
        return state
    if r.returncode != 0 and not r.stdout:
        return state

    state["reachable"] = True
    kv = {}
    for line in r.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            kv[k.strip()] = v.strip()

    state["exists"] = kv.get("EXISTS") == "1"
    state["is_git"] = kv.get("ISGIT") == "1"
    state["branch"] = kv.get("BRANCH") or None
    head = kv.get("HEAD") or ""
    state["head_sha"] = head[:40] if head else None
    if kv.get("DIRTY", "").isdigit():
        state["dirty"] = int(kv["DIRTY"])
    ab = kv.get("ABCNT", "").split()
    if len(ab) == 2 and ab[0].isdigit() and ab[1].isdigit():
        state["ahead"], state["behind"] = int(ab[0]), int(ab[1])
    return state
