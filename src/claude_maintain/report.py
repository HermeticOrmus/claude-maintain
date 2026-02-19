"""Rich table formatting and markdown report generation."""

import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def format_bytes(size: int) -> str:
    """Human-readable byte size."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def severity_color(severity: str) -> str:
    """Map severity to Rich color."""
    return {
        "CRITICAL": "red bold",
        "HIGH": "red",
        "MEDIUM": "yellow",
        "LOW": "dim",
        "healthy": "green",
        "broken": "red",
        "suspect": "yellow",
        "unknown": "dim",
    }.get(severity, "white")


def make_status_table(title: str, columns: list[tuple[str, str]], rows: list[list]) -> Table:
    """Create a Rich table with typed columns."""
    table = Table(title=title, show_lines=False, pad_edge=True)
    for name, style in columns:
        table.add_column(name, style=style)
    for row in rows:
        table.add_row(*[str(c) for c in row])
    return table


def save_report(reports_dir: Path, name: str, content: str) -> Path:
    """Save a markdown report to the reports directory."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = reports_dir / f"{name}-{ts}.md"
    path.write_text(content, encoding="utf-8")
    return path


def print_score_bar(console: Console, score: int, label: str = "Health Score") -> None:
    """Print a visual score bar."""
    bar_width = 40
    filled = int(bar_width * score / 100)
    empty = bar_width - filled

    if score >= 80:
        color = "green"
    elif score >= 60:
        color = "yellow"
    else:
        color = "red"

    bar = Text()
    bar.append(f" {label}: ", style="bold")
    bar.append("#" * filled, style=color)
    bar.append("-" * empty, style="dim")
    bar.append(f" {score}/100", style=f"bold {color}")
    console.print(Panel(bar))
