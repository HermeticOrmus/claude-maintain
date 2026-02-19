"""JSONL streaming parser and usage analytics."""

import json
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from claude_maintain.config import Environment
from claude_maintain.report import format_bytes


CACHE_FILENAME = "maintain-usage-cache.json"


@dataclass
class SessionStats:
    """Stats extracted from a single session."""

    file: str
    tool_counts: dict[str, int] = field(default_factory=dict)
    skill_calls: list[str] = field(default_factory=list)
    mcp_calls: list[str] = field(default_factory=list)
    total_tool_uses: int = 0


@dataclass
class AggregateStats:
    """Aggregated stats across all parsed sessions."""

    sessions_parsed: int = 0
    total_bytes_parsed: int = 0
    tool_counts: Counter = field(default_factory=Counter)
    skill_counts: Counter = field(default_factory=Counter)
    mcp_counts: Counter = field(default_factory=Counter)
    total_tool_uses: int = 0


def stream_parse_session(path: Path) -> SessionStats:
    """Parse a single JSONL session file using streaming."""
    stats = SessionStats(file=path.name)
    tool_counts: Counter = Counter()

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if entry.get("type") != "assistant":
                    continue

                content = entry.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue

                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue

                    name = block.get("name", "unknown")
                    tool_counts[name] += 1
                    stats.total_tool_uses += 1

                    # Extract Skill tool invocations
                    if name == "Skill":
                        inp = block.get("input", {})
                        skill_name = inp.get("skill", "unknown")
                        stats.skill_calls.append(skill_name)

                    # Extract MCP tool calls (prefixed with mcp__)
                    if name.startswith("mcp__"):
                        stats.mcp_calls.append(name)

    except OSError:
        pass

    stats.tool_counts = dict(tool_counts)
    return stats


def load_cache(env: Environment) -> dict:
    """Load the usage cache file."""
    cache_path = env.reports_dir / CACHE_FILENAME
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 1, "files": {}}


