#!/usr/bin/env bash
# Self-contained branch test for the Agent Bus tick evidence script
# (docs/evidence/bus-inbox-tick-2026-10-12-cycle-12188.sh, cycle 12188).
#
# A clean tick alone proves nothing about the failure paths, so this builds a
# throwaway stub checker in a temp dir and asserts all three exits of the
# evidence script: A real bus -> 0 (CLEAN), B unwritable snapshot -> 2
# (UNVERIFIABLE, fail closed), C injected issue -> 1 (ISSUES, live and trace
# agreeing). Exit 0 only when all three match; prints the real transcripts.
set -uo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)" || exit 1

ev=docs/evidence/bus-inbox-tick-2026-10-12-cycle-12188.sh
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

stub="$tmp/stub_checker_issues.py"
cat > "$stub" <<'PY'
# Hermetic stub of ops/scripts/orch-bus/bus-inbox-inspect.py (test only).
import json, sys
REPORT = {"ts": "2026-10-12T00:00:00+00:00", "agent": "esther",
 "buses": [{"label": "local", "base": "stub", "inspection_error": None, "queue_total": 1,
   "nonempty": [{"name": "inbox_esther_dlq", "depth": 1, "processing": 0, "dlq": True,
                 "parent": "inbox_esther"}],
   "dlq": [{"name": "inbox_esther_dlq", "depth": 1, "processing": 0}], "peeks": {}},
  {"label": "primary", "base": "stub", "inspection_error": None, "queue_total": 0,
   "nonempty": [], "dlq": [], "peeks": {}}],
 "forwarder": {"last_run": "2026-10-12T00:00:00+00:00", "total_forwarded": 0,
               "total_peer_to_local": 0, "total_local_to_peer": 0},
 "failover": {"failover_active": False}}
argv = sys.argv[1:]
if "esther" in argv and "--issues" in argv:
    print("local: BLOCKED (DLQ) inbox_esther_dlq depth=1 processing=0")
    raise SystemExit(1)
print(json.dumps(REPORT))
raise SystemExit(0)
PY

fail=0
probe() {  # probe <label> <expected_rc> <env...>
  local label="$1" want="$2"; shift 2
  local out rc
  out="$(env "$@" bash "$ev" 2>&1)"; rc=$?
  printf '### %s (expect rc=%s)\n%s\nrc=%s\n\n' "$label" "$want" "$out" "$rc"
  [ "$rc" -eq "$want" ] || { printf 'PROBE FAILED: %s rc=%s want=%s\n' "$label" "$rc" "$want"; fail=1; }
}

probe "A real bus -> CLEAN" 0 SNAPSHOT_OUT="$tmp/a.json"
probe "B unwritable snapshot -> UNVERIFIABLE" 2 SNAPSHOT_OUT=/proc/nope/x.json
probe "C injected issue -> ISSUES" 1 CHECKER="$stub" SNAPSHOT_OUT="$tmp/c.json"

if [ "$fail" -eq 0 ]; then
  printf 'branches_ok=3/3\n'
  exit 0
fi
printf 'branches_ok=FAILED\n'
exit 1
