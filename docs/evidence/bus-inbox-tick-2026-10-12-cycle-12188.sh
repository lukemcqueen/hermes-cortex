#!/usr/bin/env bash
# Re-runnable evidence for the Agent Bus inbox tick (cycle 12188, 2026-10-12).
#
# The tick is READ-ONLY: it runs the committed checker
# ops/scripts/orch-bus/bus-inbox-inspect.py (peeks via /api/pgmq/queues and
# /api/pgmq/peek only — never consumes, archives or writes) and asserts the
# fleet has no actionable bus issue. A clean tick exits 0 after printing the
# diagnostic lines below (checker, rcs, snapshot, fingerprint, policy trace);
# the underlying checker's own stdout is EMPTY when clean. It exits non-zero
# the moment anything is actionable: any DLQ depth, message older than
# STALE_HOURS, priority>=URGENT_PRIORITY, unprocessed own-inbox message,
# missing forwarder run, or active failover (fleet_issues() in the checker is
# the policy; this script re-applies it to the committed snapshot as a trace).
#
# CLEAN requires ALL of: live `--issues` rc=0 with zero issue lines, a valid
# non-empty JSON snapshot passing semantic validation, a completed snapshot
# policy trace, and the trace's issue count to EQUAL the live issue count
# (agreement between the two probes). Anything else is UNVERIFIABLE (exit 2) —
# never CLEAN, and never ISSUES on a guess.
#
# Snapshot target: $SNAPSHOT_OUT, else ~/.hermes-cortex/state/bus-inbox-tick-last.json.
# Set SNAPSHOT_OUT into docs/evidence/ to commit the exact JSON a run verified.
# Test seams (defaults are the real ones): $CHECKER overrides the checker path.
# The trace always exits 0 (it is a reporter); ISSUES/exit 1 is reached when
# live and trace agree on a non-zero issue count.
#
# Exit 0 == verified no-op (silent tick). Exit 1 == a real issue existed.
# Exit 2 == the scan could not be verified (checker/snapshot/trace failed).
set -uo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)" || exit 1

snapshot="${SNAPSHOT_OUT:-$HOME/.hermes-cortex/state/bus-inbox-tick-last.json}"
mkdir -p "$(dirname "$snapshot")"

checker="${CHECKER:-ops/scripts/orch-bus/bus-inbox-inspect.py}"

issues="$(python3 "$checker" esther --issues)"
rc=$?
live_count=0
if [ -n "$issues" ]; then
  live_count="$(printf '%s\n' "$issues" | grep -c .)"
fi
python3 "$checker" esther > "$snapshot"
snap_rc=$?

printf 'checker=%s\n' "$(printf '%s' "$checker" | sed "s|^$HOME|~|")"
printf 'issues_rc=%s\n' "$rc"
printf 'issues_stdout=%s\n' "${issues:-<empty>}"
printf 'issues_count=%s\n' "$live_count"
printf 'snapshot=%s\n' "$(printf '%s' "$snapshot" | sed "s|^$HOME|~|")"
printf 'snapshot_rc=%s\n' "$snap_rc"

# Fail closed #1: checker failed but printed no reason — probe fault, not clean.
if [ "$rc" -ne 0 ] && [ "$live_count" -eq 0 ]; then
  printf 'verdict=UNVERIFIABLE (checker rc=%s, no issue text — probe fault)\n' "$rc"
  exit 2
fi
# Fail closed #2: snapshot unwritten / empty / not JSON.
if [ "$snap_rc" -ne 0 ] || [ ! -s "$snapshot" ] \
   || ! python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$snapshot"; then
  printf 'verdict=UNVERIFIABLE (snapshot rc=%s, file missing/empty/invalid JSON)\n' "$snap_rc"
  exit 2
fi

