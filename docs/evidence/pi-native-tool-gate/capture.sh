#!/usr/bin/env bash
# capture.sh — REGENERATE docs/evidence/pi-native-tool-gate/live-e2e-proof.txt
#
# Why a script and not a hand-written log: an earlier version of this artifact
# showed a paraphrased `python3 -c "SELECT ..."` block that could not have
# produced the output beside it, and the close reviewer correctly refused it as
# fabrication. Every command here is the REAL one, printed immediately above its
# own output, with its own rc.
#
# Every emitted line passes through a single normaliser, so the transcript carries
# no host paths — including the ones echoed back INSIDE the predicate's own JSON.
# Run it exactly as documented and the output is reproducible:
#
#   cd ~ && bash hermes-cortex/docs/evidence/pi-native-tool-gate/capture.sh \
#       > hermes-cortex/docs/evidence/pi-native-tool-gate/live-e2e-proof.txt
set -u

EV="hermes-cortex/docs/evidence/pi-native-tool-gate"
SCRATCH=".hermes/cache/scratch/pi-gate-repo"
PROBE="$EV/live-gate-probe.mjs"
# The revision BEFORE the repo-scoping fix, pinned by SHA. Deliberately not
# 'HEAD': the artifact is committed in the same change as the fix, so HEAD would
# resolve to the FIXED server and the before/after comparison would be a
# tautology (review finding ADV-12605-1).
PRE_FIX="c08fbe2d"