def save_cache(env: Environment, cache: dict) -> None:
    """Save the usage cache file."""
    cache_path = env.reports_dir / CACHE_FILENAME
    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def get_session_files(env: Environment, recent_count: int = 0) -> list[Path]:
    """Get session JSONL files, optionally limited to N most recent."""
    if not env.sessions_dir.exists():
        return []
    files = sorted(env.sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if recent_count > 0:
        files = files[:recent_count]
    return files


def list_filesystem_skills(env: Environment) -> set[str]:
    """List all skill names present on the filesystem."""
    skills = set()
    if env.skills_dir.exists():
        for d in env.skills_dir.iterdir():
            if d.is_dir():
                if (d / "SKILL.md").exists() or (d / "skill.md").exists():
                    skills.add(d.name)
    return skills


def run_stats(
    env: Environment,
    console: Console,
    recent_count: int = 0,
    use_cache: bool = True,
) -> dict:
    """Run usage analytics across session logs."""
    console.print()
    console.print(Panel("[bold]Usage Analytics[/bold]", expand=False))

    files = get_session_files(env, recent_count)
    if not files:
        console.print("  No session files found.")
        return {"sessions_parsed": 0}

    cache = load_cache(env) if use_cache else {"version": 1, "files": {}}
    agg = AggregateStats()

    parsed_new = 0
    cached_hit = 0
    start_time = time.time()

    for i, fp in enumerate(files):
        try:
            stat = fp.stat()
            cache_key = fp.name
            file_mtime = str(stat.st_mtime)
            file_size = stat.st_size

            # Check cache
            cached = cache["files"].get(cache_key)
            if use_cache and cached and cached.get("mtime") == file_mtime:
                # Use cached data
                for tool, count in cached.get("tools", {}).items():
                    agg.tool_counts[tool] += count
                for skill in cached.get("skills", []):
                    agg.skill_counts[skill] += 1
                for mcp in cached.get("mcps", []):
                    agg.mcp_counts[mcp] += 1
                agg.total_tool_uses += cached.get("total", 0)
                agg.total_bytes_parsed += file_size
                cached_hit += 1
            else:
                # Parse fresh
                session = stream_parse_session(fp)
                for tool, count in session.tool_counts.items():
                    agg.tool_counts[tool] += count
                for skill in session.skill_calls:
                    agg.skill_counts[skill] += 1
                for mcp in session.mcp_calls:
                    agg.mcp_counts[mcp] += 1
                agg.total_tool_uses += session.total_tool_uses
                agg.total_bytes_parsed += file_size
                parsed_new += 1

                # Update cache
                cache["files"][cache_key] = {
                    "mtime": file_mtime,
                    "tools": session.tool_counts,
                    "skills": session.skill_calls,
                    "mcps": session.mcp_calls,
                    "total": session.total_tool_uses,
                }

            agg.sessions_parsed += 1

            # Progress every 50 files
            if (i + 1) % 50 == 0:
                console.print(f"  ... parsed {i + 1}/{len(files)} sessions", highlight=False)

        except OSError:
            pass

    elapsed = time.time() - start_time

    # Save cache
    if use_cache:
        save_cache(env, cache)

    # Display results
    console.print(
        f"\n  Parsed {agg.sessions_parsed} sessions "
        f"({format_bytes(agg.total_bytes_parsed)}) in {elapsed:.1f}s"
    )
    console.print(f"  Cache: {cached_hit} hits, {parsed_new} new parses")
    console.print(f"  Total tool invocations: {agg.total_tool_uses:,}")

    # Top tools
    if agg.tool_counts:
        console.print()
        table = Table(title="Top 15 Tools", show_lines=False, pad_edge=True)
        table.add_column("Tool", style="cyan")
        table.add_column("Count", justify="right", style="bold")
        table.add_column("% of Total", justify="right")
        for tool, count in agg.tool_counts.most_common(15):
            pct = (count / agg.total_tool_uses * 100) if agg.total_tool_uses else 0
            table.add_row(tool, f"{count:,}", f"{pct:.1f}%")
        console.print(table)

    # Skill usage
    if agg.skill_counts:
        console.print()
        table = Table(title="Skill Usage", show_lines=False, pad_edge=True)
        table.add_column("Skill", style="cyan")
        table.add_column("Invocations", justify="right", style="bold")
        for skill, count in agg.skill_counts.most_common(20):
            table.add_row(skill, str(count))
        console.print(table)

    # Cross-reference: skills on filesystem that were never invoked
    fs_skills = list_filesystem_skills(env)
    invoked_skills = set(agg.skill_counts.keys())
    never_used = sorted(fs_skills - invoked_skills)

    if never_used:
        console.print(f"\n  [bold]Never-invoked skills:[/] {len(never_used)} of {len(fs_skills)}")
        # Show in columns
        for i in range(0, len(never_used), 4):
            row = never_used[i : i + 4]
            console.print("    " + "  ".join(f"[dim]{s}[/]" for s in row))

    # MCP tool usage
    if agg.mcp_counts:
        console.print()
        table = Table(title="Top MCP Tools", show_lines=False, pad_edge=True)
        table.add_column("MCP Tool", style="cyan")
        table.add_column("Count", justify="right", style="bold")
        for mcp, count in agg.mcp_counts.most_common(10):
            table.add_row(mcp, str(count))
        console.print(table)

    return {
        "sessions_parsed": agg.sessions_parsed,
        "bytes_parsed": agg.total_bytes_parsed,
        "parse_time_seconds": round(elapsed, 1),
        "cache_hits": cached_hit,
        "new_parses": parsed_new,
        "total_tool_uses": agg.total_tool_uses,
        "top_tools": dict(agg.tool_counts.most_common(20)),
        "skill_usage": dict(agg.skill_counts.most_common()),
        "filesystem_skills": len(fs_skills),
        "never_used_skills": never_used,
        "mcp_usage": dict(agg.mcp_counts.most_common(10)),
    }
