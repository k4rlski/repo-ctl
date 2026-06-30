# repo-ctl RAG Knowledge Base

> **Repo:** https://github.com/k4rlski/repo-ctl
> **Last updated:** 2026-06-30
> **Status:** 🟢 v0.2 — core-v5 / Server / GitHub alignment tracker (`get-state` live)

---

## 1. Purpose

repo-ctl is the **alignment tracker** for the auto-ctl ecosystem as code is
consolidated into the `core-v5/` local HQ. It answers, for every tool, "where does
this repo actually sit?" across four planes:

| Plane | Meaning | Source |
|-------|---------|--------|
| **GitHub** | the canonical archive | `git ls-remote` (token-free, over SSH) |
| **Local-final** | `core-v5/<slug>` (the target HQ on osiris) | local git probe |
| **Local-current** | stray clone (`CURSOR/*`, `AUTO-CTL/*`, top-level) | local git probe |
| **Server** | source of truth (deployed) | `git` over SSH |

`get-state` is **strictly read-only** — no file moves, no fetches, no pushes. It
upserts one row per repo into `infra_ctl.repo_alignment` on dbx and is surfaced on
the MARS page `/tools/repo-ctl`.

---

## 2. Topology (Option B)

- **Authoritative scan runs on osiris** (the workstation): it is the only box that
  sees `core-v5` *and* can SSH the whole fleet + reach GitHub. It writes to dbx via
  the claw SSH forward (so the connection arrives at dbx as `127.0.0.1`).
- **Canonical code home = rodan `/opt/repo-ctl`.** Develop in `core-v5/repo-ctl`
  (osiris) → sync to rodan → push to GitHub. rodan can reach GitHub + (later) dbx.
- **Option A (future):** grant rodan SSH to the fleet so it owns the Server/Local
  probing directly, retiring the osiris-run dependency (tracked as a repo-ctl issue).

```
osiris  get-state ──ls-remote──▶ GitHub
        │  │  └─ssh git probe──▶ claw/sitectl/hiro/rodan/...
        │  └────walk───────────▶ core-v5/* + stray locals
        └────ssh -L via claw───▶ infra_ctl.repo_alignment (dbx)
MARS /tools/repo-ctl ──/api/repo/alignment──▶ dbx
```

---

## 3. Commands

```bash
# Alignment sweep (v0.2 — the main command)
repo-ctl get-state                       # all registry + core-v5 dirs -> dbx
repo-ctl get-state --target repo-ctl,context-ctl,mars-status
repo-ctl get-state --no-db               # scan + print table only (no write)
repo-ctl get-state --no-server           # skip the SSH/server plane (fast, local+GitHub)

# Legacy audit commands (v0.1, API-token based)
repo-ctl list-repos | list-issues | check-rag | check-sync | check-latest-work | audit
```

Run on osiris from the repo: `PYTHONPATH=src python3 -m repo_ctl.main get-state`
(or installed entry point `repo-ctl`).

---

## 4. Package Structure

```
src/repo_ctl/
  main.py            # Click CLI (get-state + legacy audit cmds)
  registry.py        # slug -> {github, server(host,path), local_current}; core-v5 discovery
  gh_remote.py       # token-free GitHub HEAD via `git ls-remote --symref`
  walker.py          # read-only local git state (branch/HEAD/dirty/ahead-behind)
  ssh_probe.py       # read-only server git state over SSH (single batched probe)
  scan.py            # assemble one repo_alignment row across all 4 planes
  db.py              # dbx connect (claw tunnel or direct) + upsert + compute_status
  github_client.py   # GitHub API v3 client (legacy audit cmds; needs a token)
  checks.py          # legacy check_rag/check_sync/check_latest_work/check_open_issues
schema.sql           # repo_alignment DDL (apply once into infra_ctl)
config/repo-ctl.yml.example
rag/repo-ctl-rag.md
```

---

## 5. Data model — `infra_ctl.repo_alignment`

Keyed by `slug`. Column groups: GitHub (`gh_*`), Local-final (`lf_*`),
Local-current (`lc_*`), Server (`srv_*` + `server_host`/`server_path`), and derived
`alignment_status` (`aligned|drift|missing|stale|unknown`) + `notes` + `scanned_at`.
Lives in the same DB as `tech_registry`/`tech_relations` (the infra-registry page),
so it keys off the same `slug`.

`alignment_status` logic (in `db.compute_status`):
- **aligned** — all present HEAD shas equal and nothing dirty.
- **drift** — shas differ or any plane is dirty (notes say which).
- **missing** — no core-v5 git home, or a configured server path is absent/not-git.

---

## 6. Credentials / access

- **GitHub:** TOKEN-FREE for `get-state` (`git ls-remote` over the existing SSH key).
  An optional read-only fine-grained PAT in config enables API extras (commit dates,
  pushedAt, issue counts) for the legacy commands.
- **dbx/MySQL:** reuses `perm_ctl` on `infra_ctl` (already has privileges on the
  `*_ctl` DBs). osiris connects over the claw forward (`ssh -L 13307:127.0.0.1:3307
  root@claw.auto-ctl.io`) so MySQL sees `perm_ctl@127.0.0.1`. Creds live in
  `config/repo-ctl.yml` (gitignored) — never committed. rodan's future DIRECT
  connection needs a host grant (Option A).

---

## 7. Deployment

- **Code home (server / source of truth):** rodan, `/opt/repo-ctl` (SSH GitHub remote;
  `venv` with `requests click pyyaml pymysql`).
- **Local dev:** `core-v5/repo-ctl` on osiris.
- **Schema:** apply `schema.sql` once into `infra_ctl` (via the claw path).
- **Cadence:** osiris runs `get-state` alongside the existing twice-daily ingest cron;
  the MARS page shows `scanned_at`.

---

## 8. Guardrails

Server = source of truth. `get-state` is strictly read-only (no moves/pushes/fetches).
Secret audit before committing. rodan hosts many other `/opt/*-ctl` tools — scope all
work to `/opt/repo-ctl` only. No workarounds without review/approval.
