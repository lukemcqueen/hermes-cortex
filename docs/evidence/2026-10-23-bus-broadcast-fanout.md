# Broadcaster fan-out fix — evidence (2026-10-23)

## Defect (escalated by esther 2026-10-23 05:51Z, msg archived to inbox_orchestrator 05:55Z)

`cortex-bus-mcp.py` mapped the MCP `inbox_send` recipient `"all"` to the
`broadcast` queue, but **no consumer reads the `broadcast` queue** — both
`agent-message-handler.py` and `cortex-bus-processor.py` poll only `inbox_<agent>`.

Every send-to-"all" (FLEET_NOTICE, post-commit notify) was silently dropped:

- The Excellence FLEET_NOTICE (commit 918e292e) sat pending 29h on `broadcast`,
  delivered to nobody. `msg_id b250f6f3-5f30-49ea-9fa1-b1d584f2c694`,
  `from moses`, enqueued 2026-10-22 06:14:03Z, `retry_count=0`, still `pending`
  at inspection time (2026-10-23 11:30Z).
- Whole-table scan of `bus.messages` for `FLEET_NOTICE`/`Excellence` returned
  that row only — no per-agent copies existed.
- `bus.archives` has exactly one `broadcast` row ever (2026-09-25,
  `moses-cron-bus-check` — a doctor round-trip).

## Fix

`_inbox_send` with recipient `"all"` now fans out **one message per agent** to
`inbox_<agent>` (the documented delivery in `docs/fleet-update-protocol.md`
line 58), from the v4 agent registry. Reports a partial/full count on the result.
Per-agent recipients still route to exactly one inbox (unchanged).

## Tests

`tests/test_bus_mcp_broadcast_fanout.py` (3 tests):

```
test_inbox_send_all_fans_out_one_per_agent            — RED → GREEN
test_inbox_send_all_reports_partial_failures          — RED → GREEN
test_inbox_send_single_recipient_still_direct         — passes (no regression)
```

Run capture: `tests/run-tests.sh tests/test_bus_mcp_broadcast_fanout.py -q`
→ `3 passed in 6.55s` (rc=0).

Adjacent suites `test_bus_task_subject.py`, `test_apply_mcp_tool_watch_fix.py`:
11 passed. `test_bus_task_context.py` had 2 pre-existing errors unrelated to
this change (its fixture does a bare `git commit` in a temp repo, which the
cortex hooks refuse — a test-harness / hook interaction, not this change).

## Adversarial gate

`adversarial-verify.py --file mcp-servers/cortex-bus-mcp.py --level A4 --gate`
→ `GATE_PASSED — no critical/high findings` (rc=0).
2 advisory findings, both pre-existing and outside the fan-out diff:
- `ADV-...-002` low: subprocess.run at line 204 (untouched);
- `ADV-...-001` medium: empty `except` blocks elsewhere in the file.
See `bus-mcp-fanout-adversarial-2026-10-23.json` (this dir, committed artifact).

## Who consumes the target now

Moses is admin (`bus.permissions` row for moses has `is_admin=true`,
`can_write` on all `inbox_*` queues). Each `inbox_<agent>` is polled by that
agent's 5-min `agent-message-handler.py` — the orchestrator's own handler also
polls `inbox_orchestrator` (the shared mirror), so the duplicate fan-out copy
Esther receives via the US-002 mirror is consumed by her handler.