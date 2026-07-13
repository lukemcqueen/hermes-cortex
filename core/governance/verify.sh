#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Loop Governance — Health Verification Script
#
#  Checks all components are installed, running, and working.
#  Returns exit code 0 if everything is healthy.
#
#  Usage:
#    bash verify.sh              # full health check
#    bash verify.sh --quick      # skip embed test (faster)
#    bash verify.sh --json       # machine-readable output
#    bash verify.sh --fix        # auto-fix common issues
# ─────────────────────────────────────────────────────────────
set -euo pipefail
VERSION="1.0.0"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RESET='\033[0m'

pass() { RESULTS+=("pass:$1"); [[ "$JSON" != "1" ]] && printf "  ${GREEN}✓${RESET} %s\n" "$1"; return 0; }
warn() { RESULTS+=("warn:$1"); [[ "$JSON" != "1" ]] && printf "  ${YELLOW}⚠${RESET} %s\n" "$1"; FAILED=1; }
fail() { RESULTS+=("fail:$1"); [[ "$JSON" != "1" ]] && printf "  ${RED}✗${RESET} %s\n" "$1"; FAILED=1; }
info() { [[ "$JSON" != "1" ]] && printf "  ${BLUE}ℹ${RESET} %s\n" "$1"; return 0; }

RESULTS=()
FAILED=0
QUICK=0
JSON=0
FIX=0

for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=1 ;;
    --json) JSON=1 ;;
    --fix) FIX=1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd 2>/dev/null)"

# Only print header when not in JSON mode
if [[ "$JSON" != "1" ]]; then
  echo ""
  echo "═ Loop Governance v${VERSION} — Health Check ═"
  echo ""
fi

# ── 1. Python ──────────────────────────────────────────────
info "1. Python"
PYTHON=$(command -v python3 || command -v python || echo "")
if [[ -z "$PYTHON" ]]; then
  fail "Python 3 not found"
else
  PY_VER=$("$PYTHON" --version 2>&1)
  pass "$PY_VER"
fi

# ── 2. Scripts directory ────────────────────────────────────
info "2. Scripts"
if [[ ! -d "$SCRIPT_DIR" ]]; then
  fail "Scripts directory not found at $SCRIPT_DIR"
elif [[ ! -f "${SCRIPT_DIR}/loop_scorer.py" ]]; then
  fail "loop_scorer.py not found in $SCRIPT_DIR"
else
  pass "Scripts present ($SCRIPT_DIR)"

  # Count scripts
  SCRIPTS=$(find "$SCRIPT_DIR" -maxdepth 1 -name '*.py' | wc -l)
  info "  ${SCRIPTS} Python modules"
fi

# ── 3. Symlinks ─────────────────────────────────────────────
info "3. Symlinks"
BIN_DIR="${HOME}/.local/bin"
ALL_SYMLINKS=("score-cycle" "loop-feedback" "auto-apply" "loop-config")
MISSING_SYMLINKS=()
for cmd in "${ALL_SYMLINKS[@]}"; do
  TARGET="${BIN_DIR}/${cmd}"
  if [[ -L "$TARGET" && -f "$TARGET" ]]; then
    pass "~/.local/bin/${cmd}"
  else
    MISSING_SYMLINKS+=("$cmd")
    if [[ "$FIX" == "1" && -f "${SCRIPT_DIR}/${cmd}.py" ]]; then
      ln -sf "${SCRIPT_DIR}/${cmd}.py" "$TARGET"
      chmod +x "$TARGET" 2>/dev/null || true
      pass "~/.local/bin/${cmd} (fixed)"
    else
      warn "~/.local/bin/${cmd} — missing symlink"
    fi
  fi
done

# ── 4. PATH ──────────────────────────────────────────────────
info "4. PATH"
if ! echo "$PATH" | tr ':' '\n' | grep -q "${HOME}/.local/bin"; then
  warn "${HOME}/.local/bin not in PATH"
else
  pass "${HOME}/.local/bin in PATH"
fi

# ── 5. Ollama ───────────────────────────────────────────────
info "5. Ollama"
OLLAMA=$(command -v ollama || echo "")
if [[ -z "$OLLAMA" ]]; then
  fail "Ollama not found"
else
  pass "Ollama binary: $OLLAMA"
  if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    pass "Ollama server responding on :11434"
    if curl -sf http://localhost:11434/api/tags | grep -q "nomic-embed-text:v1.5"; then
      pass "nomic-embed-text:v1.5 model loaded"
    else
      warn "nomic-embed-text:v1.5 not pulled"
      if [[ "$FIX" == "1" ]]; then
        info "  Pulling nomic-embed-text:v1.5…"
        ollama pull nomic-embed-text:v1.5 2>&1 && pass "nomic-embed-text:v1.5 pulled" || warn "  Pull failed"
      fi
    fi
  else
    warn "Ollama server not responding on :11434"
    if [[ "$FIX" == "1" ]]; then
      info "  Starting Ollama…"
      ollama serve &
      sleep 2
      if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        pass "Ollama started"
      else
        warn "  Could not start Ollama automatically"
      fi
    fi
  fi
