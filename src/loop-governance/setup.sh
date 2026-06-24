#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Loop Governance — Installer
#  Installs from hermes-cortex repo to ~/.hermes-cortex/tools/
#
#  Usage:
#    bash setup.sh                    # full install
#    bash setup.sh --check-only      # check deps without installing
#    bash setup.sh --symlinks-only   # only create symlinks
#
#  Idempotent — safe to re-run.
# ─────────────────────────────────────────────────────────────
set -euo pipefail
VERSION="1.0.0"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RESET='\033[0m'
pass() { printf "  ${GREEN}✓${RESET} %s\n" "$1"; }
warn() { printf "  ${YELLOW}⚠${RESET} %s\n" "$1"; }
fail() { printf "  ${RED}✗${RESET} %s\n" "$1"; }
info() { printf "  ${BLUE}ℹ${RESET} %s\n" "$1"; }

CHECK_ONLY=0; SYMLINKS_ONLY=0
for arg in "$@"; do
  case "$arg" in --check-only) CHECK_ONLY=1;; --symlinks-only) SYMLINKS_ONLY=1;; esac
done

# ── Locate source ──────────────────────────────────────────
# Priority: local repo > curl pipe dir > Hermes skill dir
SOURCE_DIR=""
for dir in \
  "${HOME}/hermes-cortex/src/loop-governance" \
  "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd 2>/dev/null)" \
  "${HOME}/.hermes/skills/software-development/loop-governance/scripts"; do
  if [[ -n "$dir" && -f "${dir}/loop_scorer.py" ]]; then
    SOURCE_DIR="$dir"
    break
  fi
done

if [[ -z "$SOURCE_DIR" ]]; then
  fail "Could not find loop-governance source. Clone hermes-cortex first:"
  info "  git clone https://github.com/fleet-operator/hermes-cortex.git ~/hermes-cortex"
  exit 1
fi

# ── Install target ─────────────────────────────────────────
INSTALL_DIR="${HOME}/.hermes-cortex/tools/loop-governance"
mkdir -p "$INSTALL_DIR"

echo ""
echo "═ Loop Governance v${VERSION} — Setup ═"
echo ""

if [[ "$CHECK_ONLY" == "1" ]]; then
  echo "  Checking dependencies…"
  echo ""
fi

# ── Python ──────────────────────────────────────────────────
PYTHON=$(command -v python3 || command -v python || echo "")
if [[ -z "$PYTHON" ]]; then
  fail "Python 3 not found. Install Python 3.11+ first."
  [[ "$CHECK_ONLY" == "1" ]] && exit 1
