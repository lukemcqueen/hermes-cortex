#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
PROJECT_ROOT="$(pwd)"
echo "Repo root: $REPO_ROOT"
cd "$PROJECT_ROOT"
echo "Project root: $PROJECT_ROOT"
echo

rm -rf .agentkore/runtime/*
touch .agentkore/runtime/.gitkeep
echo "AgentKore runtime cleared."
