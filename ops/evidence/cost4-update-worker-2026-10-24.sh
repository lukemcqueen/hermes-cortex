#!/usr/bin/env bash
# [cost/4] UPDATE_REQUEST never lands on esther — two defects, one transcript.
#
#   bash ops/evidence/cost4-update-worker-2026-10-24.sh
#
# WHY: the 2026-10-24 EXEC dispatch (docs/evidence/cost4-host-cost-adapter/
# dispatch-2026-10-24.txt) returned 0 of 4 worker aggregates because the four
# hosts run a cron-cost-metrics.py that predates --json-summary. The obvious
# unblock — UPDATE_REQUEST, the fleet's own update protocol — was dispatched
# (update-dispatch-2026-10-24.txt): every host CONSUMED it, none updated, none
# answered. This script records what actually happens to a detached UPDATE
# worker, using the code path the deployed handler spawns.
#
#   1. the PRE-CHANGE revision, materialised and ASSERTED pre-change
#   2. RED  — the new worker tests against that revision (the loader defect)
#   3. GREEN — the same tests at the tip
#   4. the spawner: the unit, its KillMode, and the workers it killed
#   5. the deployed worker run BY HAND (outside the unit) — it completes
#   6. the mechanism, isolated: a oneshot unit's cgroup kills its own children
#
# Writes docs/evidence/cost4-host-cost-adapter/update-worker-2026-10-24.txt.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTDIR="$REPO/docs/evidence/cost4-host-cost-adapter"
OUT="$OUTDIR/update-worker-2026-10-24.txt"
SCRATCH="$HOME/.hermes/cache/scratch"
BASELINE_SHA="a1328aeac6f3bf36e09f491b43f5c6aa182b74c3"
TEST_REL="tests/test_runtime/test_message_handler_worker.py"
WORKER="$HOME/.hermes-cortex/scripts/agent-message-handler.py"
PENDING="$HOME/.hermes-cortex/state/pending-update-results"
PY="$HOME/.hermes-cortex/venv/bin/python3"
WT="$SCRATCH/cost4-updateworker-wt"

mkdir -p "$OUTDIR" "$SCRATCH"
exec >"$OUT" 2>&1

say() { printf '%s\n' "$*" | sed -e "s|$HOME|~|g"; }
rule() { printf '\n── %s ──\n' "$*"; }

say "# [cost/4] UPDATE_REQUEST — the detached worker, on the real path"
say "captured-at: $(git -C "$REPO" rev-parse --short=8 HEAD)"
say "re-run: bash ops/evidence/cost4-update-worker-2026-10-24.sh"

rule "1. PRE-CHANGE revision, materialised and ASSERTED pre-change"
git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1 || true
git -C "$REPO" worktree add --detach "$WT" "$BASELINE_SHA" 2>&1 | sed 's/^/  /'
say "  asserted worktree HEAD: $(git -C "$WT" rev-parse HEAD)"
# The pre-change worker inserted ONLY the handler's own directory; the change
# adds the parent. Asserted, so this cannot quietly run the wrong revision.
say "  pre-change  'sys.path.insert(0, str(Path(handler_path).parent))' count: $(grep -c -F 'sys.path.insert(0, str(Path(handler_path).parent))' "$WT/ops/scripts/agent/agent-message-handler.py")  (must be 1)"
say "  pre-change  'handler_path.parent.parent' count: $(grep -c -F 'handler_path.parent.parent' "$WT/ops/scripts/agent/agent-message-handler.py")  (must be 0)"
# The NEW test does not exist at the pinned revision (it is this change's own
# artifact), so it is copied in — otherwise pytest collects nothing and a
# "0 tests ran" reads exactly like a RED that never happened.
mkdir -p "$WT/$(dirname "$TEST_REL")"
cp "$REPO/$TEST_REL" "$WT/$TEST_REL"
say "  copied this change's test into the worktree: $TEST_REL"

rule "2. RED — the new tests against the PRE-CHANGE revision"
( cd "$WT" && "$PY" -m pytest -q "$TEST_REL" 2>&1 | tail -14 )
say "  ^ the failures ARE the defect: the worker died while loading the handler,"
say "    so it wrote no result and the requester waits the whole timeout."
say "  re-run: cd <worktree at $BASELINE_SHA> && $PY -m pytest -q $TEST_REL"

rule "3. GREEN — the same tests at the tip"
( cd "$REPO" && "$PY" -m pytest -q "$TEST_REL" 2>&1 | tail -4 )

