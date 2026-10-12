#!/usr/bin/env bash
# Verify the session-cache / loop_evaluator landing (cycle 12240) in ONE run.
# Exits non-zero on any failed claim. Overrides: REPO=, PYTHON=
set -uo pipefail

REPO="${REPO:-$HOME/hermes-cortex}"
PY="${PYTHON:-$HOME/.hermes/hermes-agent/venv/bin/python3}"
FAILS=0
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
say() { printf '%s\n' "$*"; }
bad() { say "FAIL  $1"; FAILS=$((FAILS + 1)); }

cd "$REPO" || exit 2
say "session-cache / loop_evaluator landing verify — repo=$REPO  head=$(git rev-parse --short HEAD)"
say

# 1 — the metric repro: the label and the arithmetic must agree
python3 tests/run_loop_evaluator_avg_per_task_repro.py >"$TMP/metric.txt" 2>&1; rc=$?
say "1  metric repro rc=$rc  $(tail -1 "$TMP/metric.txt")"
[ "$rc" = 0 ] || bad "1 metric repro"
say "   $(grep -Eo 'avg[^:]*: [0-9.]+ .*' "$TMP/metric.txt" | tail -1)"

# 2 — the session-cache / loop-db repro
python3 tests/run_session_cache_loop_db_repro.py >"$TMP/cache.txt" 2>&1; rc=$?
say "2  session-cache repro rc=$rc  $(tail -1 "$TMP/cache.txt")"
[ "$rc" = 0 ] || bad "2 session-cache repro"

# 3 — the changed CLI still starts from the deployed layout (its import portability)
python3 ops/scripts/manage/agent-session_cache.py --help >"$TMP/help.txt" 2>&1; rc=$?
say "3  agent-session-cache --help rc=$rc  $(grep -c 'session-cache-build' "$TMP/help.txt") subcommands"
[ "$rc" = 0 ] || bad "3 agent-session-cache --help"

# 4 — the DEPLOYED copy of the changed script == repo (body compare, headers stripped)
"$PY" - <<'PY' >"$TMP/dep.txt" 2>&1
import pathlib
def body(p):
    lines = pathlib.Path(p).read_text().splitlines()
    while lines and (lines[0].startswith("#") or not lines[0].strip()):
        lines.pop(0)
    return lines
home = pathlib.Path.home()
src = "ops/scripts/manage/agent-session_cache.py"
dep = home/".hermes-cortex/scripts/agent-session_cache.py"
print(("PASS" if dep.is_file() and body(dep) == body(pathlib.Path(src)) else "FAIL"),
      "deployed == repo:", src)
PY
cat "$TMP/dep.txt"
grep -q '^FAIL' "$TMP/dep.txt" && bad "4 deployed copy differs"

say
if [ "$FAILS" -eq 0 ]; then say "ALL CLAIMS VERIFIED (0 failures)"; exit 0; fi
say "$FAILS CLAIM(S) FAILED"; exit 1
