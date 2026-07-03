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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd 2>/dev/null || echo "")"

# Check if running from repo root
if [[ ! -f "${SCRIPT_DIR}/src/loop-governance/setup.sh" ]]; then
  echo "Could not find loop-governance setup script."
  echo "Run this from the hermes-cortex repo root."
  echo ""
  echo "  git clone https://github.com/fleet-operator/hermes-cortex.git"
  echo "  cd hermes-cortex && bash quick-start.sh"
  exit 1
fi

echo "  Step 1: Install loop-governance tools…"
bash "${SCRIPT_DIR}/src/loop-governance/setup.sh" 2>&1 | grep -E "✓|⚠|✗|setup" | head -10

echo ""
echo "  Step 2: Verify installation…"
bash "${SCRIPT_DIR}/src/loop-governance/verify.sh" --quick 2>&1 | tail -3

echo ""
echo "╔═══════════════════════════════════════════════╗"
echo "║    Ready!                                     ║"
echo "╚═══════════════════════════════════════════════╝"
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
    src="${SCRIPT_DIR}/src/skills/software-development/${skill}"
    dst="${SKILLS_DIR}/${skill}"
    if [[ -d "$src" && ! -d "$dst" ]]; then
      cp -r "$src" "$dst"
      echo "  ✓ Installed skill: ${skill}"
    fi
  done
fi

echo ""