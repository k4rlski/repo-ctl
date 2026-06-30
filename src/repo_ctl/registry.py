"""
registry.py - the tool alignment registry for repo-ctl get-state.

Each entry maps a tool `slug` to its planes:
  - github:        the k4rlski repo name (default: slug)
  - server:        (host, path) where it is deployed (source of truth), or None
  - local_current: explicit stray-clone path override, or None (auto-discovered)

Local-final is always core-v5/<slug>. Local-current (stray clones) are
auto-discovered by scanning the known base dirs unless an override is given.

Server host/path are seeded from mars-status TOOL_META + the historic
repo-ctl SERVER_PATHS; extend freely. get-state tolerates missing/unknown
planes (they are reported as missing rather than failing the scan).
"""

import os
from pathlib import Path

# Dropbox roots on osiris
HOME = Path(os.path.expanduser("~")) / "DEVOPS Dropbox" / "DEVOPS-KARL"
CORE_V5 = HOME / "core-v5"

# Base dirs (besides core-v5) where stray "current" local clones may live.
STRAY_BASES = [HOME / "CURSOR", HOME / "AUTO-CTL", HOME]

# slug -> {github, server: (host, path), local_current: <override path or None>}
# Focused first on the AI-context tooling + repo-ctl + mars-status; extend over time.
REGISTRY = {
    "repo-ctl":          {"server": ("rodan.auto-cmd.io", "/opt/repo-ctl")},
    "context-ctl":       {"server": ("claw.auto-ctl.io", "/opt/context-ctl")},
    "chroma-ctl":        {"server": ("claw.auto-ctl.io", "/opt/context-ctl")},   # shares /opt/context-ctl
    "plan-ctl":          {"server": ("claw.auto-ctl.io", "/opt/plan-ctl"),
                          "local_current": str(HOME / "CURSOR" / "Plan-CTL")},
    "cursor-export-ctl": {"server": ("claw.auto-ctl.io", "/opt/cursor-export-ctl"),
                          "local_current": str(HOME / "CURSOR" / "cursor-export-ctl")},
    "rag-ctl":           {"server": ("claw.auto-ctl.io", "/opt/rag-ctl")},
    "hermes-ctl":        {"server": ("hermes.auto-ctl.io", "/home/hermes"),
                          "ssh_user": "hermes"},
    "mars-status":       {"server": ("claw.auto-ctl.io", "/opt/mars-status"),
                          "local_current": str(HOME / "MARS-STATUS")},
    "stripe-ctl":        {"server": None},
}

# Historic ecosystem server paths (used if a slug lacks an explicit server entry).
SERVER_PATHS = {
    "bkup-ctl":       ("hiro.datacrypt.org",   "/opt/bkup-ctl"),
    "dns-ctl":        ("rodan.auto-cmd.io",     "/opt/auto-cmd/dns-ctl"),
    "site-ctl":       ("sitectl.auto-lamp.io",  "/opt/site-ctl"),
    "job-board-ctl":  ("sitectl.auto-lamp.io",  "/opt/job-board-ctl"),
    "receipt-ctl":    ("rodan.auto-cmd.io",     "/opt/auto-cmd/receipt-ctl"),
    "snapshot-ctl":   ("rodan.auto-cmd.io",     "/opt/auto-cmd/snapshot-ctl"),
}


def _discover_stray(slug):
    """Find a stray 'current' local clone for slug by scanning STRAY_BASES (case-insensitive)."""
    want = slug.lower().replace("_", "-")
    for base in STRAY_BASES:
        if not base.is_dir():
            continue
        try:
            for child in base.iterdir():
                if not child.is_dir():
                    continue
                name = child.name.lower().replace("_", "-")
                if name == want:
                    return str(child)
        except OSError:
            continue
    return None


def resolve(slug):
    """Return the resolved plane coordinates for a slug."""
    entry = REGISTRY.get(slug, {})
    server = entry.get("server", SERVER_PATHS.get(slug))
    local_current = entry.get("local_current") or _discover_stray(slug)
    return {
        "slug": slug,
        "repo": entry.get("github", slug),
        "github_ssh": f"git@github.com:k4rlski/{entry.get('github', slug)}.git",
        "local_final": str(CORE_V5 / slug),
        "local_current": local_current,
        "server_host": server[0] if server else None,
        "server_path": server[1] if server else None,
        "ssh_user": entry.get("ssh_user", "root"),
    }


def core_v5_slugs():
    """All tool dirs present under core-v5 (so get-state can scan the real HQ)."""
    out = []
    if CORE_V5.is_dir():
        for child in sorted(CORE_V5.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                out.append(child.name)
    return out


def default_targets():
    """Union of registry slugs and what is actually present under core-v5."""
    return sorted(set(REGISTRY.keys()) | set(core_v5_slugs()))
