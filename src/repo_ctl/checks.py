"""
Audit checks for repo-ctl.

Each check returns a dict:
  { "status": "ok"|"warn"|"fail", "message": str, "detail": str|None }
"""

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional
from .github_client import GitHubClient

# All known repos in the ecosystem
ALL_REPOS = [
    "bkup-ctl", "dns-ctl", "site-ctl", "site-ctl-daemon",
    "job-board-ctl", "receipt-ctl", "gmail-ctl", "snapshot-ctl",
    "repo-ctl", "swa-ctl", "pwdx-daemon", "pwdx-espo",
    "context-ctl", "code-ctl", "slack-ctl", "fang-ctl",
    "banner-ctl", "auto-ctl", "send-it", "vendor-ctl",
    "tax-ctl", "research-ctl", "parity-ctl",
]

# Where each tool lives on a server (source of truth)
SERVER_PATHS = {
    "bkup-ctl":         ("hiro.datacrypt.org",    "/opt/bkup-ctl/"),
    "dns-ctl":          ("rodan.auto-cmd.io",      "/opt/auto-cmd/dns-ctl/"),
    "site-ctl":         ("sitectl.auto-lamp.io",   "/opt/site-ctl/"),
    "site-ctl-daemon":  ("sitectl.auto-lamp.io",   "/opt/site-ctl/"),
    "job-board-ctl":    ("sitectl.auto-lamp.io",   "/opt/job-board-ctl/"),
    "receipt-ctl":      ("rodan.auto-cmd.io",      "/opt/auto-cmd/receipt-ctl/"),
    "gmail-ctl":        ("claw.auto-ctl.io",       "/opt/auto-cmd/gmail-ctl/"),
    "snapshot-ctl":     ("rodan.auto-cmd.io",      "/opt/auto-cmd/snapshot-ctl/"),
    "repo-ctl":         ("claw.auto-ctl.io",       "/opt/auto-cmd/repo-ctl/"),
    "swa-ctl":          ("claw.auto-ctl.io",       "/home/openclaw/dev/swa-ctl/"),
    "context-ctl":      ("claw.auto-ctl.io",       "/opt/context-ctl/"),
    "banner-ctl":       ("claw.auto-ctl.io",       "/opt/auto-cmd/banner-ctl/"),
}

# Expected RAG file paths in each repo
RAG_PATHS = {
    "bkup-ctl":      "docs/bkup-ctl-rag.md",   # legacy location
    "dns-ctl":       "rag/dns-ctl-rag.md",
    "job-board-ctl": "rag/job-board-ctl-rag.md",
    "receipt-ctl":   "rag/receipt-ctl-rag.md",
    "gmail-ctl":     "rag/gmail-ctl-rag.md",
    "snapshot-ctl":  "rag/snapshot-ctl-rag.md",
    "repo-ctl":      "rag/repo-ctl-rag.md",
    "site-ctl":      "rag/site-ctl-rag.md",
    "swa-ctl":       "rag/swa-ctl-rag.md",
    "bkup-ctl":      "rag/bkup-ctl-rag.md",
}

# Max age (days) before RAG is considered stale
RAG_STALE_DAYS = 14


def check_rag(gh: GitHubClient, repo: str) -> dict:
    """Check if a RAG file exists in the repo and how fresh it is."""
    # Try rag/ folder first, then docs/ fallback
    candidates = [
        f"rag/{repo}-rag.md",
        f"docs/{repo}-rag.md",
        f"rag/{repo.replace('-','_')}-rag.md",
    ]
    tree = gh.get_tree(repo)
    tree_paths = {item["path"] for item in tree}

    found_path = None
    for c in candidates:
        if c in tree_paths:
            found_path = c
            break

    if not found_path:
        # Also check for any *-rag.md anywhere
        rag_files = [p for p in tree_paths if p.endswith("-rag.md") or p.endswith("_rag.md")]
        if rag_files:
            found_path = rag_files[0]

    if not found_path:
        return {"status": "fail", "message": "No RAG file found", "detail": f"Expected: rag/{repo}-rag.md"}

    # Check for "Last updated" date in content
    content = gh.get_file_content(repo, found_path)
    stale_detail = None
    if content:
        m = re.search(r"Last updated[:\s]+(\d{4}-\d{2}-\d{2})", content, re.IGNORECASE)
        if m:
            rag_date = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - rag_date).days
            if age_days > RAG_STALE_DAYS:
                stale_detail = f"RAG is {age_days} days old (>{RAG_STALE_DAYS}d threshold)"
                return {"status": "warn", "message": f"RAG exists but stale ({age_days}d)", "detail": stale_detail}

    return {"status": "ok", "message": f"RAG OK ({found_path})", "detail": None}


