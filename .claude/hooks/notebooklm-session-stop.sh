#!/bin/bash
# Save session summary to NotebookLM when Claude stops.
# Reads transcript_path from stdin JSON. Skips silently on any error.
export CLAUDE_HOOK=1
set -euo pipefail

# Resolve Python: env override → notebooklm venv → system python3
PYTHON3="${NOTEBOOKLM_PYTHON:-}"
if [ -z "$PYTHON3" ]; then
    if [ -x "$HOME/.notebooklm-env/bin/python3" ]; then
        PYTHON3="$HOME/.notebooklm-env/bin/python3"
    else
        PYTHON3="python3"
    fi
fi

if ! "$PYTHON3" -c "import notebooklm" 2>/dev/null; then
    exit 0
fi

# Read transcript path from hook stdin JSON
STDIN_DATA=$(cat)
TRANSCRIPT_PATH=$(echo "$STDIN_DATA" | "$PYTHON3" -c "
import json, sys
data = json.load(sys.stdin)
print(data.get('transcript_path', ''))
" 2>/dev/null || true)

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
    exit 0
fi

"$PYTHON3" ~/.claude/scripts/notebooklm_memory.py summarize "$TRANSCRIPT_PATH" 2>/dev/null || true
