#!/usr/bin/env bash
# Re-verify the two sweep guards (#125 and the liveness rescue) end to end.
#
#   bash docs/evidence/purge-guards-verify.sh [repo-path]
#
# Every step runs against a THROWAWAY CORTEX_HOME, so no live lock or cycle is touched. Exit 0
# only when every claim re-verifies.
set -uo pipefail

REPO="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO" || { echo "no such repo: $REPO"; exit 2; }
SCRIPT=ops/scripts/manage/purge-stale-governance-locks.py
FAILED=0

# Redact the absolute home prefix at the SOURCE, so the committed transcript equals the output.
exec > >(sed "s|$HOME|~|g") 2>&1

step() { echo; echo "--- $*"; }

step "1. contract tests: both guards, both directions, behavioural closer parity, escalation"
out=$(bash tests/run-tests.sh tests/test_purge_resolves_orphaned_cycles.py \
        tests/test_liveness_anywhere.py tests/test_purge_script_import_safety.py \
        tests/test_closer_parity_and_escalation.py 2>&1); rc=$?
printf '%s\n' "$out" | grep -E "passed|failed" | tail -2
[ "$rc" -eq 0 ] && echo "PASS  rc=0" || { echo "FAIL  rc=$rc"; FAILED=1; }

step "2. the SHIPPED CLI on a throwaway tree — three locks, three different correct outcomes"
T=$(mktemp -d); mkdir -p "$T/.hermes-cortex/state" "$T/.hermes-cortex/data"
python3 - "$T" <<'PY'
import json, sqlite3, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
home = Path(sys.argv[1]) / ".hermes-cortex"
old = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
conn = sqlite3.connect(str(home / "data" / "loop-governance.db"))
conn.execute("CREATE TABLE loop_cycles (id INTEGER PRIMARY KEY, task_id TEXT, decision TEXT,"
             " user_overrode INTEGER, unscored_reason TEXT, outcome_note TEXT, timestamp TEXT)")
# A: stale lock WITH a PENDING cycle  -> lock removed AND cycle resolved (#125)
# B: stale lock WITH a resolved cycle -> lock removed (the sweep still works)
conn.execute("INSERT INTO loop_cycles (task_id, decision) VALUES ('task-a','PENDING')")
conn.execute("INSERT INTO loop_cycles (task_id, decision) VALUES ('task-b','MOVE_ON')")
conn.execute("INSERT INTO loop_cycles (task_id, decision) VALUES ('task-c','PENDING')")
conn.commit(); conn.close()
for task in ("task-a", "task-b"):
    (home / "state" / f".governance-{task}.json").write_text(json.dumps({
        "session_id": task, "task_id": task, "agent": "sweep-probe", "status": "executing",
        "heartbeat_at": old, "started_at": old, "ttl_seconds": 3600,
        "repo_path": str(home / "no-such-repo")}))
# C: a stale-looking lock whose agent is BUSY (real repo, real commit) -> KEPT
work = Path(sys.argv[1]) / "busy-repo"; work.mkdir()
import subprocess
subprocess.run(["git", "init", "-q"], cwd=work, check=True)
subprocess.run(["git", "-c", "user.name=busy-agent", "-c", "user.email=b@example.com",
                "commit", "-q", "--allow-empty", "-m", "working"], cwd=work, check=True)
(home / "state" / ".governance-task-c.json").write_text(json.dumps({
    "session_id": "task-c", "task_id": "task-c", "agent": "busy-agent", "status": "executing",
    "heartbeat_at": old, "started_at": old, "ttl_seconds": 3600, "repo_path": str(work)}))
PY
run_out=$(CORTEX_HOME="$T/.hermes-cortex" python3 "$SCRIPT" 2>&1); run_rc=$?
printf '   rc=%s\n' "$run_rc"; printf '%s\n' "$run_out" | sed 's/^/   /'
python3 - "$T" <<'PY'
import sqlite3, sys
from pathlib import Path
home = Path(sys.argv[1]) / ".hermes-cortex"
state = home / "state"
conn = sqlite3.connect(str(home / "data" / "loop-governance.db"))
rows = dict(conn.execute("SELECT task_id, decision FROM loop_cycles").fetchall())
conn.close()
a_gone = not (state / ".governance-task-a.json").exists()
b_gone = not (state / ".governance-task-b.json").exists()
c_kept = (state / ".governance-task-c.json").exists()
ok = a_gone and rows["task-a"] == "MOVE_ON" and b_gone and c_kept and rows["task-c"] == "PENDING"
print(f"   task-a lock removed={a_gone} cycle={rows['task-a']}  (must be True / MOVE_ON)")
print(f"   task-b lock removed={b_gone} cycle={rows['task-b']}  (must be True / MOVE_ON)")
print(f"   task-c lock kept={c_kept} cycle={rows['task-c']}     (must be True / PENDING: busy agent)")
print("PASS  the sweep resolved what it orphaned, kept the busy session's lock" if ok
      else "FAIL  a guard did not hold")
sys.exit(0 if ok else 1)
PY
[ "$?" -eq 0 ] || FAILED=1

step "3. the FAIL-CLOSED direction: no store, so the lock must be KEPT"
T2=$(mktemp -d); mkdir -p "$T2/.hermes-cortex/state"
python3 - "$T2" <<'PY'
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
old = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
(Path(sys.argv[1]) / ".hermes-cortex" / "state" / ".governance-nostore.json").write_text(
    json.dumps({"session_id": "nostore", "task_id": "nostore", "agent": "a", "status": "executing",
                "heartbeat_at": old, "started_at": old, "ttl_seconds": 3600}))
PY
nostore_out=$(CORTEX_HOME="$T2/.hermes-cortex" python3 "$SCRIPT" 2>&1)
printf '%s\n' "$nostore_out" | sed 's/^/   /'
if [ -e "$T2/.hermes-cortex/state/.governance-nostore.json" ]; then
  echo "PASS  the lock was kept (a lockless PENDING cycle would block every push here)"
else
  echo "FAIL  the lock was removed with no way to resolve its cycle"; FAILED=1
fi
rm -rf "$T" "$T2"

step "4. syntax + the A4 gate on every changed source file"
python3 -m py_compile "$SCRIPT" mcp-servers/loop-gov-mcp.py && echo "COMPILE_OK" || FAILED=1
for f in "$SCRIPT" mcp-servers/loop-gov-mcp.py tests/test_purge_resolves_orphaned_cycles.py \
         tests/test_liveness_anywhere.py tests/test_closer_parity_and_escalation.py; do
  v=$(python3 ops/scripts/quality/adversarial-verify.py --file "$f" --level A4 --gate 2>&1); vrc=$?
  printf '   %s rc=%s : %s\n' "$f" "$vrc" "$(printf '%s\n' "$v" | tail -1)"
  [ "$vrc" -eq 0 ] || FAILED=1
done

echo
if [ "$FAILED" -eq 0 ]; then echo "ALL CLAIMS RE-VERIFIED (rc=0)"; else echo "SOME CLAIMS FAILED (rc=1)"; fi
exit "$FAILED"
