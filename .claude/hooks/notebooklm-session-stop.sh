#!/bin/bash
# Save session summary to NotebookLM when Claude stops.
# Reads transcript_path from stdin JSON. Skips silently on any error.
set -euo pipefail

if ! python3 -c "import notebooklm" 2>/dev/null; then
    exit 0
fi

# Read transcript path from hook stdin JSON
STDIN_DATA=$(cat)
TRANSCRIPT_PATH=$(echo "$STDIN_DATA" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(data.get('transcript_path', ''))
" 2>/dev/null || true)

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
    exit 0
fi

python3 ~/.claude/scripts/notebooklm_memory.py summarize "$TRANSCRIPT_PATH" 2>/dev/null || true
