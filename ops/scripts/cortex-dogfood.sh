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

# Capture the current governance session's task_id BEFORE deploy: the
# deploy step (cortex-update.sh) purges governance locks (known
# side-effect), which would make THIS session's own cycle look "leaked"
# to the doctor (no active lock → FAIL). Record it so the verify step
# can exempt exactly this task — other leaked cycles still fail.
DOGFOOD_OWN_TASK=""
for _lf in "${HOME}/.hermes-cortex/state"/.governance-*.json; do
  [[ -f "$_lf" ]] || continue
  _task=$(python3 -c "import json;print(json.load(open('$_lf')).get('task_id',''))" 2>/dev/null || echo "")
  if [[ -n "$_task" ]]; then
    DOGFOOD_OWN_TASK="$_task"
    break
  fi
done
if [[ -n "$DOGFOOD_OWN_TASK" ]]; then
  echo "  (running under governance task: ${DOGFOOD_OWN_TASK} — its cycle is scored at end_change)"
fi

if [[ -z "$DOCTOR_ONLY" ]]; then
  # 1. Pull latest (rebase) — never diagnose without the newest source.
  #    Resolve the remote's DEFAULT branch (not hardcoded 'main'): after the
  #    2026-08-24 PII history rewrite the default is pii-clean-history, and
  #    hardcoding 'main' pulls the stale pre-rewrite history, re-triggering a
  #    stuck interactive rebase (unmerged files) that breaks the deploy sync.
  echo "▶ 1/4 pull latest"
  _DEFAULT_BRANCH=$(git -C "$REPO" symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's#refs/remotes/origin/##' || echo "main")
  # ── Fail-closed relock (Luke 2026-10-02) ──
  # This script runs the deploy, which unlocks the immutable enforcement files.
  # cortex-update.sh relocks via its own EXIT trap now, but the mandated
  # pre-push gate must not depend on a CHILD script's trap for a security
  # property: if this script dies between the unlock and the deploy, the gate is
  # left tamperable. Belt and braces — relock on OUR exit too. `lock` is
  # idempotent, so a run that never unlocked is a harmless no-op.
  _dogfood_relock() {
    local _rc=$?
    bash -c 'hermes-plugin-lock lock 2>/dev/null || sudo -n hermes-plugin-lock lock' >/dev/null 2>&1 || true
    if [[ $_rc -ne 0 ]]; then
      echo "   (relock ran on a failed exit rc=$_rc — enforcement files re-secured)"
    fi
  }
  trap _dogfood_relock EXIT

  # ── Pull must never damage local work (Luke 2026-10-02) ──
  # `git pull --rebase` with unpushed commits, or a conflicted rebase, leaves
  # the repo mid-rebase and MOVES HEAD TO ORIGIN — dropping the local commits.
  # That happened: two unpushed commits were orphaned and were recoverable only
  # from the reflog. The local work IS what this gate is about to verify, so do
  # not rebase over it: refuse when anything local exists, and abort a failed
  # rebase rather than walking away from it.
  _pull_log="${TMPDIR:-/tmp}/cortex-dogfood-pull.log"
  (cd "$REPO" && {
      if [[ -n "$(git log --oneline "origin/${_DEFAULT_BRANCH}..HEAD" 2>/dev/null)" ]]; then
        echo "   (unpushed local commits present — skipping pull; local work is what we verify)"
      elif [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
        echo "   (working tree has changes — skipping pull)"
      elif git pull --rebase --autostash origin "$_DEFAULT_BRANCH" >"$_pull_log" 2>&1; then
        sed 's/^/   /' "$_pull_log"
      else
        sed 's/^/   /' "$_pull_log"
        echo "   (pull failed — aborting the rebase so local commits are not left dangling)"
        git rebase --abort 2>/dev/null || true
      fi
    })

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
#    would false-positive. NOTE: PENDING cycles are NOT broadly excluded —
#    the doctor FAILs only on cycles from finished tasks (no active lock).
#    BUT the deploy step purged this session's own lock, so if the doctor
#    flags exactly DOGFOOD_OWN_TASK's cycle, that is THIS run's cycle being
#    scored at end_change — exempt it. Other leaked cycles still fail.
#    (2026-08-05.)
_DOGFOOD_FAILS=$(echo "$DOCTOR_OUT" | grep -E '^ *❌' | grep -vcE 'Overall: FAILING' || true)
if [[ -n "$DOGFOOD_OWN_TASK" ]]; then
  _OWN_CYCLES=$(echo "$DOCTOR_OUT" | grep -cE "❌.*${DOGFOOD_OWN_TASK}" || true)
  if [[ "${_OWN_CYCLES:-0}" -gt 0 ]]; then
    _DOGFOOD_FAILS=$((_DOGFOOD_FAILS - _OWN_CYCLES))
    echo "  (exempted ${_OWN_CYCLES} own-task cycle(s) — scored at end_change)"
  fi
fi
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
