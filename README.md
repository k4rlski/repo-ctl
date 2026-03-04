# repo-ctl

> Repository audit and sync tool — RAG currency, issue tracking, server sync checks across all k4rlski repos.

## Commands

```bash
# List all repos
repo-ctl list-repos

# List open issues (all repos or specific)
repo-ctl list-issues --target all
repo-ctl list-issues --target bkup-ctl
repo-ctl list-issues --target bkup-ctl,job-board-ctl

# Check RAG file health
repo-ctl check-rag --target all         # all repos
repo-ctl check-rag --target dns-ctl     # specific

# Check server sync (GitHub HEAD vs deployed commit)
repo-ctl check-sync --target bkup-ctl
repo-ctl check-sync --target all

# Check latest-work session notes
repo-ctl check-latest-work --target all

# Full audit (RAG + latest-work + issues in one sweep)
repo-ctl audit --target all
repo-ctl audit --target bkup-ctl,job-board-ctl,receipt-ctl
```

## What It Checks

| Check | Command | What it catches |
|-------|---------|----------------|
| `check-rag` | `check-rag` | Missing RAG files, stale RAG (>14 days) |
| `check-sync` | `check-sync` | GitHub HEAD ≠ deployed server commit (drift) |
| `check-latest-work` | `check-latest-work` | No session notes file in repo |
| Issues | `list-issues` | Open GitHub issues across all tools |
| Full sweep | `audit` | All of the above in one pass |

## Deployment

**Lives on:** `claw.auto-ctl.io`
**Install path:** `/opt/auto-cmd/repo-ctl/`

```bash
git clone git@github.com:k4rlski/repo-ctl.git /opt/auto-cmd/repo-ctl
cd /opt/auto-cmd/repo-ctl
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config/repo-ctl.yml.example config/repo-ctl.yml
# Edit config: add GitHub PAT
```

## Config

```yaml
github:
  token: "ghp_..."
  org: k4rlski
rag_stale_days: 14
ssh_user: root
```

Or set `GITHUB_TOKEN` env var — no config file needed.
