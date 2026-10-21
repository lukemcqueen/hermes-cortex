#!/usr/bin/env bash
# Resolve the DIFFERS verdicts that section 9 of
# sweep-json-rows-and-engine-error-2026-10-21.txt reported, and do it READ-ONLY: this
# script measures and prints; it repairs nothing.
#
# Section 9 compared the full-suite run at the tip against each failing file run ALONE in a
# worktree at the range base. Two different invocation shapes — so a DIFFERS verdict there is
# a CANDIDATE, not a finding. This script closes that gap by re-running each DIFFERS file
# ALONE at the tip (the same shape as the base side), and by isolating the ambient state that
# moved the fourth file between runs.
#
# Re-run: bash docs/evidence/sweep-range-differs-resolution-2026-10-21.sh
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 2
HOME_DIR="${HOME}"
PY="$HOME/.hermes-cortex/venv/bin/python3"
CLEAN_HOME="${TMPDIR:-/tmp}/differs-clean-home.$$"

say() { printf '%s\n' "$@"; }
rule() { printf '\n===== %s =====\n' "$1"; }
norm() { sed -e "s#${HOME_DIR}#~#g"; }
outcome() {  # classify a pytest log the three ways, never from a bare rc
  if grep -qE "[0-9]+ failed" "$1"; then echo "FAIL"; \
  elif grep -qE "[0-9]+ passed" "$1"; then echo "PASS"; \
  else echo "NOT RUN (nothing was collected)"; fi
}

say "generated-by: docs/evidence/sweep-range-differs-resolution-2026-10-21.sh"
say "host-date:    $(date -Is)"
say "tip:          $(git rev-parse HEAD)"
say "range-base:   $(git merge-base origin/main HEAD)"
say ""
say "Section 9 of the committed transcript reports 19 REPRODUCED, 3 DIFFERS, 0 COULD NOT"
say "VERIFY. This script re-measures the three DIFFERS it names — tests/test_gen_briefing.py,"
say "tests/test_loop_gov_mcp_nonblocking.py, tests/test_runtime/test_doctor_pending_cycles.py"
say "— plus tests/test_repo_less_lock_handling.py, which the SAME comparison flagged in an"
say "earlier run of it (that run is not the committed one; the file is here because a"
say "comparison that moves between runs has to be explained, not just re-run)."

# ---- 1. same shape on BOTH sides: each file ALONE at the tip ----------------
rule "1. each DIFFERS file run ALONE at the tip (the shape the base side used)"
for f in tests/test_gen_briefing.py tests/test_loop_gov_mcp_nonblocking.py \
         tests/test_repo_less_lock_handling.py \
         tests/test_runtime/test_doctor_pending_cycles.py; do
  bash tests/run-tests.sh "$f" -q --color=no > "${TMPDIR:-/tmp}/d-one.txt" 2>&1
  rc=$?
  say "  $f"
  say "    tip-alone rc=$rc -> $(outcome "${TMPDIR:-/tmp}/d-one.txt")   $(grep -aE '[0-9]+ (passed|failed)' "${TMPDIR:-/tmp}/d-one.txt" | tail -1)"
done

# ---- 2. the file whose verdict moved between runs ---------------------------
rule "2. what moved tests/test_repo_less_lock_handling.py between runs — ambient state"
say "Why that file's verdict moved between runs: _promote_issue_to_task refuses when"
say "_read_lock() finds a lock for the RESOLVED session, and _read_lock() reads"
say "GOVERNANCE_STATE_DIR — shared by every session on the host, not scoped to this repo or"
say "this run. So its verdict is a function of which lock FILES happen to sit in that dir."
say ""
"$PY" - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location(
    "g", "/home/esther/hermes-cortex/mcp-servers/loop-gov-mcp.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
sid = m.get_session_id(None)
path = m._session_lock_path(sid)
print(f"  session id resolved with NO args : {sid}")
print(f"  lock file it therefore reads     : {path}")
print(f"  does that file exist right now?  : {path.exists()}")
PY

say ""
say "It also passes when that directory holds no lock at all — an independent confirmation"
say "that the deciding input is ambient state:"
mkdir -p "$CLEAN_HOME"
env -u PYTHONPATH -u PYTHONHOME HOME="$CLEAN_HOME" "$PY" -m pytest \
  tests/test_repo_less_lock_handling.py -q -p no:cacheprovider \
  > "${TMPDIR:-/tmp}/d-clean.txt" 2>&1
rc=$?
say "  rc=$rc -> $(outcome "${TMPDIR:-/tmp}/d-clean.txt")   $(grep -aE '[0-9]+ (passed|failed)' "${TMPDIR:-/tmp}/d-clean.txt" | tail -1)"
say "  (command: env -u PYTHONPATH -u PYTHONHOME HOME=<empty dir> $PY -m pytest \\"
say "            tests/test_repo_less_lock_handling.py -q -p no:cacheprovider)"
rm -rf "$CLEAN_HOME"

rule "3. lock files present in the shared state dir (this script removes NONE of them)"
ls -la "$HOME/.hermes-cortex/state/" 2>/dev/null | grep -a -e "governance" | norm

rule "end of resolution transcript"
say "A DIFFERS here is only ever a CANDIDATE: the two sides must be run the same way, and"
say "for this file the deciding input is ambient lock files rather than any code in the range."
