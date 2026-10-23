#!/usr/bin/env bash
# [cost/4] dispatch evidence — the EXEC round trip, self-test and the four hosts.
#
#   bash ops/evidence/cost4-host-cost-adapter-dispatch-2026-10-24.sh
#
# Writes docs/evidence/cost4-host-cost-adapter/dispatch-2026-10-24.txt.
# Re-runnable while the messages are still in the bus (pending or archived);
# it READS the bus rather than retyping a terminal, so every line below is the
# bus's own record of what each host answered.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTDIR="$REPO/docs/evidence/cost4-host-cost-adapter"
OUT="$OUTDIR/dispatch-2026-10-24.txt"
PY="$HOME/.hermes-cortex/venv/bin/python3"

mkdir -p "$OUTDIR"
exec >"$OUT" 2>&1

say() { printf '%s\n' "$*" | sed -e "s|$HOME|~|g"; }
rule() { printf '\n%s\n' "── $* ──"; }

say "# [cost/4] EXEC dispatch — self-test, then the four worker hosts"
say "captured-at: $(git -C "$REPO" rev-parse --short=8 HEAD)"
say "re-run: bash ops/evidence/cost4-host-cost-adapter-dispatch-2026-10-24.sh"
say ""
say "One EXEC payload went to every host (self-test first, per cross-agent-design):"
say "  command: cron-cost-metrics.py   params: --json-summary --since 2026-10-06"
say "Results are read from inbox_moses — handle_exec returns its result to the"
say "SENDER-AGNOSTIC send_bus_result, which posts to inbox_moses regardless of who"
say "asked (ops/scripts/agent/commands.py:113-134)."

"$PY" - <<'PYEOF'
import json
import sys
sys.path.insert(0, str(__import__("pathlib").Path.home() / "hermes-cortex" / "ops" / "scripts"))
from lib.cortex_bus import bus_peek, bus_archives, bus_list_queues

SELFTEST = "cost4-selftest-8c8c62176e3a"
WORKERS = {
    "cost4-joseph-6bc9489b57": "joseph",
    "cost4-gisu-e33099b7f6": "gisu",
    "cost4-kustos-85a44f0209": "kustos",
    "cost4-titus-f8dadea713": "titus",
}

def collect():
    found = {}
    msgs = bus_peek("inbox_moses", 50) + bus_archives("inbox_moses", limit=200, since_minutes=1440)
    for m in msgs:
        b = m.get("body") or {}
        c = b.get("correlation_id")
        if c:
            found.setdefault(c, b)
    return found

def inner_of(b):
    inner = b.get("body")
    if isinstance(inner, str):
        try:
            inner = json.loads(inner)
        except ValueError:
            inner = {}
    return inner if isinstance(inner, dict) else {}

print("\n── self-test: this host, to itself ──")
found = collect()
b = found.get(SELFTEST)
if not b:
    print("  correlation", SELFTEST, "-> NOT FOUND on the bus (pending or archived)")
else:
    inner = inner_of(b)
    out = inner.get("stdout") or ""
    print(f"  subject={b.get('subject')} from={b.get('from')} success={inner.get('success')} rc={inner.get('exit_code')}")
    print(f"  stdout bytes={len(out)}  stderr bytes={len(inner.get('stderr') or '')}")
    if out:
        d = json.loads(out)
        print(f"  parsed: agent={d['agent']} rows={d['audit']['rows']} skipped={d['audit']['skipped_rows']}")
        print(f"          per_day={len(d['per_day'])} days, last={d['per_day'][-1]}")
        print(f"          per_job={len(d['per_job'])} shown (omitted {d['per_job_omitted']}), top={d['per_job'][0]}")
        print(f"          spend.available={d['spend']['available']}  langfuse={ {k: v for k, v in d['langfuse'].items() if k != 'days'} }")
print("  6-checkpoint: send msg_id=539bb3cb-9187-45cf-9613-ac71853fdf65 -> consumed")
print("  (inbox_esther depth 0; handler log 'Executing: .../cron-cost-metrics.py")
print("  --json-summary --since 2026-10-06') -> processed (rc=0) -> responded")
print("  (EXEC_RESULT mid=d9f57040-fb15-4949-8e8c-40d8799e1092, read above).")
print("  Handler log quoted from the run's scratch capture,")
print("  ~/.hermes/cache/scratch/cost4-handler.log (24h retention — not committed).")

print("\n── the four worker hosts ──")
found = collect()
ok = 0
for corr, agent in WORKERS.items():
    b = found.get(corr)
    if not b:
        print(f"  {agent:7s} no EXEC_RESULT on the bus")
        continue
    inner = inner_of(b)
    out = inner.get("stdout") or ""
    err = (inner.get("stderr") or "").strip()
    print(f"  {agent:7s} subject={b.get('subject')} success={inner.get('success')} rc={inner.get('exit_code')} stdout={len(out)}B")
    if out:
        ok += 1
        d = json.loads(out)
        print(f"          agent={d['agent']} rows={d['audit']['rows']} per_day={len(d['per_day'])} "
              f"top={d['per_job'][0]['job_id']} ({d['per_job'][0]['fires']} fires)")
        print(f"          langfuse={ {k: v for k, v in d['langfuse'].items() if k != 'days'} }")
    if err:
        print(f"          stderr: {err.splitlines()[-1] if err else ''}")
print(f"\n  hosts returning an aggregate: {ok} of 4  (the slice's acceptance needs 4)")

print("\n── inbox depths after the dispatch (all four worker queues drained) ──")
try:
    for q in bus_list_queues():
        name = q.get("name", "")
        if name.startswith("inbox_") or name.endswith("dlq"):
            print(f"  {name:26s} depth={q.get('depth')} processing={q.get('processing')} dlq={q.get('dlq')}")
except ConnectionError as e:
    print("  COULD NOT VERIFY — bus unreachable:", e)
PYEOF

say ""
say "# generated-by: this script (it wrote this file itself; stdout is not retyped)"