def check_latest_work(gh: GitHubClient, repo: str) -> dict:
    """Check if a latest-work file exists and how recent."""
    tree = gh.get_tree(repo)
    tree_paths = [item["path"] for item in tree]

    lw_files = [p for p in tree_paths
                if "latest-work" in p.lower() or "latest_work" in p.lower()]

    if not lw_files:
        return {"status": "warn", "message": "No latest-work file", "detail": "Convention: {tool}-latest-work-YYYY-MM-DD.md in repo root or rag/"}

    # Find most recent by date in filename
    dates = []
    for f in lw_files:
        m = re.search(r"(\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{2})", f)
        if m:
            dates.append((m.group(1), f))
    if dates:
        dates.sort(reverse=True)
        newest_date, newest_file = dates[0]
        return {"status": "ok", "message": f"Latest-work: {newest_file}", "detail": None}

    return {"status": "ok", "message": f"Latest-work files: {', '.join(lw_files)}", "detail": None}


def check_open_issues(gh: GitHubClient, repo: str) -> dict:
    """Count open issues."""
    try:
        issues = gh.list_issues(repo, state="open")
        count = len(issues)
        if count == 0:
            return {"status": "ok", "message": "No open issues", "detail": None}
        titles = [f"#{i['number']}: {i['title'][:60]}" for i in issues[:5]]
        return {
            "status": "warn" if count > 0 else "ok",
            "message": f"{count} open issue(s)",
            "detail": "\n  ".join(titles) + ("..." if count > 5 else ""),
        }
    except Exception as e:
        return {"status": "warn", "message": f"Could not fetch issues: {e}", "detail": None}


def check_sync(gh: GitHubClient, repo: str, ssh_user: str = "root") -> dict:
    """
    Check if GitHub HEAD commit matches what's deployed on the server.
    Requires SSH access from claw to the target server.
    """
    import subprocess

    if repo not in SERVER_PATHS:
        return {"status": "warn", "message": "No server path configured for this repo", "detail": None}

    server, path = SERVER_PATHS[repo]

    # Get GitHub HEAD commit
    try:
        commits = gh.get_commits(repo, count=1)
        if not commits:
            return {"status": "warn", "message": "Could not fetch GitHub commits", "detail": None}
        github_sha = commits[0]["sha"][:7]
        github_msg = commits[0]["commit"]["message"].split("\n")[0][:60]
    except Exception as e:
        return {"status": "fail", "message": f"GitHub API error: {e}", "detail": None}

    # Get deployed commit via SSH
    try:
        result = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
             f"{ssh_user}@{server}", f"cd {path} && git rev-parse --short HEAD 2>/dev/null || echo NOT_GIT"],
            capture_output=True, text=True, timeout=10
        )
        deployed_sha = result.stdout.strip()
    except Exception as e:
        return {"status": "warn", "message": f"SSH check failed: {e}", "detail": f"{server}:{path}"}

    if deployed_sha == "NOT_GIT":
        return {"status": "warn", "message": "Deployed path is not a git repo", "detail": f"{server}:{path}"}

    if not deployed_sha:
        return {"status": "warn", "message": "Could not read deployed commit", "detail": f"{server}:{path}"}

    if deployed_sha == github_sha:
        return {"status": "ok", "message": f"In sync ({github_sha}) — {server}", "detail": None}
    else:
        return {
            "status": "warn",
            "message": f"OUT OF SYNC — GitHub: {github_sha}, Server: {deployed_sha}",
            "detail": f"{server}:{path}\nLatest GitHub commit: {github_msg}",
        }
