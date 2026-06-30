"""
gh_remote.py - token-free GitHub state via `git ls-remote` over SSH.

Returns the default branch + HEAD sha for a repo without any PAT, using the
existing SSH key. Optional API extras (commit date, pushedAt) are left to the
GitHubClient when a read-only token is configured.
"""

import subprocess


def ls_remote_head(ssh_url, timeout=20):
    """
    Return {'default_branch': str|None, 'head_sha': str|None} for a repo via SSH.
    Tolerant: returns Nones on any failure.
    """
    out = {"default_branch": None, "head_sha": None}
    try:
        r = subprocess.run(
            ["git", "ls-remote", "--symref", ssh_url, "HEAD"],
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        if r.returncode != 0:
            return out
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
        pass
    return out
