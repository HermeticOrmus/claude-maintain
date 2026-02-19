"""MCP config parsing and health checks."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from claude_maintain.config import (
    KNOWN_SERVER_REQUIREMENTS,
    LINUX_PATH_PREFIXES,
    PLACEHOLDER_VALUES,
    Environment,
)
from claude_maintain.report import save_report, severity_color


@dataclass
class ServerHealth:
    """Health assessment of a single MCP server."""

    name: str
    source: str  # "cli" or "desktop"
    status: str = "unknown"  # "healthy", "broken", "suspect", "unknown"
    issues: list[str] = field(default_factory=list)
    command: str = ""
    package: str = ""


def parse_mcp_config(path: Path) -> dict:
    """Parse an MCP config JSON file, returning the mcpServers dict."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("mcpServers", {})
    except (json.JSONDecodeError, OSError):
        return {}


def check_server(name: str, config: dict, env: Environment, source: str) -> ServerHealth:
    """Check a single MCP server configuration for issues."""
    sh = ServerHealth(name=name, source=source)
    issues = sh.issues

    command = config.get("command", "")
    args = config.get("args", [])
    env_vars = config.get("env", {})

    sh.command = command

    # Extract package name from args
    if args and isinstance(args, list):
        for arg in args:
            if isinstance(arg, str) and not arg.startswith("-"):
                sh.package = arg
                break

    # Check 1: Linux paths on Windows
    if env.is_windows:
        all_strings = [command] + args + list(env_vars.values())
        for s in all_strings:
            if isinstance(s, str) and any(s.startswith(prefix) for prefix in LINUX_PATH_PREFIXES):
                issues.append(f"Linux path on Windows: {s}")

    # Check 2: Placeholder API keys
    for key, val in env_vars.items():
        if isinstance(val, str) and val in PLACEHOLDER_VALUES:
            issues.append(f"Placeholder value for {key}: {val}")

    # Check 3: Path-based arguments that reference wrong OS
    if env.is_windows:
        for arg in args:
            if isinstance(arg, str) and any(arg.startswith(p) for p in LINUX_PATH_PREFIXES):
                issues.append(f"Linux path in args: {arg}")

    # Check 4: Known requirements
    base_name = _normalize_server_name(name)
    if base_name in KNOWN_SERVER_REQUIREMENTS:
        reqs = KNOWN_SERVER_REQUIREMENTS[base_name]
        required = reqs.get("env_required", [])
        any_ok = reqs.get("env_any", False)
        path_keys = reqs.get("path_env_keys", [])

        if any_ok:
            if not any(k in env_vars for k in required):
                issues.append(f"Missing one of: {', '.join(required)}")
        else:
            for req_key in required:
                if req_key not in env_vars:
                    issues.append(f"Missing env var: {req_key}")

        # Check that path env vars point to existing files (on current platform)
        for pk in path_keys:
            if pk in env_vars:
                p = Path(env_vars[pk])
                if not p.exists() and not any(env_vars[pk].startswith(lp) for lp in LINUX_PATH_PREFIXES):
                    issues.append(f"Path does not exist: {pk}={env_vars[pk]}")

    # Determine status
    if not issues:
        sh.status = "healthy"
    elif any("Placeholder" in i or "Missing env" in i for i in issues):
        sh.status = "broken"
    elif any("Linux path" in i for i in issues):
        sh.status = "suspect"
    else:
        sh.status = "unknown"

    return sh


def find_duplicates(cli_servers: dict, desktop_servers: dict) -> list[dict]:
    """Find services that appear to be duplicated across or within configs."""
    duplicates = []

    # Cross-config: same logical service in both
    cli_names = set(cli_servers.keys())
    desktop_names = set(desktop_servers.keys())
    common = cli_names & desktop_names
    for name in sorted(common):
        duplicates.append({
            "type": "cross-config",
            "name": name,
            "message": f"'{name}' exists in both CLI and Desktop configs",
        })

    # Within-config: services that serve the same purpose (e.g., 4 telegram variants)
    def group_by_service(servers: dict, source: str) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for name in servers:
            base = _normalize_server_name(name)
            groups.setdefault(base, []).append(name)
        return groups

    for source, servers in [("CLI", cli_servers), ("Desktop", desktop_servers)]:
        groups = group_by_service(servers, source)
        for base, names in groups.items():
            if len(names) > 1:
                duplicates.append({
                    "type": "within-config",
                    "source": source,
                    "service": base,
                    "names": names,
                    "message": f"{source}: {len(names)} {base} variants: {', '.join(names)}",
                })

    return duplicates