# Fail closed #3: semantic validation. The checker's "nonempty" list is
# "notable queues" — it lists every *_dlq queue even at depth 0 (so its is_dlq
# flag is visible). A syntactically valid snapshot is only trustworthy if that
# invariant holds: any non-dlq entry must carry depth>0 or processing>0, and
# every name ending in _dlq must be flagged dlq=true. (A DLQ at depth>0 is a
# REAL issue handled by fleet_issues(), not a snapshot defect.)
if ! python3 - "$snapshot" <<'PYSEM'; then
import json, sys
report = json.load(open(sys.argv[1]))
bad = []
for bus in report.get("buses", []):
    label = bus.get("label")
    for q in bus.get("nonempty", []):
        name = q.get("name", "?")
        depth, proc = q.get("depth", 0), q.get("processing", 0)
        if name.endswith("_dlq") and not q.get("dlq"):
            bad.append(f"{label}:{name} name says dlq but dlq flag is false")
        if not name.endswith("_dlq") and not q.get("dlq") and depth == 0 and proc == 0:
            bad.append(f"{label}:{name} listed as notable with depth=0 processing=0")
    listed = {q.get("name") for q in bus.get("nonempty", [])}
    for d in bus.get("dlq", []):
        if not d.get("name", "").endswith("_dlq"):
            bad.append(f"{label}:{d['name']} in dlq list but name does not end _dlq")
        if (d.get("depth", 0) or d.get("processing", 0)) and d.get("name") not in listed:
            bad.append(f"{label}:{d['name']} has backlog but is absent from nonempty")
if bad:
    print("semantic_inconsistencies=" + str(len(bad)))
    for x in bad:
        print("  " + x)
    sys.exit(1)
print("semantic_check=ok")
sys.exit(0)
PYSEM
  printf 'verdict=UNVERIFIABLE (snapshot failed semantic validation)\n'
  exit 2
fi

printf 'snapshot_sha256=%s\n' "$(sha256sum "$snapshot" | awk '{print $1}')"

# Policy trace: re-apply the checker's own fleet_issues() to the committed
# snapshot and show, per queued message, its age vs STALE_HOURS and priority
# vs URGENT_PRIORITY — so a non-empty queue with zero issues is auditable.
# Prints trace_fleet_issues_count=N; exits 1 when the snapshot has issues.
trace_out="$(python3 - "$snapshot" <<'PYTRACE'
import importlib.util, json, sys
from datetime import datetime, timedelta, timezone

spec = importlib.util.spec_from_file_location(
    "bus_inbox_inspect", "ops/scripts/orch-bus/bus-inbox-inspect.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

report = json.load(open(sys.argv[1]))
now = datetime.now(timezone.utc)
own = f"inbox_{report.get('agent')}"
issues_list = m.fleet_issues(report)
print(f"policy STALE_HOURS={m.STALE_HOURS} URGENT_PRIORITY={m.URGENT_PRIORITY} own_inbox={own}")
print(f"trace_fleet_issues_count={len(issues_list)}")
for issue in issues_list:
    print(f"trace_issue: {issue}")
for bus in report.get("buses", []):
    if bus.get("inspection_error"):
        print(f"  {bus['label']} INSPECTION_ERROR {bus['inspection_error']}")
    for qn, peek in (bus.get("peeks") or {}).items():
        for msg in peek.get("messages") or []:
            ts = m._parse_ts(msg.get("enqueued_at"))
            age_h = round((now - ts).total_seconds() / 3600, 3) if ts else None
            prio = msg.get("priority")
            print(f"  {bus['label']} {qn} from={msg.get('from')} to={msg.get('to')} "
                  f"subject={msg.get('subject')} priority={prio} age_h={age_h} "
                  f"stale={None if age_h is None else age_h > m.STALE_HOURS} "
                  f"urgent={isinstance(prio, int) and prio >= m.URGENT_PRIORITY} "
                  f"is_own_inbox={qn == own}")
sys.exit(0)
PYTRACE
)"
trace_rc=$?
printf '%s\n' "$trace_out"
trace_count="$(printf '%s\n' "$trace_out" | sed -n 's/^trace_fleet_issues_count=//p')"

# Fail closed #4: the trace must actually run and produce its count. The trace
# ALWAYS exits 0 when it completes (it is a reporter, not a gate); a non-zero
# rc or a missing count means it crashed — the verdict is then unverifiable.
# Agreement gate: the snapshot trace must diagnose exactly what the live
# --issues probe did; disagreement means the verdict is unverifiable.
if [ "$trace_rc" -ne 0 ] || [ -z "$trace_count" ]; then
  printf 'verdict=UNVERIFIABLE (policy trace rc=%s, count missing)\n' "$trace_rc"
  exit 2
fi
if [ "$trace_count" != "$live_count" ]; then
  printf 'verdict=UNVERIFIABLE (probe disagreement: live=%s trace=%s)\n' "$live_count" "$trace_count"
  exit 2
fi

if [ "$live_count" -eq 0 ]; then
  printf 'verdict=CLEAN (no actionable bus issue)\n'
  exit 0
fi
printf 'verdict=ISSUES\n%s\n' "$issues"
exit 1
