"""CLI entry point: maintain {health,clean,stats,optimize}."""

import json
import sys

import click
from rich.console import Console

from claude_maintain import __version__
from claude_maintain.config import detect_environment

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="maintain")
@click.option("--json", "json_output", is_flag=True, help="Machine-readable JSON output")
@click.pass_context
def cli(ctx: click.Context, json_output: bool) -> None:
    """Claude Code environment maintenance tool."""
    ctx.ensure_object(dict)
    ctx.obj["env"] = detect_environment()
    ctx.obj["json"] = json_output
    ctx.obj["console"] = Console(quiet=json_output)


@cli.command()
@click.option("--generate-clean", is_flag=True, help="Write fixed configs to ~/.claude/reports/")
@click.pass_context
def health(ctx: click.Context, generate_clean: bool) -> None:
    """Check MCP server configurations for issues."""
    from claude_maintain.health import run_health_check

    env = ctx.obj["env"]
    con = ctx.obj["console"]
    result = run_health_check(env, con, generate_clean=generate_clean)
    if ctx.obj["json"]:
        click.echo(json.dumps(result, indent=2, default=str))


@cli.command()
@click.option("--execute", is_flag=True, help="Actually perform cleanup (default is dry run)")
@click.option("--max-age", default=30, help="Stale session age threshold in days")
@click.pass_context
def clean(ctx: click.Context, execute: bool, max_age: int) -> None:
    """Find and clean environment debris."""
    from claude_maintain.clean import run_clean

    env = ctx.obj["env"]
    con = ctx.obj["console"]
    result = run_clean(env, con, execute=execute, max_age_days=max_age)
    if ctx.obj["json"]:
        click.echo(json.dumps(result, indent=2, default=str))


@cli.command()
@click.option("--recent", default=0, type=int, help="Only scan N most recent sessions (0=all)")
@click.option("--no-cache", is_flag=True, help="Ignore cached results")
@click.pass_context
def stats(ctx: click.Context, recent: int, no_cache: bool) -> None:
    """Analyze tool and skill usage from session logs."""
    from claude_maintain.stats import run_stats

    env = ctx.obj["env"]
    con = ctx.obj["console"]
    result = run_stats(env, con, recent_count=recent, use_cache=not no_cache)
    if ctx.obj["json"]:
        click.echo(json.dumps(result, indent=2, default=str))


@cli.command()
@click.pass_context
def optimize(ctx: click.Context) -> None:
    """Run all checks and produce a health score with recommendations."""
    from claude_maintain.optimize import run_optimize

    env = ctx.obj["env"]
    con = ctx.obj["console"]
    result = run_optimize(env, con)
    if ctx.obj["json"]:
        click.echo(json.dumps(result, indent=2, default=str))