def _normalize_server_name(name: str) -> str:
    """Normalize server name to base service (e.g., 'telegram-go' -> 'telegram')."""
    name = name.lower()
    # Handle compound names
    for prefix in ("supabase-", "telegram-", "lharries-"):
        if name.startswith(prefix) and name != prefix.rstrip("-"):
            # Keep supabase-biogenesis as 'supabase', telegram-go as 'telegram'
            return prefix.rstrip("-")
    # Handle periskope-whatsapp -> whatsapp
    if "whatsapp" in name:
        return "whatsapp"
    return name.split("-")[0] if "-" in name else name


def generate_clean_config(servers: dict, env: Environment) -> dict:
    """Generate a cleaned version of an MCP config with fixes applied."""
    clean = {}
    for name, config in servers.items():
        fixed = json.loads(json.dumps(config))  # deep copy

        # Fix Linux paths to Windows equivalents
        if env.is_windows:
            fixed = _fix_paths(fixed, env)

        # Remove placeholder values
        if "env" in fixed:
            for key, val in list(fixed["env"].items()):
                if val in PLACEHOLDER_VALUES:
                    fixed["env"][key] = f"TODO: Set {key}"

        clean[name] = fixed
    return {"mcpServers": clean}


def _fix_paths(config: dict, env: Environment) -> dict:
    """Replace Linux paths with Windows equivalents (and vice versa)."""
    config_str = json.dumps(config)
    win_home = str(env.home).replace("\\", "/")

    # Try common Linux home patterns and replace with current platform's home
    import re
    config_str = re.sub(r"/home/[a-zA-Z0-9_.-]+", win_home, config_str)

    return json.loads(config_str)


def run_health_check(
    env: Environment, console: Console, generate_clean: bool = False
) -> dict:
    """Run MCP health check across all configs."""
    cli_servers = parse_mcp_config(env.claude_cli_mcp)
    desktop_servers = parse_mcp_config(env.claude_desktop_mcp)

    results: list[ServerHealth] = []

    for name, config in cli_servers.items():
        results.append(check_server(name, config, env, "CLI"))
    for name, config in desktop_servers.items():
        results.append(check_server(name, config, env, "Desktop"))

    duplicates = find_duplicates(cli_servers, desktop_servers)

    # Count by status
    counts = {"healthy": 0, "broken": 0, "suspect": 0, "unknown": 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    # Display
    console.print()
    console.print(Panel("[bold]MCP Health Check[/bold]", expand=False))
    console.print(
        f"  CLI servers: {len(cli_servers)}  |  Desktop servers: {len(desktop_servers)}"
    )
    console.print(
        f"  [green]Healthy: {counts['healthy']}[/]  "
        f"[red]Broken: {counts['broken']}[/]  "
        f"[yellow]Suspect: {counts['suspect']}[/]  "
        f"[dim]Unknown: {counts['unknown']}[/]"
    )
    console.print()

    # Server details table
    table = Table(title="Server Status", show_lines=False, pad_edge=True)
    table.add_column("Server", style="bold")
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Issues")

    for r in sorted(results, key=lambda x: (x.status != "broken", x.status != "suspect", x.name)):
        status_text = f"[{severity_color(r.status)}]{r.status}[/]"
        issues_text = "; ".join(r.issues) if r.issues else "-"
        table.add_row(r.name, r.source, status_text, issues_text)

    console.print(table)

    # Duplicates
    if duplicates:
        console.print()
        console.print("[bold yellow]Duplicate Services[/bold yellow]")
        for d in duplicates:
            console.print(f"  [yellow]>[/] {d['message']}")

    # Generate clean config
    if generate_clean:
        for source, servers, orig_path in [
            ("cli", cli_servers, env.claude_cli_mcp),
            ("desktop", desktop_servers, env.claude_desktop_mcp),
        ]:
            clean = generate_clean_config(servers, env)
            path = save_report(
                env.reports_dir,
                f"mcp-clean-{source}",
                json.dumps(clean, indent=2),
            )
            console.print(f"\n  Clean {source} config saved to: [cyan]{path}[/]")

    # Return structured data
    return {
        "cli_servers": len(cli_servers),
        "desktop_servers": len(desktop_servers),
        "counts": counts,
        "servers": [
            {"name": r.name, "source": r.source, "status": r.status, "issues": r.issues}
            for r in results
        ],
        "duplicates": duplicates,
    }
