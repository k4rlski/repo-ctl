"""repo-ctl CLI — repository audit and sync tool."""

import click
import os
import sys
import yaml
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))
from repo_ctl.github_client import GitHubClient, ALL_REPOS
from repo_ctl import checks as chk

CONFIG_FILE = Path(os.environ.get("REPO_CTL_CONFIG", "/opt/auto-cmd/repo-ctl/config/repo-ctl.yml"))

STATUS_ICON = {"ok": "✅", "warn": "⚠️ ", "fail": "❌"}

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


def make_client(cfg: dict) -> GitHubClient:
    gh = cfg.get("github", {})
    return GitHubClient(token=gh["token"], org=gh.get("org", "k4rlski"))


def resolve_repos(target: str, gh: GitHubClient) -> List[str]:
    if target == "all":
        repos = gh.list_repos()
        return [r["name"] for r in repos]
    return [t.strip() for t in target.split(",")]


@click.group()
@click.version_option(version="0.1.0", prog_name="repo-ctl")
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


if __name__ == "__main__":
    cli()
