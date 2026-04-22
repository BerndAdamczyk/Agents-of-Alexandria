# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## NotebookLM Memory Skill

This repository ships a global Claude Code memory skill backed by Google NotebookLM. The skill files live in `.claude/` and must be installed once to `~/.claude/` to take effect.

### One-time setup

```bash
# 1. Install the Python library
pip install "notebooklm-py[browser]"
playwright install chromium

# 2. Authenticate with Google
notebooklm login

# 3. Install skill files globally
cp .claude/scripts/notebooklm_memory.py ~/.claude/scripts/
cp .claude/commands/memory.md           ~/.claude/commands/
cp .claude/skills/memory/SKILL.md       ~/.claude/skills/memory/
cp .claude/hooks/notebooklm-session-start.sh ~/.claude/hooks/
cp .claude/hooks/notebooklm-session-stop.sh  ~/.claude/hooks/
chmod +x ~/.claude/hooks/notebooklm-session-*.sh

# 4. Merge hooks into ~/.claude/settings.json (see .claude/hooks/ for reference config)
```

### Usage

| Command | What it does |
|---|---|
| `/memory save <text>` | Save a note (decision, finding, etc.) |
| `/memory query <question>` | Ask the notebook for past context |
| `/memory load` | Load project-relevant context at session start |
| `/memory summarize` | Save current session as a NotebookLM source |

The `SessionStart` hook loads context automatically; the `Stop` hook saves a session summary automatically once installed.

### Configuration

- **Notebook name**: `NOTEBOOKLM_NOTEBOOK` env var (default: `"Claude Code Memory"`)
- **Helper script**: `~/.claude/scripts/notebooklm_memory.py`
