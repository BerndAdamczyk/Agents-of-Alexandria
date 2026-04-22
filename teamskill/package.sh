#!/bin/bash
# Creates notebooklm-memory.zip for upload to the Claude Team admin panel.
# Admin panel: claude.ai → Organization settings → Skills → Add
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$DIR/notebooklm-memory.zip"

cd "$DIR"
rm -f "$OUT"
zip -r "$OUT" notebooklm-memory/
echo "Created: $OUT"
echo "Upload at: claude.ai → Organization settings → Skills → Add"
