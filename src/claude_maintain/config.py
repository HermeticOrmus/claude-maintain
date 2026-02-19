"""Path constants, platform detection, and environment configuration."""

import os
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Environment:
    """Detected environment configuration."""

    platform: str  # "windows", "linux", "darwin"
    home: Path
    claude_dir: Path
    claude_cli_mcp: Path
    claude_desktop_mcp: Path
    settings_json: Path
    skills_dir: Path
    commands_dir: Path
    sessions_dir: Path
    reports_dir: Path
    debug_dir: Path
    snapshots_dir: Path
    file_history_dir: Path
    plugins_dir: Path

    @property
    def is_windows(self) -> bool:
        return self.platform == "windows"

    @property
    def is_linux(self) -> bool:
        return self.platform == "linux"


def detect_environment() -> Environment:
    """Auto-detect paths based on current platform."""
    home = Path.home()
    plat = _detect_platform()
    claude_dir = home / ".claude"

    if plat == "windows":
        desktop_mcp = home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    elif plat == "darwin":
        desktop_mcp = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        desktop_mcp = home / ".config" / "Claude" / "claude_desktop_config.json"

    # Determine project session directory (Windows convention)
    if plat == "windows":
        sessions_dir = claude_dir / "projects" / f"C--Users-{home.name}"
    else:
        sessions_dir = claude_dir / "projects" / f"home-{home.name}"

    reports_dir = claude_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    return Environment(
        platform=plat,
        home=home,
        claude_dir=claude_dir,
        claude_cli_mcp=claude_dir / "mcp.json",
        claude_desktop_mcp=desktop_mcp,
        settings_json=claude_dir / "settings.json",
        skills_dir=claude_dir / "skills",
        commands_dir=claude_dir / "commands",
        sessions_dir=sessions_dir,
        reports_dir=reports_dir,
        debug_dir=claude_dir / "debug",
        snapshots_dir=claude_dir / "shell-snapshots",
        file_history_dir=claude_dir / "file-history",
        plugins_dir=claude_dir / "plugins",
    )


def _detect_platform() -> str:
    """Detect OS platform."""
    system = platform.system().lower()
    if system == "windows" or "microsoft" in platform.release().lower():
        return "windows"
    elif system == "darwin":
        return "darwin"
    return "linux"


# Linux path patterns that indicate synced-from-Linux configs
LINUX_PATH_PREFIXES = ("/home/", "/usr/", "/opt/", "/etc/", "/var/")

# Known placeholder values that indicate unconfigured servers
PLACEHOLDER_VALUES = {
    "YOUR_OPENAI_API_KEY_HERE",
    "YOUR_API_KEY_HERE",
    "your-api-key",
    "sk-...",
    "CHANGE_ME",
    "placeholder",
}

# Known MCP server requirements for health checking
KNOWN_SERVER_REQUIREMENTS: dict[str, dict] = {
    "qdrant": {
        "env_required": ["QDRANT_URL", "OPENAI_API_KEY"],
        "description": "Vector database with OpenAI embeddings",
    },
    "github": {
        "env_required": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
        "description": "GitHub API access",
    },
    "discord": {
        "env_required": ["DISCORD_BOT_TOKEN", "DISCORD_TOKEN"],
        "env_any": True,  # any one of these is sufficient
        "description": "Discord bot integration",
    },
    "telegram": {
        "env_required": ["TG_APP_ID", "TG_API_HASH"],
        "description": "Telegram user client",
    },
    "gmail": {
        "env_required": ["GMAIL_OAUTH_PATH"],
        "description": "Gmail email access",
        "path_env_keys": ["GMAIL_OAUTH_PATH", "GMAIL_CREDENTIALS_PATH"],
    },
    "google-calendar": {
        "env_required": ["GOOGLE_OAUTH_CREDENTIALS"],
        "description": "Google Calendar",
        "path_env_keys": ["GOOGLE_OAUTH_CREDENTIALS"],
    },
    "obsidian": {
        "env_required": ["OBSIDIAN_REST_API_KEY"],
        "description": "Obsidian note management",
    },
    "n8n": {
        "env_required": ["N8N_API_KEY", "N8N_BASE_URL"],
        "description": "n8n workflow automation",
    },
}
