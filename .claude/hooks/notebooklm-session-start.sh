#!/bin/bash
# Load NotebookLM memory context at session start.
# Skips silently if notebooklm-py is not installed or not authenticated.
set -euo pipefail

if ! python3 -c "import notebooklm" 2>/dev/null; then
    exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

python3 ~/.claude/scripts/notebooklm_memory.py load --project "$PROJECT_DIR" 2>/dev/null || true