fi

# ── 6. Scoring test (skip with --quick) ────────────────────
if [[ "$QUICK" != "1" ]]; then
  info "6. Scoring test"
  if [[ -f "${SCRIPT_DIR}/loop_scorer.py" ]]; then
    SCORE_RESULT=$("$PYTHON" "${SCRIPT_DIR}/loop_scorer.py" 2>&1 | tail -1)
    if echo "$SCORE_RESULT" | grep -q "All tests passed"; then
      pass "Scoring function works"
    else
      warn "Scoring test: $SCORE_RESULT"
    fi
  fi

  # Lightning test: score a tiny cycle
  info "7. Quick score cycle"
  if [[ -f "${BIN_DIR}/score-cycle" ]] || [[ -f "${SCRIPT_DIR}/score_cycle.py" ]]; then
    SCORE_CMD="${BIN_DIR}/score-cycle"
    [[ ! -f "$SCORE_CMD" ]] && SCORE_CMD="$PYTHON ${SCRIPT_DIR}/score_cycle.py"
    CYCLE_RESULT=$($SCORE_CMD --task health-check --cycle 0 --code "def test(): pass" --json 2>&1 || echo "FAILED")
    if echo "$CYCLE_RESULT" | grep -q "logged.*true"; then
      CYCLE_ID=$(echo "$CYCLE_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cycle_id','?'))" 2>/dev/null)
      pass "  Score + log: cycle #${CYCLE_ID}"
    else
      warn "  Score cycle failed: ${CYCLE_RESULT:0:80}"
    fi
    # Clean up test cycle
    "$PYTHON" -c "
from $SCRIPT_DIR.loop_db import LoopDB; d=LoopDB();
d.conn.execute('DELETE FROM loop_cycles WHERE task_id=?',('health-check',));
d.conn.commit(); d.close()
" 2>/dev/null || true
  fi
fi

# ── 8. Database ─────────────────────────────────────────────
info "8. Database"
DB_PATH="${HOME}/.hermes-cortex/state/loop-governance.db"
if [[ -f "$DB_PATH" ]]; then
  DB_SIZE=$(du -h "$DB_PATH" | cut -f1)
  pass "SQLite database: $DB_PATH ($DB_SIZE)"
else
  info "Database will be created on first score cycle"
fi

# ── 9. Config ───────────────────────────────────────────────
info "9. Config"
CFG_PATH="${HOME}/.hermes-cortex/state/loop-governance-config.json"
if [[ -f "$CFG_PATH" ]]; then
  CFG_WEIGHTS=$("$PYTHON" -c "
import json
with open('${CFG_PATH}') as f:
    c = json.load(f)
w = c.get('weights', {})
print(f'completeness={w.get(\"completeness\",\"?\")}, quality={w.get(\"quality\",\"?\")}, progress={w.get(\"progress\",\"?\")}')
" 2>/dev/null)
  pass "Config: $CFG_WEIGHTS"
else
  warn "Config file not found"
  if [[ "$FIX" == "1" && -f "${SCRIPT_DIR}/loop_config.py" ]]; then
    "$PYTHON" "${SCRIPT_DIR}/loop_config.py" >/dev/null 2>&1 || true
    pass "Config created (defaults)"
  fi
fi

# ── Summary ──────────────────────────────────────────────────
if [[ "$JSON" != "1" ]]; then
  echo ""
  echo "  ── Results ──"
fi
PASS_COUNT=$(printf '%s\n' "${RESULTS[@]}" | grep -c "^pass:" || true)
WARN_COUNT=$(printf '%s\n' "${RESULTS[@]}" | grep -c "^warn:" || true)
FAIL_COUNT=$(printf '%s\n' "${RESULTS[@]}" | grep -c "^fail:" || true)
if [[ "$JSON" != "1" ]]; then
  echo "  ${GREEN}${PASS_COUNT} passed${RESET}, ${YELLOW}${WARN_COUNT} warnings${RESET}, ${RED}${FAIL_COUNT} failed${RESET}"
  echo ""
fi

if [[ "$JSON" == "1" ]]; then
  # Write results to a temp file for reliable Python parsing
  TMP_RESULTS=$(mktemp)
  printf '%s\n' "${RESULTS[@]}" > "$TMP_RESULTS"
  python3 -c "
import json
with open('$TMP_RESULTS') as f:
    lines = [l.strip() for l in f if l.strip()]
results = []
for line in lines:
    parts = line.split(':', 1)
    if len(parts) == 2:
        results.append({'status': parts[0], 'check': parts[1]})
print(json.dumps({'version': '$VERSION', 'passed': $PASS_COUNT, 'warnings': $WARN_COUNT, 'failed': $FAIL_COUNT, 'checks': results}, indent=2))
" 2>/dev/null || echo "{}"
  rm -f "$TMP_RESULTS"
fi

exit "$FAILED"