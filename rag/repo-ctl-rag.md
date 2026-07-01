# repo-ctl RAG Knowledge Base

> **Repo:** https://github.com/k4rlski/repo-ctl
> **Last updated:** 2026-06-30
> **Status:** 🟢 v0.5 — core-v5 / Server / GitHub alignment tracker (v0.3 metadata/detail-page/refresh + v0.4 name/github_link, Stage/Role, soft-delete, MARS CRUD + v0.5 statprod/tooltype columns, Refresh-all button, live Elasticsearch search)

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

The sweep is **strictly read-only** — no file moves, no fetches, no pushes. It
upserts one row per repo into `infra_ctl.repo_alignment` on dbx and is surfaced on
the MARS page `/tools/repo-ctl`. v0.3 adds per-plane last-commit dates, RAG-file
metadata + GitHub blob link, the MARS tool-page deep-link, a clickable detail
popup, and a single-repo `refresh-alignment` command.

---

## 2. Topology (Option B)

- **Authoritative scan runs on osiris** (the workstation): it is the only box that
  sees `core-v5` *and* can SSH the whole fleet + reach GitHub. It writes to dbx via
  the claw SSH forward (so the connection arrives at dbx as `127.0.0.1`).
- **Canonical code home = rodan `/opt/repo-ctl`.** Develop in `core-v5/repo-ctl`
  (osiris) → sync to rodan → push to GitHub. rodan can reach GitHub + (later) dbx.
