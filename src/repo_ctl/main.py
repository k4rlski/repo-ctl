"""repo-ctl CLI — repository audit and sync tool."""

import click
import os
import sys
import yaml
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))
from repo_ctl.github_client import GitHubClient
from repo_ctl import checks as chk
from repo_ctl import registry as reg
from repo_ctl import scan as scanmod
from repo_ctl import db as dbmod


def _default_config_path() -> Path:
    """Search REPO_CTL_CONFIG, the rodan deploy path, then the repo-local config."""
    env = os.environ.get("REPO_CTL_CONFIG")
    if env:
        return Path(env)
    for cand in (
        Path("/opt/repo-ctl/config/repo-ctl.yml"),
        Path(__file__).resolve().parents[2] / "config" / "repo-ctl.yml",
    ):
        if cand.exists():
            return cand
    return Path("/opt/repo-ctl/config/repo-ctl.yml")


CONFIG_FILE = _default_config_path()

STATUS_ICON = {"ok": "✅", "warn": "⚠️ ", "fail": "❌"}
ALIGN_ICON = {"aligned": "✅", "drift": "⚠️ ", "uncloned": "📥", "absent": "⛔",
              "missing": "❌", "unknown": "❔", "stale": "⚠️ "}


def load_config(path: str = None) -> dict:
    p = Path(path) if path else CONFIG_FILE
    if p.exists():
        with open(p) as f:
            return yaml.safe_load(f) or {}
    # Fallback: env var
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("REPO_CTL_GITHUB_TOKEN")
    if token:
        return {"github": {"token": token, "org": "k4rlski"}}
    raise click.ClickException(f"Config not found at {p} and GITHUB_TOKEN env not set")


def load_config_soft(path: str = None) -> dict:
    """Like load_config but returns {} instead of raising (for token-free commands)."""
    p = Path(path) if path else CONFIG_FILE
    if p.exists():
        with open(p) as f:
            return yaml.safe_load(f) or {}
    return {}


def _sha(s):
    return s[:7] if s else "-"


def make_client(cfg: dict) -> GitHubClient:
    gh = cfg.get("github", {})
    return GitHubClient(token=gh["token"], org=gh.get("org", "k4rlski"))


def resolve_repos(target: str, gh: GitHubClient) -> List[str]:
    if target == "all":
        repos = gh.list_repos()
        return [r["name"] for r in repos]
    return [t.strip() for t in target.split(",")]


