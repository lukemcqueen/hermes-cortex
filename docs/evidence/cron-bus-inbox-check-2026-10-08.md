# Agent Bus Inbox Check — Evidence (Titus, 2026-10-08)

Re-executable probe: `docs/evidence/cron-bus-inbox-check.py`
Run command: `python3 docs/evidence/cron-bus-inbox-check.py`

## Captured run — 2026-10-08, exit 0

```
=== LIST_QUEUES (name, depth, dlq) ===
  ["broadcast", 0, false]
  ["bus-health-probe", 0, false]
  ["inbox_esther", 0, false]
  ["inbox_fleet", 0, false]
  ["inbox_gisu", 0, false]
  ["inbox_health_check", 2, false]
  ["inbox_joseph", 0, false]
  ["inbox_kustos", 0, false]
  ["inbox_moses", 0, false]
  ["inbox_orchestrator", 2, false]
  ["inbox_orchestrator_dlq", 0, true]
  ["inbox_titus", 0, false]
  ["out_esther", 0, false]
=== ASSERTIONS ===
  PASS: inbox_titus depth=0
  PASS: broadcast depth=0
  PASS: no non-empty DLQ queues
=== PEEK inbox_titus ===
  null (empty)
=== ACL ISOLATION (peer queue) ===
  PASS: inbox_orchestrator rejected with 403
RESULT: CLEAN
```

## Interpretation

- This agent's `inbox_titus` and `broadcast` queues: **empty**.
- No non-empty DLQ queues exist.
- The two non-zero queues (`inbox_orchestrator` depth 2, `inbox_health_check`
  depth 2) are **other agents' lanes**; this agent's read of
  `inbox_orchestrator` correctly returns HTTP 403 (ACL boundary verified),
  so they are out of scope for this cron and are not processed here.
- Decision: nothing actionable in this agent's scope → `[SILENT]`.