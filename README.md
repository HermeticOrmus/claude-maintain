<p align="center">
  <img src="https://ormus.solutions/mascot/pixellab_liquid_to_spiral.gif" alt="claude-maintain" width="128" style="image-rendering: pixelated;" />
</p>

<h1 align="center">claude-maintain</h1>

<p align="center">
  <em>Environment maintenance CLI for Claude Code — clean sessions, manage disk, optimize ~/.claude/</em>
</p>

<p align="center">
  <a href="https://github.com/HermeticOrmus/claude-maintain/stargazers"><img src="https://img.shields.io/github/stars/HermeticOrmus/claude-maintain?style=flat-square&color=aa8142" alt="Stars" /></a>
  <a href="https://github.com/HermeticOrmus/claude-maintain/blob/main/LICENSE"><img src="https://img.shields.io/github/license/HermeticOrmus/claude-maintain?style=flat-square&color=aa8142" alt="License" /></a>
  <a href="https://github.com/HermeticOrmus/claude-maintain/commits"><img src="https://img.shields.io/github/last-commit/HermeticOrmus/claude-maintain?style=flat-square&color=aa8142" alt="Last Commit" /></a>
  <img src="https://img.shields.io/badge/Claude_Code-aa8142?style=flat-square&logo=anthropic&logoColor=white" alt="Claude Code" />
</p>

---
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

---

## Part of the Libre Open-Source Stack for Claude Code

This repository is part of a growing family of open-source toolkits for Claude Code.

### Libre suite — comprehensive plugin bundles

- [LibreUIUX-Claude-Code](https://github.com/HermeticOrmus/LibreUIUX-Claude-Code) — UI/UX development (152 agents, 70 plugins, 76 commands, 74 skills)
- [LibreArch-Claude-Code](https://github.com/HermeticOrmus/LibreArch-Claude-Code) — Software architecture and system design
- [LibreCopy-Claude-Code](https://github.com/HermeticOrmus/LibreCopy-Claude-Code) — Technical writing and documentation engineering
- [LibreDevOps-Claude-Code](https://github.com/HermeticOrmus/LibreDevOps-Claude-Code) — DevOps engineering and infrastructure automation
- [LibreEmbed-Claude-Code](https://github.com/HermeticOrmus/LibreEmbed-Claude-Code) — Embedded systems, firmware, and IoT development
- [LibreFinTech-Claude-Code](https://github.com/HermeticOrmus/LibreFinTech-Claude-Code) — Financial technology development
- [LibreGEO-Claude-Code](https://github.com/HermeticOrmus/LibreGEO-Claude-Code) — AI-search optimization (ChatGPT, Perplexity, Gemini, Google AI Overviews)
- [LibreGameDev-Claude-Code](https://github.com/HermeticOrmus/LibreGameDev-Claude-Code) — Game development across Godot, Unity, Unreal
- [LibreMLOps-Claude-Code](https://github.com/HermeticOrmus/LibreMLOps-Claude-Code) — ML engineering and AI operations
- [LibreMobileDev-Claude-Code](https://github.com/HermeticOrmus/LibreMobileDev-Claude-Code) — Mobile app development (Flutter, React Native, native iOS, native Android)
- [LibreSecOps-Claude-Code](https://github.com/HermeticOrmus/LibreSecOps-Claude-Code) — Security operations

### Skills mini-repos — single CLAUDE.md drop-ins

- [vibe-engineer-skills](https://github.com/HermeticOrmus/vibe-engineer-skills) — Direct AI codegen well (hypothesis → scope → validate → reject working-but-wrong)
- [markdown-discipline-skills](https://github.com/HermeticOrmus/markdown-discipline-skills) — Strip AI-slop from markdown (no em dashes, no marketing fluff)
- [shell-safety-skills](https://github.com/HermeticOrmus/shell-safety-skills) — `set -euo pipefail` discipline + 15 failure-mode examples
- [commit-standard-skills](https://github.com/HermeticOrmus/commit-standard-skills) — Ormus Commit Standard v1.0 + commit-msg hook + commitlint
- [unwoke-skills](https://github.com/HermeticOrmus/unwoke-skills) — Strip AI theater (ten sins to eliminate, symmetric engagement)
- [python-conventions-skills](https://github.com/HermeticOrmus/python-conventions-skills) — Modern Python 3.11+ (types, pathlib, async, ruff, mypy, uv)
- [typescript-conventions-skills](https://github.com/HermeticOrmus/typescript-conventions-skills) — TypeScript strict mode, discriminated unions, Result types
- [hermetic-laws-skills](https://github.com/HermeticOrmus/hermetic-laws-skills) — Seven Hermetic Principles applied to engineering
- [riper-workflow-skills](https://github.com/HermeticOrmus/riper-workflow-skills) — Research / Innovate / Plan / Execute / Review systematic dev
- [six-day-cycle-skills](https://github.com/HermeticOrmus/six-day-cycle-skills) — Sustainable shipping cadence with mandatory rest
- [token-optimization-skills](https://github.com/HermeticOrmus/token-optimization-skills) — Claude Code token + context optimization
- [osint-skills](https://github.com/HermeticOrmus/osint-skills) — OSINT research methodology (multi-wave investigative spiral)
- [calcinate-skills](https://github.com/HermeticOrmus/calcinate-skills) — Stage 1 of the Magnum Opus (burn project bloat)
- [claude-md-overhaul-skills](https://github.com/HermeticOrmus/claude-md-overhaul-skills) — Audit CLAUDE.md and MEMORY.md against caps
- [session-handoff-skills](https://github.com/HermeticOrmus/session-handoff-skills) — Session handoff + pickup discipline
- [naming-skills](https://github.com/HermeticOrmus/naming-skills) — Product naming methodology (mine the brand's vocabulary)
- [magnum-opus-skills](https://github.com/HermeticOrmus/magnum-opus-skills) — Seven-stage alchemy applied to project transformation

### Template source

- [andrej-karpathy-skills](https://github.com/HermeticOrmus/andrej-karpathy-skills) — the canonical single-file CLAUDE.md pattern (fork of jiayuan_jy's original)

Star the family, not just one — that's how the suite stays coherent.
