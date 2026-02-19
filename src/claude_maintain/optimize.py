"""Health score calculation and recommendations."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from claude_maintain.config import Environment
from claude_maintain.health import run_health_check
from claude_maintain.clean import run_clean
from claude_maintain.stats import run_stats
from claude_maintain.report import format_bytes, print_score_bar, save_report, severity_color


@dataclass
class Recommendation:
    """A single actionable recommendation."""

    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    category: str
    message: str
    impact: str = ""
    command: str = ""


@dataclass
class ScoreBreakdown:
    """Weighted score breakdown by category."""

    mcp: int = 0         # max 25
    storage: int = 0     # max 20
    skills: int = 0      # max 20
    plugins: int = 0     # max 15
    sync: int = 0        # max 10
    naming: int = 0      # max 10

    @property
    def total(self) -> int:
        return self.mcp + self.storage + self.skills + self.plugins + self.sync + self.naming


def calculate_mcp_score(health_result: dict) -> tuple[int, list[Recommendation]]:
    """Score MCP health (0-25)."""
    recs = []
    total_servers = health_result["cli_servers"] + health_result["desktop_servers"]
    broken = health_result["counts"].get("broken", 0)
    suspect = health_result["counts"].get("suspect", 0)
    duplicates = health_result.get("duplicates", [])

    # Start at 25, deduct for issues
    score = 25
    score -= broken * 4    # -4 per broken
    score -= suspect * 2   # -2 per suspect
    score -= len([d for d in duplicates if d["type"] == "within-config"])  # -1 per within-config dup

    if broken:
        recs.append(Recommendation(
            severity="HIGH",
            category="MCP",
            message=f"{broken} broken MCP servers with placeholder/missing keys",
            impact=f"Fix {broken} servers",
            command="maintain health --generate-clean",
        ))

    if suspect:
        recs.append(Recommendation(
            severity="MEDIUM",
            category="MCP",
            message=f"{suspect} MCP servers have Linux paths on Windows (synced from Pop!_OS)",
            impact=f"Fix {suspect} server configs",
            command="maintain health --generate-clean",
        ))

    within_dups = [d for d in duplicates if d["type"] == "within-config"]
    for dup in within_dups:
        recs.append(Recommendation(
            severity="MEDIUM",
            category="MCP",
            message=f"{dup['message']} -- consider consolidating",
            impact="Reduce config complexity",
        ))

    # Security: flag exposed tokens
    recs.append(Recommendation(
        severity="CRITICAL",
        category="Security",
        message="MCP configs contain exposed API tokens (GitHub PAT, Telegram, Discord, etc.)",
        impact="Security risk -- consider using environment variables or a secrets manager",
    ))

    return max(0, score), recs


def calculate_storage_score(clean_result: dict) -> tuple[int, list[Recommendation]]:
    """Score storage health (0-20)."""
    recs = []
    score = 20
    total = clean_result.get("total_storage_bytes", 0)
    dir_sizes = clean_result.get("dir_sizes", {})

    # Deduct for large directories
    if total > 2_000_000_000:  # > 2GB
        score -= 8
    elif total > 1_000_000_000:  # > 1GB
        score -= 4
    elif total > 500_000_000:  # > 500MB
        score -= 2

    # Session logs
    session_bytes = dir_sizes.get("sessions (JSONL)", 0)
    if session_bytes > 500_000_000:
        recs.append(Recommendation(
            severity="MEDIUM",
            category="Storage",
            message=f"Session logs: {format_bytes(session_bytes)}",
            impact=f"Reclaim ~{format_bytes(session_bytes - 200_000_000)} by pruning old sessions",
            command="maintain clean --max-age 60",
        ))
        score -= 3

    # Debug dir
    debug_bytes = dir_sizes.get("debug/", 0)
    if debug_bytes > 100_000_000:
        recs.append(Recommendation(
            severity="LOW",
            category="Storage",
            message=f"Debug directory: {format_bytes(debug_bytes)}",
            impact=f"Saves ~{format_bytes(debug_bytes)}",
        ))
        score -= 2

    # Plugins dir
    plugin_bytes = dir_sizes.get("plugins/", 0)
    if plugin_bytes > 300_000_000:
        recs.append(Recommendation(
            severity="LOW",
            category="Storage",
            message=f"Plugins directory: {format_bytes(plugin_bytes)}",
            impact="Review installed plugins, remove unused ones",
        ))
        score -= 2

    return max(0, score), recs


def calculate_skills_score(stats_result: dict) -> tuple[int, list[Recommendation]]:
    """Score skill hygiene (0-20)."""
    recs = []
    score = 20
    fs_skills = stats_result.get("filesystem_skills", 0)
    never_used = stats_result.get("never_used_skills", [])
    skill_usage = stats_result.get("skill_usage", {})

    if not fs_skills:
        return score, recs

    used_pct = ((fs_skills - len(never_used)) / fs_skills * 100) if fs_skills else 100

    if used_pct < 20:
        score -= 10
    elif used_pct < 50:
        score -= 5
    elif used_pct < 80:
        score -= 2

    if len(never_used) > 20:
        recs.append(Recommendation(
            severity="MEDIUM",
            category="Skills",
            message=f"{len(never_used)} of {fs_skills} skills have never been invoked",
            impact=f"Audit and archive {len(never_used)} unused skills",
            command="maintain stats",
        ))

    if len(never_used) > 50:
        recs.append(Recommendation(
            severity="HIGH",
            category="Skills",
            message="Over 50 skills appear dormant -- significant dead weight",
            impact="Simplify skill catalog for faster discovery",
        ))
        score -= 3

    return max(0, score), recs


def calculate_plugins_score(env: Environment) -> tuple[int, list[Recommendation]]:
    """Score plugin configuration (0-15)."""
    recs = []
    score = 15

    settings_path = env.settings_json
    if not settings_path.exists():
        return score, recs

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return score, recs

    plugins = settings.get("enabledPlugins", {})
    enabled = [k for k, v in plugins.items() if v]
    total = len(enabled)

    if total > 50:
        score -= 8
        recs.append(Recommendation(
            severity="HIGH",
            category="Plugins",
            message=f"{total} plugins enabled (all from claude-code-workflows)",
            impact="Each plugin adds context to every conversation. Consider enabling only relevant ones.",
        ))
    elif total > 30:
        score -= 4
        recs.append(Recommendation(
            severity="MEDIUM",
            category="Plugins",
            message=f"{total} plugins enabled",
            impact="Reduce to core plugins used for your primary work",
        ))

    return max(0, score), recs


def calculate_sync_score(clean_result: dict) -> tuple[int, list[Recommendation]]:
    """Score sync cleanliness (0-10)."""
    recs = []
    score = 10
    conflicts = clean_result.get("sync_conflicts", 0)
    conflict_bytes = clean_result.get("sync_conflict_bytes", 0)

    if conflicts > 50:
        score -= 8
    elif conflicts > 20:
        score -= 5
    elif conflicts > 5:
        score -= 2

    if conflicts:
        recs.append(Recommendation(
            severity="HIGH" if conflicts > 30 else "MEDIUM",
            category="Sync",
            message=f"{conflicts} Syncthing conflict files ({format_bytes(conflict_bytes)})",
            impact=f"Clean up {conflicts} files",
            command="maintain clean --execute",
        ))

    orphans = clean_result.get("orphaned_files", 0)
    if orphans > 5:
        recs.append(Recommendation(
            severity="LOW",
            category="Sync",
            message=f"{orphans} orphaned files (.backup, .broken, .old)",
            impact=f"Clean up {orphans} files",
            command="maintain clean --execute",
        ))
        score -= 1

    return max(0, score), recs


def calculate_naming_score(clean_result: dict) -> tuple[int, list[Recommendation]]:
    """Score naming consistency (0-10)."""
    recs = []
    score = 10
    issues = clean_result.get("naming_issues", 0)

    if issues > 20:
        score -= 6
    elif issues > 10:
        score -= 3
    elif issues > 0:
        score -= 1

    if issues:
        recs.append(Recommendation(
            severity="LOW",
            category="Naming",
            message=f"{issues} skills have inconsistent filename casing",
            impact="Standardize naming convention",
        ))

    return max(0, score), recs


def run_optimize(env: Environment, console: Console) -> dict:
    """Run all modules and produce a health score with recommendations."""
    console.print()
    console.print(Panel("[bold]Environment Optimization[/bold]", expand=False))
    console.print("  Running all checks...\n")

    # Run sub-modules (with quieter output)
    quiet_console = Console(quiet=True)

    health_result = run_health_check(env, quiet_console)
    clean_result = run_clean(env, quiet_console)
    stats_result = run_stats(env, quiet_console, recent_count=50, use_cache=True)

    # Calculate scores
    scores = ScoreBreakdown()
    all_recs: list[Recommendation] = []

    mcp_score, mcp_recs = calculate_mcp_score(health_result)
    scores.mcp = mcp_score
    all_recs.extend(mcp_recs)

    storage_score, storage_recs = calculate_storage_score(clean_result)
    scores.storage = storage_score
    all_recs.extend(storage_recs)

    skills_score, skills_recs = calculate_skills_score(stats_result)
    scores.skills = skills_score
    all_recs.extend(skills_recs)

    plugins_score, plugins_recs = calculate_plugins_score(env)
    scores.plugins = plugins_score
    all_recs.extend(plugins_recs)

    sync_score, sync_recs = calculate_sync_score(clean_result)
    scores.sync = sync_score
    all_recs.extend(sync_recs)

    naming_score, naming_recs = calculate_naming_score(clean_result)
    scores.naming = naming_score
    all_recs.extend(naming_recs)

    # Display score
    print_score_bar(console, scores.total)

    # Score breakdown table
    table = Table(title="Score Breakdown", show_lines=False, pad_edge=True)
    table.add_column("Category", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Max", justify="right", style="dim")
    for name, val, mx in [
        ("MCP Health", scores.mcp, 25),
        ("Storage", scores.storage, 20),
        ("Skills", scores.skills, 20),
        ("Plugins", scores.plugins, 15),
        ("Sync Clean", scores.sync, 10),
        ("Naming", scores.naming, 10),
    ]:
        color = "green" if val >= mx * 0.8 else "yellow" if val >= mx * 0.5 else "red"
        table.add_row(name, f"[{color}]{val}[/]", str(mx))
    console.print(table)

    # Recommendations sorted by severity
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    all_recs.sort(key=lambda r: severity_order.get(r.severity, 99))

    if all_recs:
        console.print()
        table = Table(title="Recommendations", show_lines=True, pad_edge=True)
        table.add_column("#", style="dim", width=3)
        table.add_column("Severity", width=10)
        table.add_column("Category", width=10)
        table.add_column("Issue")
        table.add_column("Impact")
        table.add_column("Fix", style="cyan")

        for i, rec in enumerate(all_recs, 1):
            sev = f"[{severity_color(rec.severity)}]{rec.severity}[/]"
            table.add_row(str(i), sev, rec.category, rec.message, rec.impact, rec.command or "-")

        console.print(table)

    # Save markdown report
    report_md = _generate_markdown_report(scores, all_recs, health_result, clean_result, stats_result)
    report_path = save_report(env.reports_dir, "optimize", report_md)
    console.print(f"\n  Report saved to: [cyan]{report_path}[/]")

    return {
        "score": scores.total,
        "breakdown": {
            "mcp": scores.mcp,
            "storage": scores.storage,
            "skills": scores.skills,
            "plugins": scores.plugins,
            "sync": scores.sync,
            "naming": scores.naming,
        },
        "recommendations": [
            {"severity": r.severity, "category": r.category, "message": r.message, "impact": r.impact}
            for r in all_recs
        ],
        "report_path": str(report_path),
    }


def _generate_markdown_report(
    scores: ScoreBreakdown,
    recs: list[Recommendation],
    health: dict,
    clean: dict,
    stats: dict,
) -> str:
    """Generate a markdown report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# Claude Code Environment Report",
        f"Generated: {now}",
        f"",
        f"## Health Score: {scores.total}/100",
        f"",
        f"| Category | Score | Max |",
        f"|----------|-------|-----|",
        f"| MCP Health | {scores.mcp} | 25 |",
        f"| Storage | {scores.storage} | 20 |",
        f"| Skills | {scores.skills} | 20 |",
        f"| Plugins | {scores.plugins} | 15 |",
        f"| Sync Clean | {scores.sync} | 10 |",
        f"| Naming | {scores.naming} | 10 |",
        f"",
        f"## MCP Servers",
        f"- CLI: {health.get('cli_servers', 0)} servers",
        f"- Desktop: {health.get('desktop_servers', 0)} servers",
        f"- Healthy: {health['counts'].get('healthy', 0)}",
        f"- Broken: {health['counts'].get('broken', 0)}",
        f"- Suspect: {health['counts'].get('suspect', 0)}",
        f"",
        f"## Storage",
        f"- Sync conflicts: {clean.get('sync_conflicts', 0)} files ({format_bytes(clean.get('sync_conflict_bytes', 0))})",
        f"- Orphaned files: {clean.get('orphaned_files', 0)}",
        f"- Total measured: {format_bytes(clean.get('total_storage_bytes', 0))}",
        f"",
        f"## Usage",
        f"- Sessions parsed: {stats.get('sessions_parsed', 0)}",
        f"- Total tool invocations: {stats.get('total_tool_uses', 0):,}",
        f"- Filesystem skills: {stats.get('filesystem_skills', 0)}",
        f"- Never-used skills: {len(stats.get('never_used_skills', []))}",
        f"",
        f"## Recommendations",
        f"",
    ]
    for i, rec in enumerate(recs, 1):
        lines.append(f"{i}. **[{rec.severity}]** ({rec.category}) {rec.message}")
        if rec.impact:
            lines.append(f"   - Impact: {rec.impact}")
        if rec.command:
            lines.append(f"   - Fix: `{rec.command}`")
        lines.append("")

    return "\n".join(lines)
