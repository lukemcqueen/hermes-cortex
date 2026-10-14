#!/usr/bin/env bash
# Re-verify the purge script's import guard and the three-session isolation claim.
#
#   bash docs/evidence/purge-import-guard-verify.sh [repo-path]
#
# Exit 0 only when every claim re-verifies.
set -uo pipefail

REPO="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO" || { echo "no such repo: $REPO"; exit 2; }
STATEFILE=ops/scripts/manage/purge-stale-governance-locks.py
FAILED=0

# Redact the absolute home prefix from EVERYTHING this script prints, at the source: the
# transcript is a committed artifact, and a host path in it is a defect. Doing it here rather
# than with a sed pass over the captured file keeps the artifact equal to the command's output.
exec > >(sed "s|$HOME|~|g") 2>&1

step() { echo; echo "--- $*"; }

step "1. import-safety contract tests (both directions: inert import, working purge)"
out=$(bash tests/run-tests.sh tests/test_purge_script_import_safety.py -q 2>&1); rc=$?
printf '%s\n' "$out" | tail -2
[ "$rc" -eq 0 ] && echo "PASS  rc=0" || { echo "FAIL  rc=$rc"; FAILED=1; }

step "2. the three-session probe: throwaway state dir + DB, real purge/release/repair paths"
python3 docs/evidence/three-session-isolation-probe.py "$REPO"
[ "$?" -eq 0 ] && echo "PASS  every check held" || { echo "FAIL  a check above failed"; FAILED=1; }

step "3. the script still compiles and still runs as a script (the cron's path)"
python3 -m py_compile "$STATEFILE" && echo "COMPILE_OK" || { echo "FAIL  compile"; FAILED=1; }
tmp_home=$(mktemp -d); mkdir -p "$tmp_home/.hermes-cortex/state"
python3 - "$tmp_home" <<'PY'
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
old = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
(Path(sys.argv[1]) / ".hermes-cortex" / "state" / ".governance-verify-stale.json").write_text(
    json.dumps({"heartbeat_at": old, "started_at": old, "ttl_seconds": 3600,
                "task_id": "verify-stale-task", "status": "executing"}))
PY
run_out=$(HOME="$tmp_home" python3 "$STATEFILE" 2>&1); run_rc=$?
printf '   %s (rc=%s)\n' "$run_out" "$run_rc"
[ "$run_rc" -eq 0 ] && printf '%s' "$run_out" | grep -q "Purged 1 stale" \
  && [ ! -e "$tmp_home/.hermes-cortex/state/.governance-verify-stale.json" ] \
  && echo "PASS  the CLI removed the stale lock and reported it" \
  || { echo "FAIL  CLI purge path broken"; FAILED=1; }
rm -rf "$tmp_home"

step "4. the defect's exact signature on the LIVE state dir: an import must change nothing"
LIVE="$HOME/.hermes-cortex/state"
before=$(ls -1 "$LIVE" 2>/dev/null | wc -l)
python3 - "$STATEFILE" <<'PY' 2>&1 | tail -1
import importlib.util, sys
spec = importlib.util.spec_from_file_location("purge_import_verify", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print(f"   imported; STATE_DIR resolves to {mod.STATE_DIR}")
PY
after=$(ls -1 "$LIVE" 2>/dev/null | wc -l)
if [ "$before" = "$after" ]; then
  echo "PASS  live state dir unchanged by the import ($before entries before and after)"
else
  echo "FAIL  live state dir changed by the import: $before -> $after"; FAILED=1
fi

echo
if [ "$FAILED" -eq 0 ]; then
  echo "ALL CLAIMS RE-VERIFIED (rc=0)"
else
  echo "SOME CLAIMS FAILED (rc=1)"
fi
exit "$FAILED"