- **Option A (future):** grant rodan SSH to the fleet so it owns the Server/Local
  probing directly, retiring the osiris-run dependency ([#3], Phase 6).

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
# Alignment sweep (the main command) — all planes -> dbx
repo-ctl get-state                       # all registry + core-v5 dirs -> dbx
repo-ctl get-state --target repo-ctl,context-ctl,mars-status
repo-ctl get-state --no-db               # scan + print table only (no write)
repo-ctl get-state --no-server           # skip the SSH/server plane (fast, local+GitHub)

# Single-repo re-scan (v0.3) — one-off, friendly alias over get-state
repo-ctl refresh-alignment --slug repo-ctl                 # full re-probe of one repo -> dbx
repo-ctl refresh-alignment --slug repo-ctl --metadata-only # RAG/tool-page/dates only (post-CRUD, no git probe)

# Legacy audit commands (v0.1, API-token based)
repo-ctl list-repos | list-issues | check-rag | check-sync | check-latest-work | audit
```

`--metadata-only` does a targeted UPDATE of just the metadata columns (no
ls-remote, no server SSH) and no-ops if the slug has no row yet — meant to cheaply
re-sync RAG/tool-page links after a CRUD edit. Run on osiris from the repo:
`PYTHONPATH=src python3 -m repo_ctl.main get-state` (or installed entry point
`repo-ctl`). Version **0.4.0**.

---

## 4. Package Structure

```
src/repo_ctl/
  main.py            # Click CLI (get-state, refresh-alignment + legacy audit cmds)
  registry.py        # slug -> {github, server(host,path), local_current}; core-v5 discovery
  gh_remote.py       # token-free GitHub HEAD via `git ls-remote --symref`
  walker.py          # read-only local git state + RAG metadata/blob-link resolution
  ssh_probe.py       # read-only server git state over SSH (single batched probe)
  scan.py            # assemble one repo_alignment row (build_row / build_metadata_row)
  tool_pages.py      # slug -> MARS dashboard page deep-link (mirrors ui-ctl.js nav)
  db.py              # dbx connect + upsert + update_metadata + compute_status
  github_client.py   # GitHub API v3 client (legacy audit cmds; needs a token)
  checks.py          # legacy check_rag/check_sync/check_latest_work/check_open_issues
schema.sql           # repo_alignment base DDL (apply once into infra_ctl)
schema_v3.sql        # v0.3 additive ALTERs (RAG meta, tool-page link, per-plane dates)
config/repo-ctl.yml.example
rag/repo-ctl-rag.md
```

The MARS detail popup (`static/repo-ctl-detail.html`) lives in the **mars-status**
repo, not here (read-only reference for this tool).

---

## 5. Data model — `infra_ctl.repo_alignment`

Keyed by `slug`. Column groups:

- **GitHub:** `gh_default_branch`, `gh_head_sha`, `gh_head_date`, `gh_pushed_at`.
- **Local-final (core-v5):** `lf_path`, `lf_exists`, `lf_is_git`, `lf_branch`,
  `lf_head_sha`, `lf_head_date`, `lf_dirty`, `lf_ahead`, `lf_behind`.
- **Local-current (stray):** `lc_path`, `lc_exists`, `lc_is_git`, `lc_branch`,
  `lc_head_sha`, `lc_head_date`, `lc_dirty`, `lc_ahead`, `lc_behind`.
- **Server:** `server_host`, `server_path`, `srv_exists`, `srv_is_git`,
  `srv_branch`, `srv_head_sha`, `srv_head_date`, `srv_dirty`, `srv_ahead`,
  `srv_behind`.
- **RAG metadata (v0.3):** `rag_name`, `rag_link` (GitHub blob), `rag_last_updated`
  (parsed from the "Last updated:" line), `rag_published_date` (first-commit date),
  `rag_file_mtime` (filesystem mtime).
- **Deep-link (v0.3):** `tool_page_link` (full MARS page URL for the tool).
- **Derived:** `alignment_status` + `notes` (consolidation checklist) + `scanned_at`.

`schema_v3.sql` adds the RAG/tool-page columns plus the three per-plane
`*_head_date` columns; `gh_head_date`/`gh_pushed_at` already existed in
`schema.sql` and are intentionally not re-added. The table lives in the same DB as
`tech_registry`/`tech_relations` (the infra-registry page), so it keys off the same
`slug`.

### Status semantics (`db.compute_status`)

| Status | Meaning |
|--------|---------|
| **aligned** | core-v5 is a git checkout and all present planes agree on HEAD sha (nothing dirty). |
| **drift** | core-v5 is a git checkout but git planes disagree on sha (or a plane is dirty / server path missing). |
| **uncloned** | a folder and/or GitHub repo exists, but `core-v5/<slug>` has **no `.git`** yet — i.e. present in core-v5 but not yet a git checkout. **This is the consolidation to-do.** |
| **absent** | nothing anywhere — no folder on any plane and no GitHub repo. |

`notes` spells out the next action (e.g. "core-v5 folder exists but is NOT a git
checkout — git init/clone here", "stray git clone at … — consolidate into core-v5").

**Current distribution (122 rows):** uncloned **105**, drift **10**, aligned **7**.

---

## 6. MARS page (`/tools/repo-ctl`)

- Served from dbx via `/api/repo/alignment`. Header **cross-links
  `/ops/infra-registry`** and shows infra stats; a **status legend** explains the
  four states.
- **Clickable repo-name** opens a **1570×850 popup** detail page
  (`/static/repo-ctl-detail.html`) for one repo.
- Rows surface **paths on hover**, the per-plane **dates**, and **RAG + tool-page
  links**.
- Per-row **"Refresh (GitHub+meta)"** button → `GET /api/repo/refresh?slug=`. This
  refreshes only the **claw-side GitHub plane + RAG metadata**. The Server and Local
  planes are refreshed by the **osiris scan cron** (a full claw-side Server refresh
  is deferred to Phase 6, [#3]).

---

## 7. Credentials / access

- **GitHub:** TOKEN-FREE for the sweep (`git ls-remote` over the existing SSH key).
  An optional read-only fine-grained PAT in config enables API extras (commit dates,
  pushedAt, issue counts) for the legacy commands.
- **dbx/MySQL:** reuses `perm_ctl` on `infra_ctl` (already has privileges on the
  `*_ctl` DBs). osiris connects over the claw forward (`ssh -L 13307:127.0.0.1:3307
  root@claw.auto-ctl.io`) so MySQL sees `perm_ctl@127.0.0.1`. Creds live in
  `config/repo-ctl.yml` (gitignored) — never committed. rodan's future DIRECT
  connection needs a host grant ([#3], Phase 6).

---

## 8. Deployment

- **Code home (server / source of truth):** rodan, `/opt/repo-ctl` (SSH GitHub
  remote; `venv` with `requests click pyyaml pymysql`).
- **Local dev:** `core-v5/repo-ctl` on osiris.
- **Schema:** apply `schema.sql` then `schema_v3.sql` once into `infra_ctl` (via the
  claw path). v0.3 ALTERs are additive + idempotent (`ADD COLUMN IF NOT EXISTS`).
- **Cadence:** osiris runs the sweep alongside the existing twice-daily ingest cron;
  the MARS page shows `scanned_at`.

---

## 9. Roadmap (filed, not built)

- **ES / search-ctl indexing + finder popup** — [#5].
- **ChromaDB / Hermes alignment feed** — [#6].
- **rodan→fleet SSH + dbx host grant** (Option A; full claw-side Server refresh) —
  [#3], Phase 6.
- **Local plane without osiris** — [#8], deferred; keep osiris as the scan box for now.

---

## 10. Guardrails

Server = source of truth. The sweep is strictly read-only (no moves/pushes/fetches).
Secret audit before committing. rodan hosts many other `/opt/*-ctl` tools — scope all
work to `/opt/repo-ctl` only. No workarounds without review/approval.

---

## 11. v0.4 — name/github_link, Stage/Role, soft-delete, MARS CRUD

### 11.1 Schema v0.4 (additive columns on `infra_ctl.repo_alignment`)

| Column | Type | Source | Meaning |
|--------|------|--------|---------|
| `name` | VARCHAR | scanner-derived | repo display name |
| `github_link` | VARCHAR | scanner-derived | `https://github.com/<repo>` |
| `hidden` | TINYINT DEFAULT 0 | manual (MARS) | soft-delete / archive flag (1 = hidden) |
| `statrepo` | VARCHAR(16) | manual (MARS) | internal **Stage**: `Concept` / `Dev` / `Prod` / `Retired` |
| `rolerepo` | VARCHAR(24) | manual (MARS) | internal **Role**: `AI Admin` / `Biz Admin` / `Infrastructure` / `Operations` |

All additive + idempotent (`ADD COLUMN IF NOT EXISTS`), same convention as
`schema_v3.sql`.

### 11.2 Scanner rules (persistence contract)

- The scanner **fills** `name` + `github_link` on every sweep.
- The scanner **NEVER touches** `hidden` / `statrepo` / `rolerepo` — these are
  **excluded from the upsert column set**, so an archive flag and manual Stage/Role
  reference values **persist across scans**.
- `server_host` / `server_path` use **COALESCE-on-null**: a scan only overwrites them
  when it has a non-null value, so manual edits for **REGISTRY-LESS slugs** (no
  registry entry) survive a sweep. **Registry-defined slugs stay
  registry-authoritative** (the registry value is non-null and wins).

### 11.3 MARS UI (v0.4)

Table columns:
**Name** (→ detail popup) | **Repo** (→ clickable GitHub URL, opens new tab) |
**Status** | **Stage** | **Role** | **GitHub** | **Server** | **Local-final** |
**Local-current** | **Links** | **Notes** | **Action**.

- **Stage** and **Role** columns are **sortable**.
- A **"Show hidden"** toggle reveals soft-deleted (archived) rows.
- **Detail popup** shows clickable: Tool page / Repo / GitHub default-branch
  (`/tree/<branch>`) / RAG / RAG-link / GitHub path. It embeds an
  **"Edit (internal)" CRUD card** (Server host, Server path, Stage, Role) with a
  **Save** action and **Archive / Restore** toggle.

### 11.4 API endpoints (mars-status `routes/repo_bp.py`, live)

| Method + path | Purpose |
|---------------|---------|
| `GET /api/repo/alignment[?include_hidden=1]` | list rows (hidden excluded unless flag) |
| `GET /api/repo/refresh?slug=` | claw-side GitHub + RAG-metadata refresh for one slug |
| `POST /api/repo/update {slug,server_host,server_path,statrepo,rolerepo}` | save manual fields |
| `POST /api/repo/archive {slug,hidden}` | soft-delete / restore |

All endpoints are **auth-gated** (MARS Flask-Login), **parameterized** (no SQL
injection), and **never-500** (defensive error handling). Note: `/api/repo/update`
**intentionally does NOT touch `scanned_at`** — a manual edit is not a scan.

### 11.5 Persistence caveat

v0.4 uses **direct writes** to the manual columns (no separate override columns). A
full **override-columns / DB-driven registry** (manual values in a dedicated layer
that always wins over scanner values, replacing the YAML registry) remains a future
option — [#9].

---

## 12. v0.5 — statprod/tooltype columns, Refresh-all, live Elasticsearch search

### 12.1 Schema v0.5 (additive columns on `infra_ctl.repo_alignment`)

| Column | Type | Source | Meaning |
|--------|------|--------|---------|
| `statprod` | VARCHAR(16) | manual (MARS) | at-a-glance **production/health status** (color dot) |
| `tooltype` | VARCHAR(16) | manual (MARS) | **stack shape** (command-line / web / mobile / etc.) |

Both are **editable, scanner-ignored** — **excluded from the upsert update-set** (same
persistence contract as `hidden`/`statrepo`/`rolerepo`), so they **persist across
scans**. Additive + idempotent (`ADD COLUMN IF NOT EXISTS`), **DB default NULL**.

### 12.2 `statprod` — production/health status

Rendered as a **16×16 color dot in the FIRST table column** and **sortable**:

| Value | Color | Hex |
|-------|-------|-----|
| **Active** | neon green | `#39FF14` |
| **Bug Fix** | bright red | `#FF1A1A` |
| **Pending** | medium orange | `#FF8C00` |
| **Inactive** | medium blue | `#2E7DD1` |
| **Retire** | medium purple | `#9B59B6` |

### 12.3 `tooltype` — stack shape

Column **after Status**, **sortable**. Values: **Command Line**, **Web UI**,
**CLI / Web**, **Mobile UI**, **All**.

### 12.4 MARS UI (v0.5)

- Both `statprod` (dot) and `tooltype` editable in the **detail popup "Edit (internal)"
  card** via `POST /api/repo/update`, which **now validates `statprod`/`tooltype`** too
  (against the allowed value sets above).
- **Notes** cell font reduced to **7px** to keep the wide table readable.
- **Refresh-all (GitHub+meta) button** on `/tools/repo-ctl`: a **client-side sequential
  loop** over the **currently filtered rows** calling `GET /api/repo/refresh?slug=` one
  at a time, with a **progress indicator + Cancel**. Refreshes **GitHub `ls-remote` +
  RAG metadata ONLY** — **NOT** the Local/Server planes (those come from the twice-daily
  **osiris `get-state` scan**, cron `50 7,19`). A true **full 4-plane web-triggered scan**
  + a **rodan server-side refresh** remain deferred ([#11], [#3]).

### 12.5 Elasticsearch search (LIVE)

- **search-ctl** now indexes `infra_ctl.repo_alignment` into the ES index
  **`repo_alignment`** (`search.permtrak.com:9200`) via **`index_repos.py`** on a
  **`15 */6` cron** (search-ctl [#6]).
- MARS surfaces it two ways:
  - **`/adm/search-ctl`** — the ES **test dropdown** includes `repo_alignment`.
  - **`/tools/repo-ctl`** — a **fuzzy ES search box** hitting
    `GET /api/search/test?index=repo_alignment&q=`, with **graceful fallback to the
    client-side filter** if ES is down.

### 12.6 Issue refs

| Issue | Scope |
|-------|-------|
| repo-ctl [#10] | `statprod` / `tooltype` columns + colors + validation |
| repo-ctl [#11] | Refresh-all button (+ deferred full 4-plane / rodan server-refresh) |
| search-ctl [#6] | `index_repos.py` → ES `repo_alignment` index |
| chroma-ctl [#14] | stale 384-dim collections rebuilt to 768-dim |
