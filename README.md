# claude-maintain

Environment maintenance tool for [Claude Code](https://claude.com/claude-code) (`~/.claude/`).

Diagnoses MCP server health, finds sync debris, analyzes tool usage from session logs, and produces a health score with prioritized recommendations.

## Install

```bash
# With uv (recommended)
uv tool install claude-maintain

# With pip
pip install claude-maintain

# Development (editable)
git clone https://github.com/HermeticOrmus/claude-maintain.git
cd claude-maintain
uv tool install -e .
```

## Commands

### `maintain health` -- MCP Server Health Check

Parses both Claude Code CLI (`~/.claude/mcp.json`) and Claude Desktop (`claude_desktop_config.json`) configs. Detects:

- Placeholder API keys (`YOUR_OPENAI_API_KEY_HERE`)
- Cross-platform path issues (Linux paths on Windows, synced via Syncthing/rsync)
- Duplicate services (e.g., 4 Telegram variants)
- Missing required environment variables

```bash
maintain health                  # Show health report
maintain health --generate-clean # Save fixed configs to ~/.claude/reports/
```

### `maintain clean` -- Environment Cleanup

Finds accumulated debris in `~/.claude/`:

- Syncthing conflict files (`*.sync-conflict-*`)
- Orphaned files (`.backup`, `.broken`, `.old`)
- Stale session logs (configurable age threshold)
- Skill naming inconsistencies (`SKILL.md` vs `skill.md`)
- Directory size breakdown

```bash
maintain clean                 # Dry run (shows what would be cleaned)
maintain clean --execute       # Move debris to ~/.claude/backups/ (safe, reversible)
maintain clean --max-age 60    # Flag sessions older than 60 days
```

### `maintain stats` -- Usage Analytics

Stream-parses session JSONL files to extract tool usage patterns:

- Per-tool invocation counts (Read, Bash, Write, MCP tools, etc.)
- Skill usage tracking (which `/skills` are actually used)
- Cross-reference with filesystem (find never-invoked skills)
- Results cached for fast repeat runs

```bash
maintain stats                 # Full scan (all sessions, cached)
maintain stats --recent 20     # Only 20 most recent sessions
maintain stats --no-cache      # Force fresh parse
```

### `maintain optimize` -- Health Score + Recommendations

Runs all three modules and synthesizes a weighted health score (0-100):

| Category | Weight |
|----------|--------|
| MCP Health | 25 |
| Storage | 20 |
| Skills | 20 |
| Plugins | 15 |
| Sync Cleanliness | 10 |
| Naming Consistency | 10 |

Produces prioritized recommendations (CRITICAL / HIGH / MEDIUM / LOW) and saves a markdown report to `~/.claude/reports/`.

```bash
maintain optimize              # Full analysis + score
```

## JSON Output

All commands support `--json` for machine-readable output:

```bash
maintain --json health         # JSON health report
maintain --json stats          # JSON usage data
maintain --json optimize       # JSON score + recommendations
```

## Safety

- **Dry run by default** -- `maintain clean` shows what it would do without acting
- **Backups before deletion** -- `--execute` moves files to `~/.claude/backups/maintain-{timestamp}/`
- **Never overwrites configs** -- `--generate-clean` writes fixed versions to `~/.claude/reports/`
- **Never logs secrets** -- API tokens are flagged as a security concern but never displayed in reports

## Who is this for?

Anyone who:

- Uses Claude Code across multiple machines (Syncthing, rsync, cloud sync)
- Has accumulated MCP servers they've experimented with
- Wants to know which of their 100+ skills are actually used
- Has never cleaned `~/.claude/` and suspects it's grown large

## Requirements

- Python 3.10+
- Claude Code installed (`~/.claude/` directory exists)

## License

MIT