body() {
  cd "$HOME" || exit 1
  local PY
  PY=$(command -v python3)

  echo "PI NATIVE-WRITE GATE — LIVE end-to-end proof (generated, not hand-written)"
  echo "Produced by: bash $EV/capture.sh   (every path below is normalised to ~)"
  echo "Generated at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo

  echo "═══════ 1. The SHARED predicate, three ways ═══════"
  echo "\$ loop-gov.py check_repo_lock '{\"repo_path\":\"<repo>\"}'"
  for R in "$HOME/hermes-cortex" "$HOME/steadfaste" "$HOME/.hermes/cache/scratch/pi-gate-repo"; do
    echo "--- repo_path=${R/$HOME/~}"
    "$PY" .hermes-cortex/scripts/loop-gov.py check_repo_lock "{\"repo_path\":\"$R\"}" 2>/dev/null
    echo "rc=$?"
    echo
  done
  echo "NOTE: a repo with its OWN lock answers covered=true (match=path); one without"
  echo "answers covered=false with rc=1; an unresolvable path is a REFUSAL, never an"
  echo "'unlocked' verdict. Where live_lock_count>0 sits beside covered=false, that is"
  echo "the 'do not mix gates' property: another repo's live lock does not authorise"
  echo "this one."
  echo

  echo "═══════ 2. Repo scoping is pinned by a test that FAILS on the old behaviour ═══════"
  echo "\$ python3 hermes-cortex/tests/test_check_repo_lock_scoping.py"
  "$PY" hermes-cortex/tests/test_check_repo_lock_scoping.py 2>&1 | grep -v '^\[mcp-server\]'
  echo "rc=${PIPESTATUS[0]}"
  echo
  echo "\$ git -C hermes-cortex show $PRE_FIX:mcp-servers/loop-gov-mcp.py > /tmp/pre-fix-loop-gov.py"
  git -C hermes-cortex show "$PRE_FIX:mcp-servers/loop-gov-mcp.py" > /tmp/pre-fix-loop-gov.py
  echo "  (baseline PINNED to $PRE_FIX, never 'HEAD': at the reviewed commit HEAD already"
  echo "   contains the fix, so extracting from HEAD would silently test the FIXED code"
  echo "   and this comparison would prove nothing.)"
  echo "\$ grep -c 'unscoped_locks' /tmp/pre-fix-loop-gov.py   # 0 proves the extraction is pre-fix"
  grep -c 'unscoped_locks' /tmp/pre-fix-loop-gov.py || true
  echo "\$ CORTEX_LOOP_GOV_SERVER=/tmp/pre-fix-loop-gov.py python3 hermes-cortex/tests/test_check_repo_lock_scoping.py   # must FAIL"
  CORTEX_LOOP_GOV_SERVER=/tmp/pre-fix-loop-gov.py "$PY" hermes-cortex/tests/test_check_repo_lock_scoping.py 2>&1 \
    | grep -v '^\[mcp-server\]' | head -3
  echo "rc=${PIPESTATUS[0]}"
  echo "  -> on the pre-fix server a lock with no repo_path answers covered=true with"
  echo "     match=slug-legacy for a DIFFERENT project sharing the directory name: the"
  echo "     gate-mixing case this change removes."
  echo

  echo "═══════ 3. The extension, EXECUTED both directions (stubbed CLI, hermetic) ═══════"
  echo "\$ node hermes-cortex/ops/install/harnesses/pi/verify-governance-extension.mjs"
  node hermes-cortex/ops/install/harnesses/pi/verify-governance-extension.mjs 2>&1 | tail -3
  echo "rc=${PIPESTATUS[0]}"
  echo
  echo "\$ python3 hermes-cortex/tests/test_pi_governance_gate.py"
  "$PY" hermes-cortex/tests/test_pi_governance_gate.py 2>&1 | tail -2
  echo "rc=${PIPESTATUS[0]}"
  echo

  echo "═══════ 4. Composition: the extension driving the REAL loop-gov.py ═══════"
  echo "\$ node $PROBE ~/.hermes/cache/scratch/pi-gate-repo"
  node "$PROBE" "$HOME/$SCRATCH" 2>&1
  echo "rc=${PIPESTATUS[0]}"
  echo

  echo "═══════ 5. The REAL pi session that ran this gate (pi 1.2.0) ═══════"
  echo "NOT reproducible by re-running this script: the turn is an LLM call. The"
  echo "evidence is the gate's OWN log, which records the decision it reached then."
  echo "The WHOLE log is printed (it is short) so nothing is trimmed into a story:"
  echo "\$ cat ~/.hermes-cortex/logs/pi-governance.log"
  cat .hermes-cortex/logs/pi-governance.log
  echo "  -> in order: the session's first write was REFUSED; the agent then opened a"
  echo "     lock of its own and its retry was ALLOWED; the read-only bash was allowed;"
  echo "     the trailing 'refused' lines are later runs of the §4 probe, which is"
  echo "     pointed at the same unlocked repo. Fail closed, name the remedy, comply"
  echo "     through the sanctioned path — a gate that only ever blocked is a deadlock."
  echo

  echo "═══════ 6. The cycle the pi session created for itself ═══════"
  echo "\$ loop-gov.py cycle_query '{\"task_id\":\"create-proof-txt\"}'"
  "$PY" .hermes-cortex/scripts/loop-gov.py cycle_query '{"task_id":"create-proof-txt"}' 2>/dev/null
  echo "rc=$?"
  echo "  -> pi's OWN session id created its OWN cycle, and it is scored (not PENDING),"
  echo "     so it is not a leak. No lock file for the scratch repo remains. Read through"
  echo "     the shared CLI, not raw SQL, so this stays one implementation."
  echo

  echo "═══════ 7. The file the session created (the assertion, not its claim) ═══════"
  echo "\$ ls -1 ~/.hermes/cache/scratch/pi-gate-repo    # no ownership column: public repo"
  ls -1 "$HOME/$SCRATCH"
  echo
  echo "\$ cat ~/.hermes/cache/scratch/pi-gate-repo/proof.txt"
  cat "$HOME/$SCRATCH/proof.txt"
  echo
  echo

  echo "═══════ 8. Adversarial gate (A4) on every changed source file ═══════"
  echo "\$ adversarial-verify.py --file <f> --level A4 --gate   (rc 0 = no critical/high)"
  for f in mcp-servers/loop-gov-mcp.py tests/test_check_repo_lock_scoping.py \
           tests/test_pi_governance_gate.py docs/evidence/pi-native-tool-gate/capture.sh \
           docs/evidence/pi-native-tool-gate/live-gate-probe.mjs; do
    printf '%-58s ' "$f"
    hermes-cortex/ops/scripts/quality/adversarial-verify.py --file "hermes-cortex/$f" --level A4 --gate 2>&1 \
      | grep -E 'GATE_PASSED|GATE_FAILED' || echo "NO VERDICT"
  done
  echo "  -> NOT reproduced here: the deploy/dogfood run, which MUTATES the host. Its"
  echo "     verdict belongs to the deploy tool's own output, and this artifact claims"
  echo "     nothing about it."
  echo

  echo "═══════ 9. What this proof does NOT cover ═══════"
  echo "- macOS. The extension shells out to a resolved python3 and is overridable via"
  echo "  CORTEX_GOVERNANCE_PYTHON for a Homebrew python off pi's PATH; untested here."
  echo "- The live pi turn is not reproducible (§5): only its gate log is. §4 is the"
  echo "  reproducible composition proof."
  echo "- The same-NAME/different-project case is pinned by §2 rather than driven live,"
  echo "  because constructing it needs a lock with no repo_path, and hand-writing a"
  echo "  lock file is a governance violation."
}

body | sed "s|$HOME|~|g"
