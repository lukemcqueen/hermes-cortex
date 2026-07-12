#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  change-validate.sh — Pre-commit change validation
#
#  Called by pre-commit-score hook on every git commit. Checks
#  staged files for common issues BEFORE they hit the repo.
#
#  Warn-only — does NOT block the commit. The block comes from
#  the change-checklist skill that agents run before end_change().
#
#  Checks:
#   1. Script syntax (bash -n, python compile)
#   2. OS-agnostic paths (no hardcoded /etc/nginx/ without brew_dir)
#   3. Registration consistency (files in deploy/nginx/ → cortex-update.sh)
#   4. Unsubstituted placeholders in templates
#   5. Multi-OS markers for platform-specific code
# ─────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
error() { echo -e "${RED}❌${RESET} $*"; }
warn()  { echo -e "${YELLOW}⚠${RESET} $*"; }
pass()  { echo -e "${GREEN}✅${RESET} $*"; }
info()  { echo -e "${CYAN}ℹ${RESET} $*"; }

# ── Config ──────────────────────────────────────────────────
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")
CORTEX_UPDATE="${REPO_ROOT}/ops/scripts/cortex-update.sh"

# Get staged files (no deletions, no binary/lock)
STAGED=$(git diff --cached --name-only --diff-filter=ACMR \
  | grep -v '\.lock$\|package-lock\.json\|yarn\.lock\|pnpm-lock\.yaml' \
  | grep -v '\.svg$\|\.png$\|\.jpg$\|\.jpeg$\|\.gif$\|\.ico$\|\.woff2?$' \
  || true)

if [[ -z "$STAGED" ]]; then
  exit 0
fi

HAS_ISSUES=0

# ── 1. Syntax check ─────────────────────────────────────────
for f in $STAGED; do
  case "$f" in
    *.sh)
      bash -n "$f" 2>/dev/null && pass "Syntax OK: $f" || {
        error "Syntax error in $f (bash -n failed)"
        HAS_ISSUES=1
      }
      ;;
    *.py)
      python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null && \
        pass "Syntax OK: $f" || {
        error "Syntax error in $f (python compile failed)"
        HAS_ISSUES=1
      }
      ;;
    *.yaml|*.yml)
      python3 -c "import yaml; yaml.safe_load(open('$f'))" 2>/dev/null && \
        pass "Syntax OK: $f" || {
        warn "YAML parse issue in $f (python3 yaml.safe_load failed)"
        HAS_ISSUES=1
      }
      ;;
  esac
done

# ── 2. OS-agnostic path check ───────────────────────────────
# Flag any script that hardcodes /etc/nginx/ without including
# ${brew_dir} or os-config.sh to make it OS-aware
for f in $STAGED; do
  case "$f" in
    *.sh|*.py)
      if grep -q '/etc/nginx/' "$f" 2>/dev/null; then
        if ! grep -q 'brew_dir\|NGINX_BREW_DIR\|NGINX_DIR\|os-config\|CORTEX_OS\|IS_MAC\|IS_LINUX' "$f" 2>/dev/null; then
          warn "$f uses /etc/nginx/ but lacks brew_dir/os-config.sh — macOS incompatible"
          HAS_ISSUES=1
        else
          pass "OS-aware path: $f"
        fi
      fi
      if grep -q '/opt/homebrew/etc/nginx' "$f" 2>/dev/null; then
        if ! grep -q 'CORTEX_OS\|IS_MAC\|uname\|Darwin' "$f" 2>/dev/null; then
          warn "$f uses /opt/homebrew path but no OS guard — Linux incompatible"
          HAS_ISSUES=1
        else
          pass "OS-guarded path: $f"
        fi
      fi
      ;;
  esac
done

# ── 3. Registration consistency ─────────────────────────────
# If a deployable file was added/modified, check it's registered
if [[ -f "$CORTEX_UPDATE" ]]; then
  for f in $STAGED; do
    # Skip files not in deploy/ or ops/scripts/
    case "$f" in
      deploy/*|ops/scripts/*)
        basename_f=$(basename "$f")
        if ! grep -q "$basename_f" "$CORTEX_UPDATE" 2>/dev/null; then
          warn "File $f is not registered in cortex-update.sh register() —"
          info "  Add: register \"$f\" \"\${CORTEX_DEPLOY_HOME}/scripts/$(basename $f)\""
          HAS_ISSUES=1
        fi
        ;;
    esac
  done
fi

# ── 4. Unsubstituted placeholders ───────────────────────────
# Check that template files don't contain stale placeholders
for f in $STAGED; do
  case "$f" in
    deploy/nginx/hermes-services.conf)
      # The template itself MUST have placeholders — that's normal
      pass "Template placeholders expected: $f"
      ;;
    *.conf)
      if grep -qE '__[A-Z_]+__' "$f" 2>/dev/null; then
        warn "Deployed config $f has unsubstituted placeholders"
        HAS_ISSUES=1
      fi
      ;;
  esac
done

# ── 5. Multi-role awareness check ────────────────────────────
# Check scripts that hardcode machine-specific paths
for f in $STAGED; do
  case "$f" in
    *.sh|*.py)
      if grep -qE '/home/(luke|moses|joseph|esther)/' "$f" 2>/dev/null; then
        warn "$f has hardcoded /home/<user>/ path — use \$HOME or Path.home()"
        HAS_ISSUES=1
      fi
      if grep -qE "'/root/" "$f" 2>/dev/null; then
        warn "$f references /root/ — fix to use user home (SUDO_USER detection)"
        HAS_ISSUES=1
      fi
      ;;
  esac
done

# ── Summary ──────────────────────────────────────────────────
if [[ "$HAS_ISSUES" -eq 0 ]]; then
  echo "  ${GREEN}✅ change-validate: all checks passed${RESET}"
fi
echo ""
exit 0  # Always pass — this is advisory. Blocking is done by the skill.
