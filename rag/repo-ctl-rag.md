# repo-ctl RAG Knowledge Base

> **Repo:** https://github.com/k4rlski/repo-ctl
> **Last updated:** 2026-03-04
> **Status:** 🟡 v0.1.0 skeleton — ready to install on claw

---

## 1. Purpose

Meta-tool: audits and monitors all other k4rlski repos. Checks RAG currency, server sync, open issues, and session notes (latest-work files) across the entire ecosystem in a single sweep.

---

## 2. Commands

```bash
repo-ctl list-repos                             # all repos + issue count + last push
repo-ctl list-issues --target all              # all open issues, all repos
repo-ctl list-issues --target bkup-ctl         # one repo
repo-ctl check-rag --target all               # RAG file health sweep
repo-ctl check-rag --target dns-ctl           # specific repo
repo-ctl check-sync --target bkup-ctl         # GitHub HEAD vs deployed server
repo-ctl check-sync --target all
repo-ctl check-latest-work --target all       # session notes present?
repo-ctl audit --target all                   # FULL SWEEP: RAG + latest-work + issues
repo-ctl audit --target bkup-ctl,job-board-ctl
```

---

## 3. Package Structure

```
src/repo_ctl/
  __init__.py
  main.py            # Click CLI
  github_client.py   # GitHub API v3 client (list repos, issues, tree, file content)
  checks.py          # check_rag(), check_sync(), check_latest_work(), check_open_issues()
config/
  repo-ctl.yml.example
rag/
  repo-ctl-rag.md
```

---

## 4. Checks Detail

### check_rag
- Looks for `rag/{repo}-rag.md` (primary), `docs/{repo}-rag.md` (fallback)
- Reads file content, finds `Last updated: YYYY-MM-DD`
- Warns if older than `rag_stale_days` (default: 14)
- Returns: ok / warn (stale) / fail (missing)

### check_sync
- Gets GitHub HEAD commit SHA via API
- SSHes to server (from SERVER_PATHS dict in checks.py) → `cd {path} && git rev-parse --short HEAD`
- Compares: match = ok, mismatch = warn with both SHAs shown
- SERVER_PATHS covers: bkup-ctl, dns-ctl, site-ctl, job-board-ctl, receipt-ctl, gmail-ctl, snapshot-ctl, swa-ctl, context-ctl

### check_latest_work
- Scans repo file tree for any path containing "latest-work" or "latest_work"
- Extracts date from filename (YYYY-MM-DD or YY-MM-DD pattern)
- Convention: `{tool}-latest-work-YYYY-MM-DD.md` in repo root or rag/

### check_open_issues
- Simple GitHub API issues count
- Shows first 5 issue titles if any open

### audit
- Runs all three checks per repo, derives overall status
- Shows consolidated view: one block per repo

---

## 5. Deployment

**Server:** `claw.auto-ctl.io` (172.236.243.118)
**Path:** `/opt/auto-cmd/repo-ctl/`
**Config:** `/opt/auto-cmd/repo-ctl/config/repo-ctl.yml`

GitHub PAT needed: `ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX` (already on claw — or set `GITHUB_TOKEN` env)

---

## 6. Known Repos Tracked

auto-ctl, bkup-ctl, banner-ctl, code-ctl, context-ctl, dns-ctl, fang-ctl,
gmail-ctl, job-board-ctl, parity-ctl, pwdx-daemon, pwdx-espo, receipt-ctl,
repo-ctl, research-ctl, send-it, site-ctl, site-ctl-daemon, slack-ctl,
snapshot-ctl, swa-ctl, tax-ctl, vendor-ctl

---

## 7. Server Paths (for check-sync)

| Repo | Server | Path |
|------|--------|------|
| bkup-ctl | hiro.datacrypt.org | /opt/bkup-ctl/ |
| dns-ctl | rodan.auto-cmd.io | /opt/auto-cmd/dns-ctl/ |
| site-ctl | sitectl.auto-lamp.io | /opt/site-ctl/ |
| job-board-ctl | sitectl.auto-lamp.io | /opt/job-board-ctl/ |
| receipt-ctl | rodan.auto-cmd.io | /opt/auto-cmd/receipt-ctl/ |
| gmail-ctl | claw.auto-ctl.io | /opt/auto-cmd/gmail-ctl/ |
| snapshot-ctl | rodan.auto-cmd.io | /opt/auto-cmd/snapshot-ctl/ |
| repo-ctl | claw.auto-ctl.io | /opt/auto-cmd/repo-ctl/ |
| swa-ctl | claw.auto-ctl.io | /home/openclaw/dev/swa-ctl/ |
| context-ctl | claw.auto-ctl.io | /opt/context-ctl/ |
