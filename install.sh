#!/bin/bash
# Installs the NotebookLM memory skill for Claude Code globally.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${HOME}/.claude"

echo "Installing NotebookLM memory skill for Claude Code..."

# Create target directories
mkdir -p \
    "$CLAUDE_DIR/scripts" \
    "$CLAUDE_DIR/commands" \
    "$CLAUDE_DIR/skills/memory" \
    "$CLAUDE_DIR/hooks"

# Copy skill files
cp "$REPO_DIR/.claude/scripts/notebooklm_memory.py" "$CLAUDE_DIR/scripts/"
cp "$REPO_DIR/.claude/commands/memory.md"            "$CLAUDE_DIR/commands/"
cp "$REPO_DIR/.claude/skills/memory/SKILL.md"        "$CLAUDE_DIR/skills/memory/"
cp "$REPO_DIR/.claude/hooks/notebooklm-session-start.sh" "$CLAUDE_DIR/hooks/"
cp "$REPO_DIR/.claude/hooks/notebooklm-session-stop.sh"  "$CLAUDE_DIR/hooks/"
chmod +x "$CLAUDE_DIR/hooks/notebooklm-session-start.sh" \
         "$CLAUDE_DIR/hooks/notebooklm-session-stop.sh"

# Write install config for auto-update + version marker
INSTALLED_HASH=$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo "unknown")
cat > "$CLAUDE_DIR/scripts/.notebooklm-memory-config" <<EOF
NOTEBOOKLM_MEMORY_REPO="$REPO_DIR"
NOTEBOOKLM_MEMORY_HASH="$INSTALLED_HASH"
NOTEBOOKLM_MEMORY_SKILL_VERSION="2"
EOF

# Stub team-sharing config (opt-in; edit to add collaborators)
TEAM_CONFIG="$CLAUDE_DIR/notebooklm-team.json"
if [ ! -f "$TEAM_CONFIG" ]; then
    cat > "$TEAM_CONFIG" <<'EOF'
{
  "emails": [],
  "role": "editor"
}
EOF
    echo "Edit $TEAM_CONFIG to enable team sharing."
fi

# Merge hooks and permissions into ~/.claude/settings.json
SETTINGS="$CLAUDE_DIR/settings.json"
if [ ! -f "$SETTINGS" ]; then
    echo '{}' > "$SETTINGS"
fi

python3 - "$SETTINGS" <<'PYEOF'
import json, sys

path = sys.argv[1]
with open(path) as f:
    cfg = json.load(f)

cfg.setdefault("hooks", {})
cfg.setdefault("permissions", {})
cfg["permissions"].setdefault("allow", [])

# SessionStart hook
start_hook = {"hooks": [{"type": "command", "command": "~/.claude/hooks/notebooklm-session-start.sh"}]}
cfg["hooks"].setdefault("SessionStart", [])
if start_hook not in cfg["hooks"]["SessionStart"]:
    cfg["hooks"]["SessionStart"].append(start_hook)

# Stop hook
stop_hook = {"matcher": "", "hooks": [{"type": "command", "command": "~/.claude/hooks/notebooklm-session-stop.sh"}]}
cfg["hooks"].setdefault("Stop", [])
if stop_hook not in cfg["hooks"]["Stop"]:
    cfg["hooks"]["Stop"].append(stop_hook)

# Permission glob for the helper script.
# The trailing '*' already covers every new subcommand (save, query, load,
# summarize, list-topics, share, merge) — no change needed at upgrade time.
perm = "Bash(python3 ~/.claude/scripts/notebooklm_memory.py*)"
if perm not in cfg["permissions"]["allow"]:
    cfg["permissions"]["allow"].append(perm)

with open(path, "w") as f:
    json.dump(cfg, f, indent=4)
    f.write("\n")

print(f"Updated {path}")
PYEOF

# Install Python dependency
if ! python3 -c "import notebooklm" 2>/dev/null; then
    echo "Installing notebooklm-py..."
    pip install "notebooklm-py[browser]" --quiet
    python3 -m playwright install chromium 2>/dev/null || true
fi

echo ""
echo "Done. Next step: authenticate with Google."
echo "  notebooklm login"
echo ""
echo "Then try:"
echo "  python3 ~/.claude/scripts/notebooklm_memory.py list-topics"
echo "  python3 ~/.claude/scripts/notebooklm_memory.py save --topic=demo 'Hello topic-partitioned memory'"
echo ""
echo "What's new in v2 (topic-partitioned):"
echo "  - Each topic is its own NotebookLM notebook — one library, many topics."
echo "  - Claude picks or invents the topic via 'list-topics' before saving."
echo "  - Default merge threshold: 40 sources (override with NOTEBOOKLM_MERGE_AT)."
echo "  - Opt-in env vars: NOTEBOOKLM_LOAD_ON_START, NOTEBOOKLM_CROSS_TOPIC_QUERY."
echo "  - Team sharing via $TEAM_CONFIG (auto-invite on notebook create)."
echo "  - NOTEBOOKLM_NOTEBOOK is removed; legacy notebook content is not migrated."
