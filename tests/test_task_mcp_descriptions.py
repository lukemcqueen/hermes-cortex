#!/usr/bin/env python3
"""The task tools must say what ACTUALLY gates verification, and what to do about it.

Raised 2026-10-21 (operator, from the Pi agent): task_verify described itself only as
"ORCHESTRATOR-ONLY: verify a review slice" and task_report as "awaiting orchestrator verify". Both
invite the inference that moses/esther will pick the slice up — and NOTHING does. Verified
mechanism, not assumed: tasks.verify_slice (ops/services/tasks/schema/v009__task-model-v3.sql) is
the only review→completed path, it is enforced in the DB (SECURITY DEFINER, moses/esther allowlist
inside the function, no EXECUTE grant for other profiles), and the fleet cron inventory
(docs/cron-schedules.md) lists no slice-verification job. An agent that believes someone will act
stops working on a slice that then sits in review forever, so the wording an agent READS under a
refusal is the fix.

WHY A TEXT GUARD: the deliverable here IS the wording. The mechanism the wording cites is proven
in the schema and the cron inventory (named above); what this pins is that the description cannot
quietly regress to the passive phrasing.
"""
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "mcp-servers" / "task-mcp.py"
TEXT = SRC.read_text()

REQUIRED = {
    "task_verify names the DB enforcement": "SECURITY DEFINER",
    "task_verify names the refusal a worker actually sees":
        "permission denied for function verify_slice",
    "task_verify states nothing runs it automatically": "NOTHING RUNS THIS AUTOMATICALLY",
    "task_verify tells the agent what to DO instead": "hand the slice id",
    "task_report says review is not completion": "does NOT reach completed",
    "task_report tells the agent to follow up, not wait": "rather than wait",
}
FORBIDDEN = {
    "the passive claim that an orchestrator will verify": "awaiting orchestrator verify",
    "the bare label with no enforcement and no next step":
        "ORCHESTRATOR-ONLY: verify a review slice",
}

if not SRC.is_file():
    print(f"RESULT: FAILED — {SRC} not found")
    raise SystemExit(1)

fails = 0
for why, needle in REQUIRED.items():
    if needle in TEXT:
        print(f"  ✓ {why}")
    else:
        print(f"  ✗ {why} — missing {needle!r}")
        fails += 1
for why, needle in FORBIDDEN.items():
    if needle in TEXT:
        print(f"  ✗ {why} — still present: {needle!r}")
        fails += 1
    else:
        print(f"  ✓ {why} — gone")

print(f"RESULT: {'ALL PASS' if not fails else f'{fails} FAILED'}")
raise SystemExit(1 if fails else 0)
