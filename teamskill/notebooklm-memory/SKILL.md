---
name: notebooklm-memory
description: Persistent team memory using Google NotebookLM. Save important decisions, architectural choices, and session context so they survive across conversations. TRIGGER when: the user asks to remember something, references a past decision not in current context, starts a new project session, or explicitly uses /notebooklm-memory.
allowed-tools: Bash(notebooklm*)
---

# NotebookLM Team Memory

Provides persistent memory across Claude conversations using Google NotebookLM as the knowledge store. Important decisions, findings, and session summaries are saved as notes or sources and can be recalled at any time.

## Prerequisites

The execution environment must have `notebooklm-py` installed and authenticated:

```bash
pip install "notebooklm-py[browser]"
notebooklm login
```

Verify with: `notebooklm status`

The default notebook is named **"Claude Code Memory"**. Override by setting the `NOTEBOOKLM_NOTEBOOK` environment variable.

## Operations

### Save a note
Use when the user asks to remember a decision, finding, or piece of context.

```bash
NOTEBOOK_ID=$(notebooklm list --json | python3 -c "
import json,sys
nbs = json.load(sys.stdin).get('notebooks', [])
target = next((n for n in nbs if n['title'] == 'Claude Code Memory'), None)
print(target['id'] if target else '')
")

# Create the notebook if it doesn't exist yet
if [ -z "$NOTEBOOK_ID" ]; then
    NOTEBOOK_ID=$(notebooklm create "Claude Code Memory" --json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
fi

notebooklm note create "$(echo "$TEXT")" -t "Note [$(date '+%Y-%m-%d %H:%M')]" -n "$NOTEBOOK_ID"
```

### Query past context
Use when the user references past decisions or asks what was previously discussed.

```bash
notebooklm ask "$QUESTION" -n "$NOTEBOOK_ID"
```

### Load project context
Use at the start of a session to surface relevant past notes.

```bash
notebooklm ask "Summarize the most recent notes, decisions, and context for project: $PROJECT_NAME" -n "$NOTEBOOK_ID"
```

### Save session summary
Use at the end of a productive session to persist key outcomes.

```bash
notebooklm source add "$SUMMARY_TEXT" -n "$NOTEBOOK_ID"
```
(Saves as a source so it becomes part of the searchable knowledge base.)

## Workflow

1. **On session start**: If the user mentions a project, load context with a `notebooklm ask` query.
2. **During session**: After important decisions, call `notebooklm note create` to save them without asking the user.
3. **On session end** (if requested): Save a brief summary via `notebooklm source add`.

## Error Handling

| Error | Resolution |
|---|---|
| `auth error` | Run `notebooklm login` to re-authenticate |
| `no notebook context` | Always use `-n $NOTEBOOK_ID` — never rely on implicit context |
| `rate limit` | Wait 5 minutes and retry |
