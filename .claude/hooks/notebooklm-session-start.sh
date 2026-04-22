#!/bin/bash
# Load NotebookLM memory context at session start + auto-update check.
# Skips silently if notebooklm-py is not installed or not authenticated.
set -euo pipefail

if ! python3 -c "import notebooklm" 2>/dev/null; then
    exit 0
fi

# --- Auto-update check (max once per 24h) ---
CONFIG="$HOME/.claude/scripts/.notebooklm-memory-config"
LAST_CHECK="$HOME/.claude/scripts/.notebooklm-memory-last-check"

if [ -f "$CONFIG" ]; then
    # shellcheck source=/dev/null
    source "$CONFIG"

    NOW=$(date +%s)
    LAST=0
    [ -f "$LAST_CHECK" ] && LAST=$(cat "$LAST_CHECK")

    if [ $(( NOW - LAST )) -gt 86400 ] && [ -d "${NOTEBOOKLM_MEMORY_REPO:-}/.git" ]; then
        echo "$NOW" > "$LAST_CHECK"

        git -C "$NOTEBOOKLM_MEMORY_REPO" fetch origin --quiet 2>/dev/null || true

        REMOTE_HASH=$(git -C "$NOTEBOOKLM_MEMORY_REPO" rev-parse origin/HEAD 2>/dev/null || echo "")

        if [ -n "$REMOTE_HASH" ] && [ "$REMOTE_HASH" != "${NOTEBOOKLM_MEMORY_HASH:-}" ]; then
            echo "[NotebookLM Memory] Update available — installing..."
            git -C "$NOTEBOOKLM_MEMORY_REPO" pull --quiet 2>/dev/null || true
            bash "$NOTEBOOKLM_MEMORY_REPO/install.sh" 2>/dev/null && \
                echo "[NotebookLM Memory] Updated to $(git -C "$NOTEBOOKLM_MEMORY_REPO" rev-parse --short HEAD)"
        fi
    fi
fi

# --- Load project context ---
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
python3 ~/.claude/scripts/notebooklm_memory.py load --project "$PROJECT_DIR" 2>/dev/null || true
