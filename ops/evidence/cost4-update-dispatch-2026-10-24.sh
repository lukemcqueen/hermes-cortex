#!/usr/bin/env bash
# [cost/4] UPDATE_REQUEST dispatch — self-test on this host, then the four
# worker hosts that must run cron-cost-metrics.py --json-summary.
#
#   bash ops/evidence/cost4-update-dispatch-2026-10-24.sh
#
# WHY: the 2026-10-24 EXEC dispatch (docs/evidence/cost4-host-cost-adapter/
# dispatch-2026-10-24.txt) returned 0 of 4 aggregates: joseph/kustos/titus run
# a cron-cost-metrics.py that predates --json-summary (rc=2, missing
# --prometheus) and gisu has no such deployed script. The change is already
# pushed (a1328aea == origin/main); the four hosts only need to pull+redeploy.
# UPDATE_REQUEST is the fleet's own protocol for exactly that (handler:
# ops/scripts/agent/commands.py handle_update → cortex-update.sh + doctor).
#
# Sent with from=esther, NOT via ops/scripts/orch-bus/orch-bus-fleet-dispatch.py
# — that script hardcodes "from": "moses", which from this host would be
# impersonation (SOUL #3). It also targets moses/esther; this dispatch is scoped
# to the four worker hosts the slice needs.
#
# Writes docs/evidence/cost4-host-cost-adapter/update-dispatch-2026-10-24.txt,
# and ~/.hermes/cache/scratch/cost4-update-corrs.json (the correlation ids the
# verify step reads back).
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTDIR="$REPO/docs/evidence/cost4-host-cost-adapter"
OUT="$OUTDIR/update-dispatch-2026-10-24.txt"
CORRS="$HOME/.hermes/cache/scratch/cost4-update-corrs.json"
PY="$HOME/.hermes-cortex/venv/bin/python3"

mkdir -p "$OUTDIR" "$(dirname "$CORRS")"
exec >"$OUT" 2>&1

say() { printf '%s\n' "$*" | sed -e "s|$HOME|~|g"; }

say "# [cost/4] UPDATE_REQUEST dispatch — self-test, then the four worker hosts"
say "captured-at: $(git -C "$REPO" rev-parse --short=8 HEAD)"
say "re-run: bash ops/evidence/cost4-update-dispatch-2026-10-24.sh"
say ""

"$PY" - <<'PYEOF'
import json
import os
import socket
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path.home() / "hermes-cortex" / "ops" / "scripts"))
from lib.cortex_bus import bus_send, bus_peek
from lib.handoff_schema import validate_payload

CORRS = Path.home() / ".hermes/cache/scratch/cost4-update-corrs.json"
REPO = Path.home() / "hermes-cortex"

import subprocess
sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                     capture_output=True, text=True).stdout.strip()
me = os.environ.get("AGENT_NAME") or "esther"

TARGETS = ["esther", "joseph", "gisu", "kustos", "titus"]

payload = {"target_sha": sha, "target_version": "2.0.0", "run_doctor": True}
valid, errs = validate_payload(payload, "UPDATE_REQUEST")
print(f"payload validated against UPDATE_REQUEST schema: valid={valid} {errs}")
print(f"target sha: {sha}   sender: {me}")
print()

sent = {}
for agent in TARGETS:
    kind = "selftest" if agent == me else "worker"
    corr = f"cost4-{kind}-{agent}-{uuid.uuid4().hex[:10]}"
    body = {
        "from": me,
        "to": agent,
        "subject": "UPDATE_REQUEST",
        "correlation_id": corr,
        "body": dict(payload),
    }
    label = "SELF-TEST (this host)" if agent == me else "worker"
    res = bus_send(f"inbox_{agent}", body)
    mid = (res or {}).get("msg_id", "?") if isinstance(res, dict) else "?"
    ok = bool(res) and not (isinstance(res, dict) and res.get("permanent"))
    print(f"  {label:22s} {agent:8s} -> {ok}  msg_id={str(mid)[:36]}  corr={corr}")
    sent[agent] = {"correlation_id": corr, "msg_id": str(mid), "kind": kind,
                   "sent": ok, "sha": sha, "at_utc": __import__("datetime").datetime.now(
                       __import__("datetime").timezone.utc).isoformat()}

CORRS.write_text(json.dumps(sent, indent=2))
print()
print(f"correlation ids persisted for the verify step: {CORRS}")
PYEOF

say ""
say "── the four worker queues, right after the dispatch ──"
"$PY" - <<'PYEOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "hermes-cortex" / "ops" / "scripts"))
from lib.cortex_bus import bus_list_queues
for q in bus_list_queues():
    n = q.get("name", "")
    if n.startswith("inbox_") and n != "inbox_health_check":
        print(f"  {n:26s} depth={q.get('depth')} processing={q.get('processing')}")
PYEOF

say ""
say "# generated-by: this script (it wrote this file itself; stdout is not retyped)"