fi
PY_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
PY_MAJOR=${PY_VER%%.*}; PY_MINOR=${PY_VER#*.}
if [[ "$PY_MAJOR" -lt 3 || ("$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11) ]]; then
  warn "Python $PY_VER found — recommend 3.11+"
else
  pass "Python $PY_VER"
fi

# ── Ollama ───────────────────────────────────────────────────
OLLAMA=$(command -v ollama || echo "")
if [[ -z "$OLLAMA" ]]; then
  # Detect macOS for brew-based install suggestion
  if [[ "$(uname)" == "Darwin" ]]; then
    fail "Ollama not found. Install with: brew install ollama"
  else
    fail "Ollama not found. Run: curl -fsSL https://ollama.com/install.sh | sh"
  fi
  if [[ "$CHECK_ONLY" == "1" ]]; then exit 1; fi
  info "Skipping Ollama install (install manually, then re-run)"
else
  pass "Ollama: $OLLAMA"
  if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    pass "Ollama server running"
    if curl -sf http://localhost:11434/api/tags | grep -q "nomic-embed-text"; then
      pass "nomic-embed-text model loaded"
    else
      warn "nomic-embed-text not pulled"
      if [[ "$CHECK_ONLY" != "1" ]]; then
        info "  Pulling nomic-embed-text…"
        ollama pull nomic-embed-text 2>&1 && pass "OK" || warn "Pull failed"
      fi
    fi
  else
    warn "Ollama server not running (try: ollama serve)"
  fi
fi

if [[ "$SYMLINKS_ONLY" == "1" ]]; then
  echo ""; echo "  ── Symlinks only ──"
fi

# ── Copy scripts to install target ─────────────────────────
if [[ "$CHECK_ONLY" != "1" ]]; then
  info "Installing to ${INSTALL_DIR}"
  cp "$SOURCE_DIR"/*.py "$INSTALL_DIR"/
  cp "$SOURCE_DIR"/*.sh "$INSTALL_DIR"/
  cp "$SOURCE_DIR"/VERSION "$INSTALL_DIR"/
  chmod +x "$INSTALL_DIR"/*.sh "$INSTALL_DIR"/*.py 2>/dev/null || true
  pass "Scripts copied ($(ls "$INSTALL_DIR"/*.py 2>/dev/null | wc -l) modules)"
fi

# ── Symlinks ────────────────────────────────────────────────
BIN_DIR="${HOME}/.local/bin"
mkdir -p "$BIN_DIR"

declare -A TOOLS
TOOLS["score_cycle.py"]="score-cycle"
TOOLS["loop_feedback.py"]="loop-feedback"
TOOLS["auto_apply.py"]="auto-apply"
TOOLS["loop_config.py"]="loop-config"

CREATED=0
for src in "${!TOOLS[@]}"; do
  dst="${TOOLS[$src]}"
  src_path="${INSTALL_DIR}/${src}"
  dst_path="${BIN_DIR}/${dst}"
  if [[ -f "$src_path" ]]; then
    ln -sf "$src_path" "$dst_path"
    chmod +x "$dst_path" 2>/dev/null || true
    pass "Symlink: ${dst}"
    CREATED=$((CREATED + 1))
  fi
done

if ! echo "$PATH" | tr ':' '\n' | grep -q "${HOME}/.local/bin"; then
  warn "${HOME}/.local/bin not in PATH — add to ~/.bashrc: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ── Database directory ─────────────────────────────────────
DB_DIR="${HOME}/.hermes/data"
mkdir -p "$DB_DIR"

# ── Config ──────────────────────────────────────────────────
CFG_PATH="${DB_DIR}/loop-governance-config.json"
if [[ ! -f "$CFG_PATH" ]]; then
  cat > "$CFG_PATH" << 'JSONEOF'
{
  "version": 1,
  "weights": {"completeness": 0.40, "quality": 0.30, "progress": 0.30},
  "thresholds": {"stop": 8.0, "loop": 5.0, "move_on": 3.0, "no_progress_score": 2.0, "no_progress_limit": 3},
  "auto_apply": {"min_confidence": 0.7, "max_threshold_delta": 1.0, "max_weight_delta": 0.10, "requires_review": true}
}
JSONEOF
  pass "Config created"
fi

# ── Crons ──────────────────────────────────────────────────
if [[ "$CHECK_ONLY" != "1" && "$SYMLINKS_ONLY" != "1" ]]; then
  if command -v hermes &>/dev/null; then
    info "Installing crons from template…"
    python3 "${SOURCE_DIR}/install-crons.py" 2>&1 | grep -E "✓|⚠|✗|created|updated" || true
  else
    info "Hermes not found — skip cron install (re-run after Hermes setup)"
  fi
fi

# ── Symlink Hermes skill → repo (so Hermes agents find it) ─
HERMES_SKILL_DIR="${HOME}/.hermes/skills/software-development/loop-governance"
if [[ -d "$HERMES_SKILL_DIR" && ! -L "$HERMES_SKILL_DIR" ]]; then
  # Only if it's a real directory, not already a symlink
  HERMES_SCRIPTS="${HERMES_SKILL_DIR}/scripts"
  if [[ ! -L "$HERMES_SCRIPTS" ]]; then
    rm -rf "$HERMES_SCRIPTS" 2>/dev/null || true
    ln -sf "$INSTALL_DIR" "$HERMES_SCRIPTS" 2>/dev/null || true
    pass "Hermes skill linked → ${INSTALL_DIR}"
  fi
fi

# ── Summary ─────────────────────────────────────────────────
echo ""
echo "  ── Summary ──"
echo ""
echo "  Source:   ${SOURCE_DIR}"
echo "  Installed: ${INSTALL_DIR}"
echo "  Symlinks: ${CREATED} in ${BIN_DIR}"
echo "  Config:   ${CFG_PATH}"
echo "  DB dir:   ${DB_DIR}/"
echo ""
echo "  Commands:"
echo "    score-cycle     Score a TDD cycle + log to DB"
echo "    loop-feedback   Accept/override decisions"
echo "    auto-apply      Auto-apply safe config patches"
echo "    loop-config     View/set runtime config"
echo "    verify.sh       Full health check"
echo "    update.sh       Update to latest version"
echo ""

if [[ "$CHECK_ONLY" == "1" ]]; then
  pass "All checks complete"
fi