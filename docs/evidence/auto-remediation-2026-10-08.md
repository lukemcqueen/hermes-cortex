# Auto-remediation scan — 2026-10-08 22:33 KST

Result: **nothing to fix** — sensor empty, all spot-checks healthy.

## Re-executable check (committed, verbatim output)

Script: `docs/evidence/remediation-health-check.sh`
Runs the sensor, asserts it is empty, spot-checks disk/Ollama/bus/fences,
prints everything unmodified, exits 0 only on all-clear. Re-run:
```bash
bash docs/evidence/remediation-health-check.sh
```

Committed verbatim output (script_exit=0 = all-clear):
`docs/evidence/remediation-health-check-2026-10-08.out.txt`
```
=== sensor ===
[]
=== sensor_exit=0 ===
=== disk (df -h / | tail -1) ===
/dev/disk3s1s1   926Gi    13Gi    61Gi    18%    484k  638M    0%   /
=== ollama (curl status) ===
200
=== bus (curl status; CORTEX_BUS_URL from .env) ===
401
=== fences ===
balanced
=== done ===
RESULT: PASS (sensor empty, fences balanced)
script_exit=0
```

Notes on values:
- **Bus 401** = auth-gated endpoint reachable (expected; no token sent).
- Script lives under `docs/evidence/` because `tests/` and `ops/scripts/`
  are orchestrator-only paths on this host — this is a non-orchestrator
  committable location. A `tests/`-path regression test would need an
  orchestrator to land it.

## Host context
- `IS_SERVER=false` in `~/hermes-cortex/.env` → non-server host, sensor expected empty (skill: sensor runs only where `IS_SERVER=true`). Empty array is the healthy signal here.
- No fixes applied; read-only audit.