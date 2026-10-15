#!/usr/bin/env bash
# bus-inbox-tick-2026-10-15-cycle-12668.sh — re-runnable capture of the
# 2026-10-15 20:50 KST Agent-Bus inbox tick (governance cycle 12668/12671).
#
# Sections, in order — each label matches the order the script actually runs:
#   1. bus-inbox-inspect.py --issues        (the tick's own silent-policy gate)
#   2. queue / DLQ / forwarder state, both buses (pending grouped, not per-row)
#   3. the remediation itself: the scheduler invocation and its output, then the
#      job's durable run history (which still holds the pre-fix failure)
#   4. enabled cron jobs with last_status != ok — captured here, i.e. AFTER the
#      remediation in section 3
#   5. daily regression gate re-run (the command the cron's script runs)
#   6. scheduler status for the job AFTER the re-run
#   7. health vector AFTER the re-run (index 2 = no_errored_crons)
#   8. doctor overall line + rc
#
# Read-only except 3/5, which re-run an existing cron job's own script (no new
# artifacts). Every emitted line passes through ONE normaliser applied at
# generation time (`bash <this> | sed "s|$HOME|~|g" > <this>.txt`); no committed
# line is hand-patched. The transcript's ONLY elision is the labelled 20-line cap
# on the run history in section 3b; nothing else is dropped.
set -uo pipefail

SCRIPTS="$HOME/.hermes-cortex/scripts"
INSPECT="$HOME/hermes-cortex/ops/scripts/orch-bus/bus-inbox-inspect.py"
JOB=d39c3b3eca5d

echo "=== 1. bus-inbox-inspect.py --issues (empty output + rc=0 == tick silent policy) ==="
python3 "$INSPECT" --issues
echo "rc=$?"

echo
echo "=== 2. queue / DLQ / forwarder state (pending grouped by queue+from+subject) ==="
python3 - "$INSPECT" <<'PY'
import collections, json, os, subprocess, sys
inspect = sys.argv[1]
r = subprocess.run([sys.executable, inspect, "esther"], capture_output=True, text=True)
print("inspect rc=%s" % r.returncode)
d = json.loads(r.stdout)
for b in d["buses"]:
    print("%s: queue_total=%s inspection_error=%s" % (b["label"], b["queue_total"], b["inspection_error"]))
    plain = [(q["name"], q["depth"], q["processing"]) for q in b["nonempty"] if not q.get("dlq")]
    print("  non-DLQ non-empty (name,depth,processing):", plain)
    print("  DLQ non-empty:", [(q["name"], q["depth"], q["processing"])
                               for q in b["dlq"] if q["depth"] or q["processing"]])
    groups = collections.defaultdict(list)
    for qn, peek in b["peeks"].items():
        if isinstance(peek, dict) and peek.get("count"):
            for m in peek["messages"]:
                groups[(qn, m.get("from"), m.get("subject"), m.get("priority"))].append(m["enqueued_at"])
    for (qn, frm, subj, pri), stamps in sorted(groups.items(), key=lambda kv: min(kv[1])):
        print("  pending %-18s from=%-7s subject=%-26s priority=%s n=%d oldest=%s newest=%s" % (
            qn, frm, subj, pri, len(stamps), min(stamps), max(stamps)))
f, fo = d["forwarder"], d["failover"]
print("forwarder: last_run=%s peer_to_local=%s local_to_peer=%s" % (
    f.get("last_run"), f.get("total_peer_to_local"), f.get("total_local_to_peer")))
print("failover: active=%s last_status=%s" % (fo.get("failover_active"), fo.get("last_status")))
PY
echo "rc=$?"

echo
echo "=== 3. the remediation: scheduler invocation, output, then durable run history ==="
echo "--- 3a. command: hermes cron run $JOB"
cron_out="$(hermes cron run "$JOB" 2>&1)"; cron_rc=$?
printf '%s\n' "$cron_out"
echo "rc=$cron_rc"
echo "--- 3b. durable run history (newest first): the 03:15 builtin FAILURE, then the direct runs"
runs_out="$(hermes cron runs "$JOB" 2>&1)"; runs_rc=$?
printf '%s\n' "$runs_out" | sed -n '1,20p'
echo "... (THIS is the transcript's only elision: the run history is capped at 20 lines by sed -n 1,20p)"
echo "rc=$runs_rc"

echo
echo "=== 4. enabled cron jobs with last_status != ok (captured here, i.e. after section 3) ==="
python3 - <<'PY'
import json, os
j = json.load(open(os.path.expanduser("~/.hermes/cron/jobs.json")))
j = j if isinstance(j, list) else j.get("jobs", j)
if isinstance(j, dict):
    j = list(j.values())
bad = [(x.get("name"), x.get("id"), x.get("last_status")) for x in j
       if x.get("enabled", True) and x.get("last_status") not in (None, "ok", "success", "")]
print("enabled jobs total:", len(j))
print("enabled non-ok jobs (at this capture):", len(bad), bad)
PY
echo "rc=$?"

echo
echo "=== 5. daily regression gate re-run (same command the cron's script runs) ==="
cd "$SCRIPTS" && timeout 570 bash lib/python-with-module.sh yaml run-evals.py --suite regression --standalone
echo "rc=$?"

echo
echo "=== 6. scheduler status for the job AFTER the re-run ==="
python3 - "$JOB" <<'PY'
import json, os, sys
j = json.load(open(os.path.expanduser("~/.hermes/cron/jobs.json")))
j = j if isinstance(j, list) else j.get("jobs", j)
if isinstance(j, dict):
    j = list(j.values())
for x in j:
    if x.get("id") == sys.argv[1]:
        print("last_status=%s failure_streak=%s last_run_at=%s" % (
            x.get("last_status"), x.get("failure_streak"), x.get("last_run_at")))
PY
echo "rc=$?"

echo
echo "=== 7. health vector AFTER the re-run (index 2 == no_errored_crons) ==="
timeout 300 python3 "$SCRIPTS/health-vector.py" --json
echo "rc=$?"

echo
echo "=== 8. doctor overall line ==="
doc_out="$(timeout 900 python3 "$SCRIPTS/cortex-doctor.py" --quiet 2>&1)"; doc_rc=$?
printf '%s\n' "$doc_out" | grep -E "Overall:" || echo "(no Overall line captured)"
echo "rc=$doc_rc  (warnings do not block; the push gate blocks on FAIL only)"
