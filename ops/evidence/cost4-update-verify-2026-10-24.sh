#!/usr/bin/env bash
# [cost/4] verify the UPDATE_REQUEST dispatch — read the bus's own record.
#
#   bash ops/evidence/cost4-update-verify-2026-10-24.sh
#
# Reads the correlation ids the dispatch persisted (~/.hermes/cache/scratch/
# cost4-update-corrs.json) and looks each one up on the bus (pending peek +
# archived). A host that answered shows its git SHA before/after and its doctor
# verdict; a host that has not answered yet shows NOT FOUND. Nothing is retyped
# from a terminal — every line is the bus's record.
#
# Writes docs/evidence/cost4-host-cost-adapter/update-verify-2026-10-24.txt.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTDIR="$REPO/docs/evidence/cost4-host-cost-adapter"
OUT="$OUTDIR/update-verify-2026-10-24.txt"
CORRS="$HOME/.hermes/cache/scratch/cost4-update-corrs.json"
PY="$HOME/.hermes-cortex/venv/bin/python3"

mkdir -p "$OUTDIR"
exec >"$OUT" 2>&1

printf '%s\n' "# [cost/4] UPDATE_REQUEST verify — what the bus recorded"
printf 'captured-at: %s\n' "$(git -C "$REPO" rev-parse --short=8 HEAD)"
printf 're-run: bash ops/evidence/cost4-update-verify-2026-10-24.sh\n\n'

"$PY" - <<'PYEOF'
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "hermes-cortex" / "ops" / "scripts"))
from lib.cortex_bus import bus_peek, bus_archives, bus_list_queues

CORRS = Path.home() / ".hermes/cache/scratch/cost4-update-corrs.json"
sent = json.loads(CORRS.read_text())

# UPDATE_RESULT lands in inbox_moses (handle_* → send_bus_result, sender-agnostic).
seen = {}
for m in bus_peek("inbox_moses", 50) + bus_archives("inbox_moses", limit=400, since_minutes=1440):
    b = m.get("body") or {}
    if isinstance(b.get("body"), str):
        try:
            b = dict(b, body=json.loads(b["body"]))
        except ValueError:
            pass
    c = b.get("correlation_id")
    if c:
        seen.setdefault(c, b)

print("── per-correlation result ──")
answered = 0
for agent, info in sent.items():
    corr = info["correlation_id"]
    kind = info["kind"]
    b = seen.get(corr)
    label = f"{agent} ({kind})"
    if not b:
        print(f"  {label:22s} NOT FOUND on the bus yet (msg_id={info['msg_id'][:8]}…)")
        continue
    inner = b.get("body") or {}
    answered += 1
    print(f"  {label:22s} subject={b.get('subject')} from={b.get('from')} "
          f"success={inner.get('success')} sha={inner.get('git_sha_before')} -> {inner.get('git_sha_after')}")
    if inner.get("error"):
        print(f"        error: {str(inner['error'])[:180]}")
    if inner.get("errors"):
        for e in inner["errors"][:3]:
            print(f"        error: {str(e)[:150]}")
    upd = (inner.get("update_output") or "").strip().splitlines()
    if upd:
        print(f"        update tail: {upd[-1][:150]}")
print(f"\n  answered: {answered} of {len(sent)}")

print("\n── inbox depths ──")
for q in bus_list_queues():
    n = q.get("name", "")
    if n.startswith("inbox_") or n.endswith("dlq"):
        print(f"  {n:26s} depth={q.get('depth')} processing={q.get('processing')} dlq={q.get('dlq')}")
PYEOF

printf '\n%s\n' "# generated-by: this script (it wrote this file itself; stdout is not retyped)"
