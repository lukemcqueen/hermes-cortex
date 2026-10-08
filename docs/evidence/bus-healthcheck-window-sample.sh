#!/usr/bin/env bash
# bus-healthcheck-window-sample.sh — regenerate the bus time-window sampling
# raw output for the agent-bus cron evidence.
#
# Reads only lib.cortex_bus (bus_list_queues — non-consuming) every 5s for 75s
# and prints depth/processing for the in-scope queues. Output is written to
# docs/evidence/bus-healthcheck-window-2026-10-08.raw.txt (overwrites).
#
# Usage: bash bus-healthcheck-window-sample.sh
set -euo pipefail

HC_SCRIPTS="${HOME}/.hermes-cortex/scripts"
OUT="${HOME}/hermes-cortex/docs/evidence/bus-healthcheck-window-2026-10-08.raw.txt"

TOTAL=75
STEP=5
TARGETS="inbox_health_check inbox_orchestrator inbox_titus inbox_orchestrator_dlq"

python3 - "$HC_SCRIPTS" "$OUT" "$TOTAL" "$STEP" "$TARGETS" <<'PY'
import sys, time, json
sys.path.insert(0, sys.argv[1])
out_path, total, step = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
targets = [t for t in sys.argv[5].split() if t]
from lib.cortex_bus import bus_list_queues

lines = []
lines.append(f"Sampling every {step}s for {total}s. Fields: depth/processing")
seen = {}
for t in range(0, total + 1, step):
    queues = bus_list_queues()
    row = {}
    for q in queues:
        if q.get("name") in targets:
            row[q["name"]] = (q.get("depth"), q.get("processing"))
            seen.setdefault(q["name"], set()).add((q.get("depth"), q.get("processing")))
    parts = [f"{n}=d{row[n][0]}p{row[n][1]}" for n in targets if n in row]
    lines.append(f"t={t:>3}s  " + "  ".join(parts))
    if t + step <= total:
        time.sleep(step)
lines.append("")
lines.append("=== unique (depth,processing) states observed per queue ===")
for n in targets:
    lines.append(f"  {n}: {sorted(seen.get(n, []))}")
with open(out_path, "w") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"wrote {out_path} ({len(lines)} lines)")
PY

echo "done"
