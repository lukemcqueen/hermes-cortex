#!/usr/bin/env bash
# Capture the before/after for the suite-collection break (issue #212 / event #212): the same
# pytest collection command run at a PINNED pre-change revision and at the working tip.
#
# Read-only: it runs tests and writes only its own transcript.
#
# Re-run: bash docs/evidence/suite-collection-fix-2026-10-21.sh
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 2
TMP="${TMPDIR:-/tmp}/collection-fix.$$"
mkdir -p "$TMP" || exit 2

# PINNED BASELINE, not `git merge-base origin/main HEAD`.
# 7af34e79 is the commit this change sits on — the last revision whose
# tests/test_task_mcp_descriptions.py still ran its checks at MODULE level and ended in a bare
# `raise SystemExit(...)`. A merge-base baseline is wrong in BOTH directions here: before the
# commit it resolves to the tip (so the comparison measures the fix against itself — a tautology
# wearing a PASS), and after a push origin/main IS the fix, so it silently stops discriminating.
# Pinned, the comparison keeps testing what it claims.
BASE_PIN="7af34e798fd9137470bad40fab7bcf8baa986917"

# The transcript IS this script's stdout, written to the committed path: run it bare and the
# file below is regenerated in place. `generated-by` is therefore a fact about the file, not a
# claim about who typed it.
OUT="${1:-docs/evidence/suite-collection-fix-2026-10-21.txt}"
exec >"$OUT" 2>&1

say() { printf '%s\n' "$@"; }
rule() { printf '\n===== %s =====\n' "$1"; }
norm() { sed -e "s#${HOME}#~#g"; }

say "generated-by: docs/evidence/suite-collection-fix-2026-10-21.sh   (this file IS that script's stdout)"
say "host-date:    $(date -Is)"
say "captured-at:  $(git rev-parse HEAD)"
say "              ^ the revision the working tree sat on WHEN THIS WAS CAPTURED. The change under"
say "                test was UNCOMMITTED at that moment, which is why the assertions below are"
say "                about a worktree baseline rather than about a commit of this change."
say "committed-in: the commit that ADDS this file — one commit AHEAD of captured-at, always. A"
say "              transcript cannot name its own commit: writing this file changes the revision,"
say "              so any 'tip' line here would be false the instant it was committed. Read"
say "              captured-at as provenance, never as a claim about the range tip."
say "range-base:   $BASE_PIN   (== the baseline measured below: see the note)"
say "baseline:     $BASE_PIN"
say "              This equals the range base ON PURPOSE. The range base IS the pre-change"
say "              revision here: the fix lives in the working tree on top of it, so the base is"
say "              the last revision whose tests/test_task_mcp_descriptions.py still exits at"
say "              import. The baseline is asserted to carry that defect below, which is what"
say "              stops this being a comparison of the fix against itself."
say "working-tree: $(git status --porcelain | grep -c . ) path(s) modified at capture"

rule "1. the fixed file, run BOTH ways (the script behaviour must survive the restructure)"
python3 tests/test_task_mcp_descriptions.py > "$TMP/direct.txt" 2>&1
rc=$?
tail -4 "$TMP/direct.txt" | norm
say "rc=$rc   (command: python3 tests/test_task_mcp_descriptions.py)"

bash tests/run-tests.sh tests/test_task_mcp_descriptions.py -q --color=no > "$TMP/one.txt" 2>&1
rc=$?
grep -aE "[0-9]+ (passed|failed)" "$TMP/one.txt" | tail -1
say "rc=$rc   (command: bash tests/run-tests.sh tests/test_task_mcp_descriptions.py -q --color=no)"

rule "2. THE SYMPTOM — whole-suite collection, at the PINNED baseline and at the WORKING TREE"
say "Same command on both sides. The baseline is a git worktree at $BASE_PIN, an immutable"
say "revision, and the script ASSERTS that checkout really is the pre-change revision before"
say "claiming anything from it."
say ""
BASE_WT="$TMP/base-wt"
git worktree add -q "$BASE_WT" "$BASE_PIN" 2>"$TMP/wt.err"
wt_rc=$?
if [ "$wt_rc" -ne 0 ]; then
  say "comparison NOT RUN, nothing claimed: could not create a worktree at $BASE_PIN"
  sed -e "s#${HOME}#~#g" "$TMP/wt.err" | head -3
else
  resolved="$(git -C "$BASE_WT" rev-parse HEAD)"
  say "worktree resolves to: $(git -C "$BASE_WT" rev-parse --short=8 HEAD)"
  if [ "$resolved" != "$BASE_PIN" ]; then
    say "comparison NOT RUN, nothing claimed: the checkout is $resolved, not $BASE_PIN"
  else
    say "ASSERTED: the checkout is exactly $BASE_PIN"
    # Prove the extracted copy is the PRE-change revision, one level down: the defect must be
    # present in it. Without this, a baseline that silently resolved to the fixed code would
    # keep printing success.
    defect="$(grep -c '^raise SystemExit' "$BASE_WT/tests/test_task_mcp_descriptions.py" 2>/dev/null || echo 0)"
    say "ASSERTED: module-level 'raise SystemExit' lines in the baseline copy = $defect (must be >= 1)"
    if [ "$defect" -lt 1 ]; then
      say "comparison NOT RUN, nothing claimed: the baseline copy does not carry the defect"
    else
      say ""
      say "--- BASELINE ($(git -C "$BASE_WT" rev-parse --short=8 HEAD)): bash tests/run-tests.sh <worktree>/tests -q --collect-only --color=no"
      # ABSOLUTE path into the worktree. A relative `tests/` resolves against the CWD — the MAIN
      # checkout — so the "baseline" would collect the FIXED file and report a tautology. The
      # first version of this script did exactly that and printed 2463 collected on both sides.
      bash "$BASE_WT/tests/run-tests.sh" "$BASE_WT/tests" -q --collect-only --color=no > "$TMP/base.txt" 2>&1
      brc=$?
      grep -a -e "INTERNALERROR>" -e "no tests ran" -e "tests collected" "$TMP/base.txt" | tail -3 | norm
      say "  rc=$brc"
      say ""
      say "--- WORKING TREE (the change under test): bash tests/run-tests.sh tests/ -q --collect-only --color=no"
      bash tests/run-tests.sh tests/ -q --collect-only --color=no > "$TMP/tip.txt" 2>&1
      trc=$?
      grep -a -e "INTERNALERROR>" -e "no tests ran" -e "tests collected" "$TMP/tip.txt" | tail -3 | norm
      say "  rc=$trc"
      say ""
      say "INTERNALERROR lines: baseline=$(grep -ac INTERNALERROR "$TMP/base.txt")  working-tree=$(grep -ac INTERNALERROR "$TMP/tip.txt")"
    fi
  fi
  git worktree remove --force "$BASE_WT" >/dev/null 2>&1 || rm -rf "$BASE_WT"
fi

rule "3. the guard proven BOTH ways, not just green on the healthy file"
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("t", "tests/test_task_mcp_descriptions.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
healthy = " ".join(m.REQUIRED.values())
print(f"  healthy text        -> {m.check(healthy)}   (empty list = passes)")
print(f"  healthy + forbidden -> {m.check(healthy + ' awaiting orchestrator verify')}")
print(f"  empty text          -> {len(m.check(''))} failure(s)")
PY

rule "end of transcript"
rm -rf "$TMP"
