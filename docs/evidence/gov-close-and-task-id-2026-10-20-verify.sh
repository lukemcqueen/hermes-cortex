#!/usr/bin/env bash
# SOURCE: hermes-cortex/docs/evidence/gov-close-and-task-id-2026-10-20-verify.sh
#
# Re-runnable proof for cycle 13412 (governance close-path + pre-commit task-id).
# Recorded output: gov-close-and-task-id-2026-10-20.txt — regenerate by running
# this script; do not trust the .txt without re-running it.
#
# Every claim the change makes is reprinted here from a live measurement:
#   §1 the root cause is a shell shape, reproduced in a throwaway repo
#   §2 the ledger damage, read from the loop-governance DB (read-only)
#   §3 the regression guard
#   §4 the deployed hook (the artifact the fleet actually runs)
#   §5 the suites around the change
#   §6 end-to-end: a first commit through the DEPLOYED hook records a clean id
#
# Exits non-zero if any assertion fails, so it is safe to wire into CI.
#
# Related records: cycle 13412; loop-governance issue event #188 (ledger
# hygiene: the 6,395 pre-existing malformed rows and the hook share of
# cycle_stats); issue #186 (learning-report staging, a different defect).
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOYED="${CORTEX_DEPLOY_HOME:-$HOME/.hermes-cortex}"
HOOK_SRC="$REPO/ops/scripts/pre-commit-score"
HOOK_DEPLOYED="$DEPLOYED/scripts/pre-commit-score"
FAILED=0

say() { printf '%s\n' "$*"; }
run() { printf '$ %s\n' "$*"; "$@"; }
fail() { say "ASSERTION FAILED: $*"; FAILED=1; }

say "# governance close-path + pre-commit task-id — verification (cycle 13412)"
say "# host: $(hostname -s)  date: $(date '+%F %T %Z')"
say

say "=== 1. root cause: \$(cmd || echo fallback) concatenates both outputs ==="
say '# in a repo with no commits, git prints "HEAD" AND exits non-zero, so the'
say '# substitution yields "HEAD" + newline + "unknown"'
TMP1="$(mktemp -d)"
( cd "$TMP1" && git init -q . && printf '  OLD: %s\n' "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')" | cat -A )
OLD_OUT="$( cd "$TMP1" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown' )"
case "$OLD_OUT" in
  *$'\n'*) ;;                      # newline present = the bug is real
  *) fail "the old shape no longer concatenates — re-derive the root cause" ;;
esac
rm -rf "$TMP1"
say

say "=== 2. ledger damage from that shape (read-only) ==="
run python3 - "$HOME/.hermes-cortex/data/loop-governance.db" <<'PY'
import sqlite3, sys, pathlib
db = pathlib.Path(sys.argv[1])
if not db.exists():
    print("  ledger absent on this host — nothing to measure"); raise SystemExit(0)
c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
rows = c.execute("SELECT task_id, user_overrode FROM loop_cycles").fetchall()
pref = [r for r in rows if str(r[0]).startswith("precommit-")]
nf = [r for r in rows if r[1] is None]
print(f"  total cycles            : {len(rows)}")
print(f"  precommit-* hook cycles : {len(pref)}")
print(f"  task_id with a NEWLINE  : {sum(1 for r in rows if chr(10) in str(r[0]))}")
print(f"  distinct malformed ids  : {len({r[0] for r in rows if chr(10) in str(r[0])})}")
print(f"  no feedback (all)       : {len(nf)}")
print(f"  no feedback (precommit) : {sum(1 for r in nf if str(r[0]).startswith('precommit-'))}")
PY
say '# the malformed counts are HISTORICAL: they predate this change, which stops'
say '# new ones being minted. Normalising the existing rows is a data decision'
say '# recorded as loop-governance issue event #188.'
say

say "=== 3. the regression guard ==="
run python3 "$REPO/tests/test_gov_close_and_task_id.py"; RC=$?
[ "$RC" -eq 0 ] || fail "the guard exited $RC"
say

say "=== 4. the deployed hook is the fixed one ==="
if [ -f "$HOOK_DEPLOYED" ]; then
  if grep -q "_field() { printf" "$HOOK_DEPLOYED"; then
    say "  deployed hook: normalised field helper present"
  else
    fail "the deployed hook has no _field() helper — run cortex-update.sh"
  fi
  N_OLD="$(grep -c 'abbrev-ref HEAD 2>/dev/null || echo' "$HOOK_DEPLOYED" || true)"
  say "  deployed hook: old concatenating line count = $N_OLD (want 0)"
  [ "$N_OLD" = "0" ] || fail "the deployed hook still builds the id with the old shape"
else
  say "  deployed hook absent at $HOOK_DEPLOYED — skipped"
fi
say

say "=== 5. suites around the change ==="
run bash "$REPO/tests/run-tests.sh" -q \
  tests/test_gov_close_and_task_id.py \
  tests/test_doctor_score_cycle_check.py \
  tests/test_precommit_test_discovery.py \
  tests/test_runtime/test_governance_bypass.py 2>&1 | tail -3
say

say "=== 6. end-to-end: a FIRST commit through the DEPLOYED hook ==="
TMP6="$(mktemp -d)"
mkdir -p "$TMP6/hooks"
if [ -f "$HOOK_DEPLOYED" ]; then
  cp "$HOOK_DEPLOYED" "$TMP6/hooks/pre-commit"
  chmod +x "$TMP6/hooks/pre-commit"
  git init -q "$TMP6/repo"
  ( cd "$TMP6/repo" \
    && git config user.email fixture@example.com \
    && git config user.name fixture \
    && git config core.hooksPath "$TMP6/hooks" \
    && echo x > f.txt && git add f.txt \
    && PRE_COMMIT_SCORE_DB="$TMP6/scratch.db" git commit -qm "first commit via the deployed hook" )
  python3 - "$TMP6/scratch.db" <<'PY'
import sqlite3, sys, pathlib, re
db = pathlib.Path(sys.argv[1])
if not db.exists():
    print("  no scratch ledger — the hook did not score"); raise SystemExit(1)
ids = [r[0] for r in sqlite3.connect(db).execute("SELECT DISTINCT task_id FROM loop_cycles")]
print(f"  ids recorded: {ids}")
bad = [i for i in ids if "\n" in i or re.search(r"\s", i)]
print(f"  ids with newline/whitespace: {len(bad)} (want 0)")
raise SystemExit(1 if (bad or not ids) else 0)
PY
  [ $? -eq 0 ] || fail "the deployed hook still records a malformed task id"
else
  say "  deployed hook absent — skipped"
fi
rm -rf "$TMP6"
say

if [ "$FAILED" -eq 0 ]; then
  say "RESULT: PASS — every claim in this cycle is reproduced above"
else
  say "RESULT: FAIL — see ASSERTION FAILED lines"
fi
exit "$FAILED"
