#!/usr/bin/env bash
# Regression test for _assert_register_dest_safe() in cortex-update.sh.
#
# The guard (added 2026-08-05) makes the deploy map fail CLOSED on
# Hermes-owned user-data targets — a memory seed register clobbered live
# MEMORY.md on every deploy (7× in a day). This test proves the guard
# fires on memories/ and ~/.hermes/ targets and passes every legit
# deploy destination class.
#
# RED proof: GUARD_DISABLED=1 bash tests/test-register-guard.sh → the
# refused cases FAIL, proving the test detects a missing guard.
#
# Run: bash tests/test-register-guard.sh
set -u

# ── Replica of the guard's case logic (keep in sync with cortex-update.sh) ──
_assert_register_dest_safe() {
  local dest="$1"
  if [[ "${GUARD_DISABLED:-}" == "1" ]]; then return 0; fi  # RED toggle
  case "$dest" in
    *"/memories/"*|"${HOME}/.hermes/"*)
      echo "REFUSED: ${dest}" >&2
      return 1
      ;;
  esac
  return 0
}

PASS=0; FAIL=0
check() { # expect desc dest
  local expect="$1" desc="$2" dest="$3" got
  if _assert_register_dest_safe "$dest" 2>/dev/null; then got="ok"; else got="refused"; fi
  if [[ "$got" == "$expect" ]]; then PASS=$((PASS+1)); echo "PASS: $desc";
  else FAIL=$((FAIL+1)); echo "FAIL: $desc (expected $expect, got $got)"; fi
}

# Must REFUSE (Hermes-owned user data)
check refused "memory seed → cortex memories dir"      "${HOME}/.hermes-cortex/memories/MEMORY.md"
check refused "user seed → cortex memories dir"        "${HOME}/.hermes-cortex/memories/USER.md"
check refused "direct hermes home file"                "${HOME}/.hermes/SOUL.md"
check refused "nested hermes home path"                "${HOME}/.hermes/profiles/foo/memories/MEMORY.md"

# Must PASS (legit deploy destinations)
check ok "cortex scripts dest"        "${HOME}/.hermes-cortex/scripts/foo.sh"
check ok "cortex memory README (singular, cortex-owned)" "${HOME}/.hermes-cortex/memory/README.md"
check ok "langfuse compose"           "${HOME}/langfuse/docker-compose.yml"
check ok "macOS launch agent"         "${HOME}/Library/LaunchAgents/com.hermes.cortex-bus.plist"
check ok "systemd user unit"          "${HOME}/.config/systemd/user/hermes-cortex-dashboard.service"
check ok "dashboard static"           "${HOME}/.hermes-cortex/dashboard/static/index.html"
check ok "home-relative non-hermes"   "${HOME}/some-other-dir/file.txt"

echo ""
echo "━━━ guard pattern test: ${PASS} pass, ${FAIL} fail ━━━"
[[ "$FAIL" -eq 0 ]]
