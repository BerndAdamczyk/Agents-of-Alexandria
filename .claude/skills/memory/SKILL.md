---
name: memory
description: Persistent memory using Google NotebookLM. TRIGGER this skill when: starting work on an unfamiliar project (load context), making an architectural or product decision (save it), completing a significant task (save a summary), or when the user references past decisions that aren't in the current context (query). Use sparingly — only for genuinely important context worth persisting across sessions.
---

# NotebookLM Memory Skill

Provides persistent memory across Claude Code sessions via Google NotebookLM.

## When to Use

- **load**: At the start of a session on a project you haven't recently worked on
- **save**: After making an architectural decision, choosing a library, or resolving a non-obvious bug
- **query**: When context from a previous session is needed (e.g. "what did we decide about auth?")
- **summarize**: At the end of a productive session with important decisions or completed features

## Commands

All commands use the helper script `~/.claude/scripts/notebooklm_memory.py`.

### Load context for a project
```bash
python3 ~/.claude/scripts/notebooklm_memory.py load --project "$PWD"
```

### Save a note
```bash
python3 ~/.claude/scripts/notebooklm_memory.py save "We chose JWT over sessions because the API is stateless and needs mobile support"
```

### Query past context
```bash
python3 ~/.claude/scripts/notebooklm_memory.py query "What database schema decisions were made?"
```

### Save session summary
Find the current session transcript (most recently modified `.jsonl` in `~/.claude/projects/`), then:
```bash
python3 ~/.claude/scripts/notebooklm_memory.py summarize /path/to/transcript.jsonl
```

## Configuration

- **Notebook name**: Set via `NOTEBOOKLM_NOTEBOOK` env var (default: `"Claude Code Memory"`)
- **Auth**: Run `notebooklm login` once to authenticate with Google
- **Install**: `pip install 'notebooklm-py[browser]' && playwright install chromium`
