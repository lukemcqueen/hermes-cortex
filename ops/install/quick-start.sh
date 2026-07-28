#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — Quick Start (10 seconds)
#
#  Installs the bare minimum to use TDD scoring and skills:
#    1. Loop-governance tools (score-cycle, loop-feedback)
#    2. Ollama + nomic-embed-text:v1.5 (for AI-powered scoring)
#
#  Usage:
#    bash quick-start.sh
#
#  For the full Hermes Cortex experience (brain, dashboard,
#  offline knowledge), run: bash install.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

echo ""
echo "╔═══════════════════════════════════════════════╗"
echo "║    Hermes Cortex — Quick Start               ║"
echo "║    TDD scoring + skills in 10 seconds        ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""

echo ""
echo "  Loop-governance CLI tools have been replaced by MCP-based governance."
echo "  See docs/templates/AGENTS-loop-governance.md for current workflow:"
echo "    begin_change → work → cycle_query → feedback_accept/override → end_change"
echo ""
echo "  Quick-start for scoring: the pre-commit hook auto-creates cycles."
echo ""
echo "  Commands:"
echo "    score-cycle --help"
echo "    loop-feedback --help"
echo "    auto-apply --help"
echo ""
echo "  Next steps:"
echo "    bash install.sh     Full install (brain, dashboard, offline)"
echo "    cat AGENTS.md       Agent guidelines"
echo ""

# Optionally install core skills too
if command -v hermes &>/dev/null; then
  echo "  Hermes Agent detected — installing core skills…"
  SKILLS_DIR="${HERMES_HOME:-${HOME}/.hermes}/skills/software-development"
  mkdir -p "$SKILLS_DIR"
  for skill in change-test-loop lesson-aware-agent systematic-debugging memory-architecture; do
    src="${SCRIPT_DIR}/../skills/software-development/${skill}"
    dst="${SKILLS_DIR}/${skill}"
    if [[ -d "$src" && ! -d "$dst" ]]; then
      cp -r "$src" "$dst"
      echo "  ✓ Installed skill: ${skill}"
    fi
  done
fi

echo ""