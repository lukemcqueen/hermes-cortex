#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  cortex-dogfood — permanent dogfood gate after commit/push
#
#  Runs the full dogfood cycle: pull latest → deploy → doctor →
#  verify clean. The dogfood directive (2026-08-04/05): a change is
#  not done until tested end-to-end from the deployed path. This
#  script makes that a one-command ritual — run it after any
#  commit/push that touches shared code.
#
#  Usage:
#    cortex-dogfood.sh            # full cycle (default)
#    cortex-dogfood.sh --quiet    # doctor output compact
#    cortex-dogfood.sh --doctor-only  # skip pull/deploy, just verify
#    cortex-dogfood.sh --force    # cortex-update --force-all
#
#  Exit 0 = deployed state verified clean (doctor no FAIL).
#  Exit 1 = something failed; fix before claiming done.
# ─────────────────────────────────────────────────────────────
set -uo pipefail

REPO="${HOME}/hermes-cortex"
UPDATE="${REPO}/ops/scripts/cortex-update.sh"
DOCTOR="${REPO}/ops/scripts/manage/cortex-doctor.py"
QUIET=""
FORCE=""
DOCTOR_ONLY=""

# Orchestrator scope (Luke correction 2026-08-05): dogfood verifies the
# deployed hermes-cortex state end-to-end — that is an orchestrator's
# (moses/esther) job. Non-orchestrator hosts get a clear message instead.
_detect_orch() {
  local _host _home _user
  _host=$(hostname -s 2>/dev/null || echo "unknown")
  _user=$(id -un 2>/dev/null || echo "$USER")
  _home=$(getent passwd "$_user" 2>/dev/null | cut -d: -f6)
  _home="${_home:-$HOME}"
  case "$_host" in
    moses|esther)
      [[ "$_home" == "/home/$_host" ]] && return 0
      ;;
  esac
  return 1
}

if ! _detect_orch; then
  echo "❌  cortex-dogfood: orchestrator-only (moses/esther hosts)."
  echo "    Dogfood verifies the deployed hermes-cortex state — a"
  echo "    non-orchestrator cannot run the full deploy/verify cycle."
  exit 1
fi

for arg in "$@"; do
  case "$arg" in
    --quiet) QUIET=1 ;;
    --force) FORCE="--force-all" ;;
    --doctor-only) DOCTOR_ONLY=1 ;;
    *) echo "unknown arg: $arg (use --quiet / --force / --doctor-only)"; exit 2 ;;
  esac
done

[[ -f "$DOCTOR" ]] || { echo "❌ doctor not found at $DOCTOR"; exit 1; }

echo "━━━ cortex-dogfood ━━━"

if [[ -z "$DOCTOR_ONLY" ]]; then
  # 1. Pull latest (rebase) — never diagnose without the newest source
  echo "▶ 1/4 pull latest"
  (cd "$REPO" && git pull --rebase origin main 2>&1 | sed 's/^/   /' || { echo "   (no remote or up to date)"; })

  # 2. Deploy — sync deployed files to repo source
  if [[ -f "$UPDATE" ]]; then
    echo "▶ 2/4 deploy"
    bash "$UPDATE" ${FORCE:-} 2>&1 | sed 's/^/   /'
  else
    echo "⚠️  update script not found — skipping deploy (doctor-only state)"
  fi
else
  echo "▶ 1/2 doctor-only mode (skipping pull/deploy)"
fi

# 3. Doctor — full state verification
echo "▶ $([ -z "$DOCTOR_ONLY" ] && echo 3/4 || echo 2/2) doctor"
if [[ -n "$QUIET" ]]; then
  DOCTOR_OUT=$(cd "$(dirname "$DOCTOR")" && python3 "$(basename "$DOCTOR")" --quiet 2>&1)
else
  DOCTOR_OUT=$(cd "$(dirname "$DOCTOR")" && python3 "$(basename "$DOCTOR")" 2>&1)
fi
echo "$DOCTOR_OUT" | sed 's/^/   /'

# 4. Verify — FAIL means the dogfood cycle failed. A real failure is any
#    ❌ check line that is NOT the "Overall: FAILING" summary line.
#    Match on the ❌ marker, not the word "FAIL" — "Overall: FAILING"
#    would false-positive. NOTE: PENDING cycles are NOT excluded — the
#    doctor FAILs only on cycles from finished tasks (no active lock), so
#    a dogfood run with leaked prior-task cycles fails. (2026-08-05.)
_DOGFOOD_FAILS=$(echo "$DOCTOR_OUT" | grep -E '^ *❌' | grep -vcE 'Overall: FAILING' || true)
if [[ "${_DOGFOOD_FAILS:-0}" -gt 0 ]]; then
  echo ""
  echo "❌  DOGFOOD FAILED — deployed state does not verify clean."
  echo "    Fix the FAIL above, re-run cortex-dogfood.sh, then claim done."
  echo ""
  exit 1
fi

echo ""
echo "✅  DOGFOOD PASSED — deployed state verified clean."
exit 0
