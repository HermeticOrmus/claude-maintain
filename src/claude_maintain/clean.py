"""Environment cleanup: sync conflicts, stale sessions, naming."""

import os
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from claude_maintain.config import Environment
from claude_maintain.report import format_bytes, save_report


# Syncthing conflict pattern: name.sync-conflict-YYYYMMDD-HHMMSS-DEVICEID.ext
SYNC_CONFLICT_RE = re.compile(r"\.sync-conflict-(\d{8})-(\d{6})-([A-Z0-9]+)\.")


@dataclass
class CleanupItem:
    """A file or directory flagged for cleanup."""

    path: Path
    category: str  # "sync-conflict", "stale-session", "orphan", "naming"
    size: int = 0
    age_days: float = 0.0
    detail: str = ""


@dataclass
class DirSizeInfo:
    """Size info for a directory."""

    path: Path
    name: str
    total_bytes: int = 0
    file_count: int = 0


@dataclass
class NamingIssue:
    """Skill/command naming inconsistency."""

    path: Path
    current: str
    expected: str
    category: str


def find_sync_conflicts(claude_dir: Path) -> list[CleanupItem]:
    """Find all Syncthing conflict files under ~/.claude/."""
    items = []
    for p in claude_dir.rglob("*"):
        if p.is_file() and SYNC_CONFLICT_RE.search(p.name):
            m = SYNC_CONFLICT_RE.search(p.name)
            date_str = m.group(1) if m else "unknown"
            device_id = m.group(3) if m else "unknown"
            try:
                size = p.stat().st_size
                age = (time.time() - p.stat().st_mtime) / 86400
            except OSError:
                size, age = 0, 0
            items.append(CleanupItem(
                path=p,
                category="sync-conflict",
                size=size,
                age_days=age,
                detail=f"date={date_str} device={device_id}",
            ))
    return items


def find_stale_sessions(sessions_dir: Path, max_age_days: int) -> list[CleanupItem]:
    """Find session JSONL files older than max_age_days."""
    items = []
    if not sessions_dir.exists():
        return items
    cutoff = time.time() - (max_age_days * 86400)
    for p in sessions_dir.glob("*.jsonl"):
        try:
            stat = p.stat()
            if stat.st_mtime < cutoff:
                age = (time.time() - stat.st_mtime) / 86400
                items.append(CleanupItem(
                    path=p,
                    category="stale-session",
                    size=stat.st_size,
                    age_days=age,
                    detail=f"{age:.0f} days old",
                ))
        except OSError:
            pass
    return items


def find_orphaned_files(claude_dir: Path) -> list[CleanupItem]:
    """Find .backup, .broken, .bak files."""
    items = []
    for pattern in ("*.backup", "*.broken", "*.bak", "*.old"):
        for p in claude_dir.rglob(pattern):
            if p.is_file():
                try:
                    size = p.stat().st_size
                    age = (time.time() - p.stat().st_mtime) / 86400
                except OSError:
                    size, age = 0, 0
                items.append(CleanupItem(
                    path=p,
                    category="orphan",
                    size=size,
                    age_days=age,
                    detail=p.suffix,
                ))
    return items


def analyze_naming(skills_dir: Path) -> list[NamingIssue]:
    """Find SKILL.md vs skill.md inconsistencies."""
    issues = []
    if not skills_dir.exists():
        return issues

    uppercase_count = 0
    lowercase_count = 0
    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        upper = skill_dir / "SKILL.md"
        lower = skill_dir / "skill.md"
        if upper.exists():
            uppercase_count += 1
        elif lower.exists():
            lowercase_count += 1

    # Convention is whatever the majority uses
    if uppercase_count > lowercase_count:
        expected = "SKILL.md"
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            lower = skill_dir / "skill.md"
            if lower.exists() and not (skill_dir / "SKILL.md").exists():
                issues.append(NamingIssue(
                    path=lower,
                    current="skill.md",
                    expected=expected,
                    category="case-mismatch",
                ))
    elif lowercase_count > uppercase_count:
        expected = "skill.md"
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            upper = skill_dir / "SKILL.md"
            if upper.exists() and not (skill_dir / "skill.md").exists():
                issues.append(NamingIssue(
                    path=upper,
                    current="SKILL.md",
                    expected=expected,
                    category="case-mismatch",
                ))

    return issues


def measure_directories(env: Environment) -> list[DirSizeInfo]:
    """Measure sizes of key directories."""
    dirs_to_measure = [
        (env.debug_dir, "debug/"),
        (env.snapshots_dir, "shell-snapshots/"),
        (env.file_history_dir, "file-history/"),
        (env.sessions_dir, "sessions (JSONL)"),
        (env.plugins_dir, "plugins/"),
    ]
    results = []
    for path, name in dirs_to_measure:
        info = DirSizeInfo(path=path, name=name)
        if path.exists():
            for f in path.rglob("*"):
                if f.is_file():
                    try:
                        info.total_bytes += f.stat().st_size
                        info.file_count += 1
                    except OSError:
                        pass
        results.append(info)
    return results