@click.group()
@click.version_option(version="0.6.0", prog_name="repo-ctl")
@click.option("--config", "-c", default=None, help="Config file path")
@click.pass_context
def cli(ctx, config):
    """repo-ctl — Repository audit, sync, and RAG currency checks for the auto-ctl ecosystem."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


@cli.command("list-repos")
@click.option("--verbose", "-v", is_flag=True)
@click.pass_obj
def list_repos(obj, verbose):
    """List all GitHub repositories."""
    cfg = load_config(obj.get("config_path"))
    gh = make_client(cfg)
    repos = gh.list_repos()
    repos.sort(key=lambda r: r["name"])
    click.echo(f"\n{'Repo':<35} {'Open Issues':>12} {'Last Push'}")
    click.echo("-" * 65)
    for r in repos:
        pushed = r.get("pushed_at", "")[:10] if r.get("pushed_at") else "—"
        issues = r.get("open_issues_count", 0)
        flag = " ⚠️" if issues > 0 else ""
        click.echo(f"{r['name']:<35} {issues:>12}{flag}  {pushed}")
    click.echo(f"\nTotal: {len(repos)} repos")


@cli.command("list-issues")
@click.option("--target", default="all", show_default=True, help="Repo name or 'all'")
@click.option("--state", default="open", show_default=True, help="open|closed|all")
@click.pass_obj
def list_issues(obj, target, state):
    """List GitHub issues across repos."""
    cfg = load_config(obj.get("config_path"))
    gh = make_client(cfg)
    repos = resolve_repos(target, gh)

    total = 0
    for repo in repos:
        try:
            issues = gh.list_issues(repo, state=state)
            if not issues:
                continue
            click.echo(f"\n── {repo} ({len(issues)} {state}) ──")
            for i in issues:
                labels = ", ".join(l["name"] for l in i.get("labels", []))
                label_str = f" [{labels}]" if labels else ""
                click.echo(f"  #{i['number']}: {i['title']}{label_str}")
            total += len(issues)
        except Exception as e:
            click.echo(f"  {repo}: error — {e}")
    click.echo(f"\nTotal {state} issues: {total}")


@cli.command("check-rag")
@click.option("--target", default="all", show_default=True, help="Repo name or 'all'")
@click.pass_obj
def check_rag(obj, target):
    """Check RAG file existence and freshness across repos."""
    cfg = load_config(obj.get("config_path"))
    gh = make_client(cfg)
    repos = resolve_repos(target, gh)

    click.echo(f"\n{'Repo':<30} {'Status':<8} Message")
    click.echo("-" * 75)
    ok = warn = fail = 0
    for repo in repos:
        result = chk.check_rag(gh, repo)
        icon = STATUS_ICON[result["status"]]
        click.echo(f"{repo:<30} {icon}  {result['message']}")
        if result.get("detail"):
            click.echo(f"  {'':30}   → {result['detail']}")
        if result["status"] == "ok": ok += 1
        elif result["status"] == "warn": warn += 1
        else: fail += 1

    click.echo(f"\n✅ {ok}  ⚠️  {warn}  ❌ {fail}")


@cli.command("check-sync")
@click.option("--target", required=True, help="Repo name or 'all'")
@click.option("--ssh-user", default="root", show_default=True)
@click.pass_obj
def check_sync(obj, target, ssh_user):
    """Check if GitHub HEAD matches deployed server version."""
    cfg = load_config(obj.get("config_path"))
    gh = make_client(cfg)
    repos = resolve_repos(target, gh)

    click.echo(f"\n{'Repo':<28} {'Status':<8} Message")
    click.echo("-" * 75)
    for repo in repos:
        result = chk.check_sync(gh, repo, ssh_user=ssh_user)
        icon = STATUS_ICON[result["status"]]
        click.echo(f"{repo:<28} {icon}  {result['message']}")
        if result.get("detail"):
            for line in result["detail"].split("\n"):
                click.echo(f"  {'':28}   → {line}")


@cli.command("check-latest-work")
@click.option("--target", default="all", show_default=True, help="Repo name or 'all'")
@click.pass_obj
def check_latest_work(obj, target):
    """Check for latest-work session notes files across repos."""
    cfg = load_config(obj.get("config_path"))
    gh = make_client(cfg)
    repos = resolve_repos(target, gh)

    click.echo(f"\n{'Repo':<30} {'Status':<8} Message")
    click.echo("-" * 75)
    ok = warn = 0
    for repo in repos:
        result = chk.check_latest_work(gh, repo)
        icon = STATUS_ICON[result["status"]]
        click.echo(f"{repo:<30} {icon}  {result['message']}")
        if result["status"] == "ok": ok += 1
        else: warn += 1
    click.echo(f"\n✅ {ok}  ⚠️  {warn}")


@cli.command("audit")
@click.option("--target", default="all", show_default=True, help="Repo name or 'all'")
@click.pass_obj
def audit(obj, target):
    """Full audit: RAG + latest-work + open issues for each repo."""
    cfg = load_config(obj.get("config_path"))
    gh = make_client(cfg)
    repos = resolve_repos(target, gh)

    click.echo(f"\n{'':=<75}")
    click.echo(f"  repo-ctl audit — {len(repos)} repos")
    click.echo(f"{'':=<75}")

    for repo in repos:
        rag = chk.check_rag(gh, repo)
        lw = chk.check_latest_work(gh, repo)
        issues = chk.check_open_issues(gh, repo)

        overall = "ok"
        for r in [rag, lw, issues]:
            if r["status"] == "fail": overall = "fail"
            elif r["status"] == "warn" and overall != "fail": overall = "warn"

        click.echo(f"\n{STATUS_ICON[overall]} {repo}")
        click.echo(f"   RAG:          {STATUS_ICON[rag['status']]}  {rag['message']}")
        click.echo(f"   Latest-work:  {STATUS_ICON[lw['status']]}  {lw['message']}")
        click.echo(f"   Issues:       {STATUS_ICON[issues['status']]}  {issues['message']}")
        if issues.get("detail"):
            for line in issues["detail"].split("\n"):
                click.echo(f"                   {line}")

    click.echo(f"\n{'':=<75}")


@cli.command("get-state")
@click.option("--target", default="all", show_default=True,
              help="Comma-separated slugs, or 'all' (registry + core-v5 dirs)")
@click.option("--no-db", is_flag=True, help="Scan + print only; do not write to dbx")
@click.option("--no-server", is_flag=True, help="Skip the server (SSH) plane")
@click.pass_obj
def get_state(obj, target, no_db, no_server):
    """Read-only alignment sweep: core-v5 / Local-current / Server / GitHub -> dbx."""
    if target == "all":
        slugs = reg.default_targets()
    else:
        slugs = [t.strip() for t in target.split(",") if t.strip()]

    rows = []
    click.echo(f"\n{'SLUG':<20} {'STATUS':<9} {'GITHUB':<8} {'SERVER':<22} {'CORE-V5':<12} {'CURRENT'}")
    click.echo("-" * 90)
    for slug in slugs:
        row = scanmod.build_row(slug, skip_server=no_server)
        rows.append(row)

        icon = ALIGN_ICON.get(row["alignment_status"], "?")
        srv = "-"
        if row["server_host"]:
            host = row["server_host"].split(".")[0]
            ssha = _sha(row["srv_head_sha"])
            dd = f"*{row['srv_dirty']}" if (row.get("srv_dirty") or 0) else ""
            srv = f"{host} {ssha}{dd}" if row["srv_is_git"] else f"{host} (none)"
        lf = _sha(row["lf_head_sha"]) + (f"*{row['lf_dirty']}" if (row.get("lf_dirty") or 0) else "")
        if not row["lf_is_git"]:
            lf = "(none)"
        lc = _sha(row["lc_head_sha"]) if row["lc_is_git"] else "-"
        click.echo(f"{slug:<20} {icon} {row['alignment_status']:<7} {_sha(row['gh_head_sha']):<8} "
                   f"{srv:<22} {lf:<12} {lc}")

    from collections import Counter
    dist = Counter(r["alignment_status"] for r in rows)
    summary = "  ".join(f"{k} {dist[k]}" for k in sorted(dist))
    click.echo(f"\n{len(rows)} repos | {summary}")

    if no_db:
        click.echo("(--no-db: not written to dbx)")
        return

    cfg = load_config_soft(obj.get("config_path"))
    dbx = cfg.get("dbx")
    if not dbx:
        raise click.ClickException(
            "No [dbx] config found; cannot persist. Use --no-db, or add a dbx: section "
            f"to {CONFIG_FILE}")
    try:
        with dbmod.connect(dbx) as conn:
            for r in rows:
                dbmod.upsert(conn, r)
        click.echo(f"Wrote {len(rows)} rows to infra_ctl.repo_alignment")
    except Exception as e:
        raise click.ClickException(f"DB write failed: {e}")


@cli.command("refresh-alignment")
@click.option("--slug", required=True, help="Single tool slug to re-scan")
@click.option("--metadata-only", is_flag=True,
              help="Refresh only RAG/tool-page/date metadata (no git re-probe)")
@click.option("--no-server", is_flag=True, help="Skip the server (SSH) plane")
@click.option("--no-db", is_flag=True, help="Scan + print only; do not write to dbx")
@click.pass_obj
def refresh_alignment(obj, slug, metadata_only, no_server, no_db):
    """One-off single-repo alignment re-scan -> dbx (friendly alias over get-state)."""
    if metadata_only:
        row = scanmod.build_metadata_row(slug)
        click.echo(f"\n{slug} (metadata-only)")
        click.echo(f"  rag_name:           {row.get('rag_name')}")
        click.echo(f"  rag_link:           {row.get('rag_link')}")
        click.echo(f"  rag_last_updated:   {row.get('rag_last_updated')}")
        click.echo(f"  rag_published_date: {row.get('rag_published_date')}")
        click.echo(f"  rag_file_mtime:     {row.get('rag_file_mtime')}")
        click.echo(f"  tool_page_link:     {row.get('tool_page_link')}")
    else:
        row = scanmod.build_row(slug, skip_server=no_server)
        icon = ALIGN_ICON.get(row["alignment_status"], "?")
        click.echo(f"\n{slug}: {icon} {row['alignment_status']}  "
                   f"gh={_sha(row['gh_head_sha'])} "
                   f"core-v5={_sha(row['lf_head_sha'])} "
                   f"srv={_sha(row['srv_head_sha'])}")
        if row.get("notes"):
            click.echo(f"  notes: {row['notes']}")
        click.echo(f"  tool_page_link: {row.get('tool_page_link')}")
        click.echo(f"  rag_link:       {row.get('rag_link')}")

    if no_db:
        click.echo("(--no-db: not written to dbx)")
        return

    cfg = load_config_soft(obj.get("config_path"))
    dbx = cfg.get("dbx")
    if not dbx:
        raise click.ClickException(
            "No [dbx] config found; cannot persist. Use --no-db, or add a dbx: section "
            f"to {CONFIG_FILE}")
    try:
        with dbmod.connect(dbx) as conn:
            if metadata_only:
                n = dbmod.update_metadata(conn, row)
                if n:
                    click.echo(f"Updated metadata for {slug} (1 row)")
                else:
                    click.echo(f"No existing row for {slug}; run a full get-state first")
            else:
                dbmod.upsert(conn, row)
                click.echo(f"Upserted {slug} into infra_ctl.repo_alignment")
    except Exception as e:
        raise click.ClickException(f"DB write failed: {e}")


@cli.command("clone-local")
@click.option("--host", default=None,
              help="Target host queue to poll (default: this machine's short "
                   "hostname; e.g. osiris|ares|raven)")
@click.pass_obj
def clone_local(obj, host):
    """Pull-agent: claim + process ONE pending clone job for this host -> core-v5."""
    from repo_ctl import clone as clonemod
    host = (host or clonemod.short_host()).lower()

    cfg = load_config_soft(obj.get("config_path"))
    if not cfg.get("dbx"):
        raise click.ClickException(
            "No [dbx] config found; cannot poll clone jobs. Add a dbx: section "
            f"to {CONFIG_FILE}")

    try:
        res = clonemod.run_poller(cfg, host)
    except Exception as e:
        raise click.ClickException(f"clone poll failed: {e}")

    action = res.get("action")
    if action == "noop":
        click.echo(f"clone-local [{host}]: no pending jobs")
        return
    if action == "error":
        raise click.ClickException(res.get("message", "clone poll error"))

    slug = res.get("slug", "?")
    icon = {"success": "✅", "skipped": "⏭️ ", "failed": "❌"}.get(action, "•")
    click.echo(f"clone-local [{host}]: {icon} {slug} -> {action} — "
               f"{res.get('message', '')}")
    if not res.get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    cli()
