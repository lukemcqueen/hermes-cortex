#!/usr/bin/env bash
set -euo pipefail

echo "== AgentKore Archive Session =="
SRC=".agentkore/sessions/current.md"
if [ ! -f "$SRC" ]; then
  echo "No current session to archive: $SRC"
  exit 0
fi
mkdir -p .agentkore/sessions/archive
DEST=".agentkore/sessions/archive/$(date +%Y-%m-%d-%H%M)-session.md"
cp "$SRC" "$DEST"
echo "Archived to $DEST"
