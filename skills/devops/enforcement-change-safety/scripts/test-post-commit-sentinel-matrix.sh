#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# test-post-commit-sentinel-matrix.sh
#
# Verifies post-commit-audit's sentinel logic across ALL eight git commit
# paths. Run this before shipping ANY change to post-commit-audit (or to the
# pre-commit sentinel protocol) — it proves genuine --no-verify bypasses are
# still logged while git-internal replays (rebase/cherry-pick/revert/merge)
# stay silent.
#
# Usage:
#   bash scripts/test-post-commit-sentinel-matrix.sh \
#       [PATH_TO_POST_COMMIT_AUDIT] [PATH_TO_PRE_COMMIT_SCORE]
#
# Defaults: repo copies at ~/hermes-cortex/ops/scripts/.
#
# Expectation table (the contract):
#   path                    | must log? | reflog prefix
#   ------------------------+-----------+------------------
#   1 normal commit         | NO        | commit:
#   2 git commit --no-verify| YES       | commit:
#   3 rebase replay         | NO        | rebase (pick):
#   4 cherry-pick           | NO        | cherry-pick:
#   5 revert                | NO        | revert:
#   6 merge (non-ff)        | NO        | merge <branch>:
#   7 amend (normal)        | NO        | commit (amend):
#   8 amend --no-verify     | YES       | commit (amend):
#
# Each path is measured as a DELTA: the log is reset before the path and
# asserted AFTER it, so a genuine --no-verify entry (paths 2/8) can never
# inflate the counts of later silent paths.
#
# Exit 0 if all eight behave; exit 1 with the failing case(s) named.
# ─────────────────────────────────────────────────────────────────────────────
set -u

POST_COMMIT="${1:-$HOME/hermes-cortex/ops/scripts/post-commit-audit}"
PRE_COMMIT="${2:-$HOME/hermes-cortex/ops/scripts/pre-commit-score}"
WORK="$(mktemp -d /tmp/sentinel-matrix.XXXXXX)"
export HOME="$WORK/home"
mkdir -p "$HOME/.hermes-cortex/state"

cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

cd "$WORK" || exit 1
git init -q -b main
git config user.email test@test
git config user.name test

# Install the REAL hooks under test. The pre-commit sentinel contract:
# pre-commit touches .git/.pre-commit-ran; post-commit consumes it or logs.
mkdir -p .git/hooks
cp "$POST_COMMIT" .git/hooks/post-commit
chmod +x .git/hooks/post-commit
cat > .git/hooks/pre-commit <<EOF
#!/usr/bin/env bash
SENTINEL="\${GIT_DIR:-.git}/.pre-commit-ran"
touch "\$SENTINEL"
EOF
chmod +x .git/hooks/pre-commit

LOG="$HOME/.hermes-cortex/state/no-verify-log.json"
count_entries() {
  python3 -c "
import json, os
p = '$LOG'
if not os.path.exists(p):
    print(0)
else:
    print(len(json.load(open(p))))
" 2>/dev/null || echo 0
}

PASS=1

# run_path <label> <expected_delta> -- runs the command via stdin; asserts
# the log gained exactly <expected_delta> entries (0 or 1).
run_path() {
  local label="$1" expected="$2"
  shift 2
  rm -f "$LOG"
  "$@" >/dev/null 2>&1
  local actual
  actual=$(count_entries)
  if [[ "$actual" != "$expected" ]]; then
    PASS=0
    echo "FAIL path $label: expected $expected log entries, got $actual"
  fi
}

# Path 1: normal commit — silent
echo a > f1.txt && git add f1.txt
run_path 1 0 git commit -q -m "normal"

# Path 2: --no-verify — must log exactly 1
echo b > f2.txt && git add f2.txt
run_path 2 1 git commit -q --no-verify -m "bypass"

# Path 3: rebase replay — silent
git checkout -q -b rb
echo c > f3.txt && git add f3.txt && git commit -q -m "rb-src"
git checkout -q main
echo d > f4.txt && git add f4.txt && git commit -q -m "main-src"
git checkout -q rb
run_path 3 0 git rebase main

# Path 4: cherry-pick — silent
git checkout -q main
run_path 4 0 git cherry-pick rb

# Path 5: revert — silent
run_path 5 0 git revert --no-edit HEAD

# Path 6: merge (non-ff) — silent
git checkout -q -b mrg
echo e > f5.txt && git add f5.txt && git commit -q -m "mrg-src"
git checkout -q main
echo f > f6.txt && git add f6.txt && git commit -q -m "main-src2"
run_path 6 0 git merge mrg --no-edit

# Path 7: amend (normal) — silent
echo g > f7.txt && git add f7.txt && git commit -q -m "amend-orig"
run_path 7 0 git commit -q --amend --no-edit

# Path 8: amend --no-verify — MUST log (genuine bypass, reflog 'commit (amend):')
echo more >> f7.txt && git add f7.txt
run_path 8 1 git commit -q --amend --no-edit --no-verify

if [[ "$PASS" == "1" ]]; then
  echo "✅ All 8 sentinel paths behave per contract (only genuine --no-verify logged)."
  exit 0
else
  echo "❌ Sentinel matrix FAILED — do NOT ship this hook change."
  exit 1
fi
