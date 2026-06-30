"""
gh_remote.py - token-free GitHub state via `git ls-remote` over SSH.

Returns the default branch + HEAD sha for a repo without any PAT, using the
existing SSH key. Optional API extras (commit date, pushedAt) are left to the
GitHubClient when a read-only token is configured.
"""

import subprocess


_ABSENT_HINTS = (
    "repository not found",
    "does not exist",
    "not found",
    "access denied",
)


def ls_remote_head(ssh_url, timeout=20):
    """
    Return {'default_branch', 'head_sha', 'probe_ok'} for a repo via SSH.

    `probe_ok` is True when we got a *definitive* answer from GitHub: either the
    ls-remote succeeded, or it failed in a way that means the repo is genuinely
    absent (e.g. "Repository not found"). It is False on a transient/ambiguous
    failure (network, timeout, auth hiccup) — callers must NOT treat that as an
    absent plane (see compute_status; avoids a false `aligned`).
    Tolerant: returns Nones for the shas on any failure.
    """
    out = {"default_branch": None, "head_sha": None, "probe_ok": False}
    try:
        r = subprocess.run(
            ["git", "ls-remote", "--symref", ssh_url, "HEAD"],
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        if r.returncode != 0:
            err = (r.stderr or "").lower()
            # Definitive "repo absent" answers count as a successful probe.
            out["probe_ok"] = any(h in err for h in _ABSENT_HINTS)
            return out
        out["probe_ok"] = True
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("ref:") and line.endswith("HEAD"):
                # e.g. "ref: refs/heads/main\tHEAD"
                ref = line.split()[1]
                out["default_branch"] = ref.rsplit("/", 1)[-1]
            elif line.endswith("HEAD") and "\t" in line:
                sha = line.split("\t", 1)[0].strip()
                if len(sha) == 40:
                    out["head_sha"] = sha
    except Exception:
        # transient (timeout / exception): probe_ok stays False
        pass
    return out