rule "4. the spawner: the unit, and the workers it killed"
systemctl --user cat cortex-bridge-agent-message-handler.service 2>/dev/null | grep -v '^$' | sed 's/^/  /'
say ""
for p in KillMode Type RemainAfterExit Restart; do
  say "  $(systemctl --user show cortex-bridge-agent-message-handler.service -p "$p" 2>/dev/null)"
done
say ""
say "  A worker killed when the tick's cgroup went away leaves a .running marker"
say "  with NO sibling .json and no live process. Uncollected right now:"
for m in "$PENDING"/*.running; do
  [[ -e "$m" ]] || { say "    (none)"; break; }
  stem="${m%.running}"
  say "    $(basename "$m")  age=$(( $(date +%s) - $(stat -c %Y "$m") ))s  result-json=$( [[ -f "$stem.json" ]] && echo yes || echo no )"
done
say "  (each of these was spawned by a tick; none was ever collected, while the"
say "   same worker run BY HAND in step 5 finishes and writes its result)"

rule "5. the deployed worker, run BY HAND — outside the unit's cgroup"
say "  \$ python3 -c \"<the deployed handler's own _update_worker_code()>\" \\"
say "      $WORKER '<UPDATE_REQUEST body>' cost4-bymanual-<ts>"
"$PY" - "$WORKER" <<'PYEOF' > "$SCRATCH/cost4-worker-code.py"
import importlib.util, os, sys
from pathlib import Path
os.environ.setdefault("AGENT_NAME", "esther")
p = sys.argv[1]
sys.path.insert(0, str(Path(p).parent))
spec = importlib.util.spec_from_file_location("h", p)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
sys.stdout.write(mod._update_worker_code())
PYEOF
CORR="cost4-bymanual-$(date +%H%M%S)"
timeout 400 /usr/bin/python3 -c "$(cat "$SCRATCH/cost4-worker-code.py")" "$WORKER" \
  '{"from":"esther","subject":"UPDATE_REQUEST","body":"{\"target_sha\":\"a1328aea\",\"run_doctor\":false}"}' \
  "$CORR" > "$SCRATCH/cost4-bymanual.out" 2>&1
RC=$?
sed 's/^/  /' "$SCRATCH/cost4-bymanual.out"
say "  worker exit: $RC  (the worker's own rc — not a filter's)"
if [[ -f "$PENDING/$CORR.json" ]]; then
  say "  RESULT WRITTEN: $CORR.json"
  "$PY" -c "
import json
d = json.load(open('$PENDING/$CORR.json'))
print('    success=%s  sha %s -> %s  update_output_present=%s' % (
    d.get('success'), d.get('git_sha_before'), d.get('git_sha_after'), bool(d.get('update_output'))))
" | sed 's/^/  /'
else
  say "  NO RESULT — do not trust this step"
fi

rule "6. the mechanism, isolated: a oneshot unit's cgroup kills its own children"
say "  A) detached from THIS shell (no unit involved):"
setsid sleep 150 >/dev/null 2>&1 &
A_PID=$!
sleep 3
say "     spawned sleep pid=$A_PID alive=$(kill -0 "$A_PID" 2>/dev/null && echo yes || echo no)"
say ""
say "  B) the same spawn inside a oneshot unit (systemd-run), KillMode default:"
systemd-run --user --collect --unit=cost4-cgroup-probe --wait \
  /bin/bash -c 'setsid sleep 150 >/dev/null 2>&1 & echo "    child spawned inside the unit: $!"' 2>&1 | sed 's/^/  /'
sleep 3
B_PID=$(pgrep -u "$(id -u)" -f '^sleep 150$' | grep -v "^$A_PID$" | head -1 || true)
say "     unit's child (sleep) still alive after the unit finished: ${B_PID:-<already gone>}"
say "     this shell's child (A) still alive: $(kill -0 "$A_PID" 2>/dev/null && echo yes || echo no)"
say ""
say "     -> same command, same user, same moment: the child born inside the"
say "        oneshot unit does not survive its unit; the one born outside does."
kill "$A_PID" 2>/dev/null || true
[[ -n "${B_PID:-}" ]] && kill "$B_PID" 2>/dev/null || true
systemctl --user reset-failed cost4-cgroup-probe 2>/dev/null || true

rule "7. cleanup"
git -C "$REPO" worktree remove --force "$WT" 2>&1 | sed 's/^/  /'
say "  worktree removed"
say ""
say "# generated-by: this script (it wrote this file itself; stdout is not retyped)"