def execute_cleanup(
    items: list[CleanupItem], env: Environment, console: Console
) -> tuple[int, int]:
    """Move flagged items to backup directory. Returns (count, bytes)."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = env.claude_dir / "backups" / f"maintain-{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    moved_count = 0
    moved_bytes = 0

    for item in items:
        try:
            # Preserve relative path structure in backup
            rel = item.path.relative_to(env.claude_dir)
            dest = backup_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item.path), str(dest))
            moved_count += 1
            moved_bytes += item.size
        except (OSError, ValueError) as e:
            console.print(f"  [red]Failed to move {item.path}: {e}[/]")

    console.print(
        f"\n  Moved {moved_count} files ({format_bytes(moved_bytes)}) to [cyan]{backup_dir}[/]"
    )
    return moved_count, moved_bytes


def run_clean(
    env: Environment,
    console: Console,
    execute: bool = False,
    max_age_days: int = 30,
) -> dict:
    """Run environment cleanup scan."""
    console.print()
    console.print(Panel("[bold]Environment Cleanup[/bold]", expand=False))

    # 1. Sync conflicts
    conflicts = find_sync_conflicts(env.claude_dir)
    conflict_bytes = sum(c.size for c in conflicts)
    console.print(
        f"\n  [bold]Sync Conflicts:[/] {len(conflicts)} files ({format_bytes(conflict_bytes)})"
    )
    if conflicts:
        # Group by directory
        by_dir: dict[str, list[CleanupItem]] = {}
        for c in conflicts:
            d = str(c.path.parent.relative_to(env.claude_dir))
            by_dir.setdefault(d, []).append(c)
        for d, items in sorted(by_dir.items()):
            console.print(f"    {d}/: {len(items)} files")

    # 2. Stale sessions
    stale = find_stale_sessions(env.sessions_dir, max_age_days)
    stale_bytes = sum(s.size for s in stale)
    console.print(
        f"\n  [bold]Stale Sessions (>{max_age_days}d):[/] {len(stale)} files ({format_bytes(stale_bytes)})"
    )

    # 3. Orphaned files
    orphans = find_orphaned_files(env.claude_dir)
    orphan_bytes = sum(o.size for o in orphans)
    console.print(
        f"\n  [bold]Orphaned Files:[/] {len(orphans)} files ({format_bytes(orphan_bytes)})"
    )
    for o in orphans[:10]:
        rel = o.path.relative_to(env.claude_dir)
        console.print(f"    {rel} ({format_bytes(o.size)})")

    # 4. Naming analysis
    naming_issues = analyze_naming(env.skills_dir)
    console.print(f"\n  [bold]Naming Issues:[/] {len(naming_issues)} skills with inconsistent casing")
    for ni in naming_issues[:10]:
        skill_name = ni.path.parent.name
        console.print(f"    {skill_name}/: has {ni.current}, convention is {ni.expected}")

    # 5. Directory sizes
    dir_sizes = measure_directories(env)
    console.print(f"\n  [bold]Directory Sizes:[/]")
    table = Table(show_header=True, show_lines=False, pad_edge=True)
    table.add_column("Directory", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Files", justify="right")
    total_bytes = 0
    for ds in dir_sizes:
        table.add_row(ds.name, format_bytes(ds.total_bytes), str(ds.file_count))
        total_bytes += ds.total_bytes
    table.add_row("[bold]Total[/]", f"[bold]{format_bytes(total_bytes)}[/]", "")
    console.print(table)

    # Execute or dry-run
    all_items = conflicts + orphans  # sync conflicts + orphans are safe to move
    if execute and all_items:
        console.print("\n  [bold yellow]Executing cleanup...[/]")
        moved_count, moved_bytes = execute_cleanup(all_items, env, console)
    elif all_items:
        console.print(
            f"\n  [dim]Dry run: {len(all_items)} files ({format_bytes(sum(i.size for i in all_items))}) "
            f"would be moved. Use --execute to proceed.[/]"
        )

    return {
        "sync_conflicts": len(conflicts),
        "sync_conflict_bytes": conflict_bytes,
        "stale_sessions": len(stale),
        "stale_session_bytes": stale_bytes,
        "orphaned_files": len(orphans),
        "orphan_bytes": orphan_bytes,
        "naming_issues": len(naming_issues),
        "dir_sizes": {ds.name: ds.total_bytes for ds in dir_sizes},
        "total_storage_bytes": total_bytes,
    }
