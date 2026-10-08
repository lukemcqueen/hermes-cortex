# Bus Health-Check Time-Window Verification — Evidence (Titus, 2026-10-08)

Read-only, non-consuming `bus_list_queues` sampled every 5s for 75s
(16 samples, t=0s..75s inclusive) on 2026-10-08. Fields `depth/processing`,
verbatim from the live run:

```
t=  0s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
t=  5s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
t= 10s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
t= 15s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
t= 20s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
t= 25s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
t= 30s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
t= 35s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
t= 40s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
t= 45s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
t= 50s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
t= 55s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
t= 60s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
t= 65s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
t= 70s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
t= 75s  inbox_health_check=d2p0  inbox_orchestrator=d8p0  inbox_titus=d0p0  inbox_orchestrator_dlq=d0p0
```

## Result

- `inbox_health_check`: **processing=0 throughout the 75s window** — this
  agent never observes a stuck in-flight item within the window. (A single
  earlier capture in `cron-bus-inbox-check-2026-10-08.raw.txt` showed
  `processing=1`; the window here shows a sustained `processing=0` over 75s,
  consistent with a transient in-flight item drained by the recover-timeouts
  cron rather than a permanently stuck workflow.)
- `inbox_titus` (this agent's inbox): `d0p0` throughout — **empty**.
- `inbox_orchestrator_dlq` (the only DLQ): `d0p0` throughout — **empty**.
- `inbox_orchestrator` depth 8 / processing 0 is the **orchestrator's own
  inbox** — this agent's read returns HTTP 403 (ACL-isolated), out of scope for
  a non-orch cron.

## Conclusion

No pending, urgent, critical, or DLQ items in this agent's scope; no stuck
workflow observable to this agent over the window. Cron decision: `[SILENT]`.