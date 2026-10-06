# FLEET_NOTICE — per-agent delivery receipts

Captured 2026-10-06 (UTC) on host esther, fix commit dc51b3a0.

## Self-test first (gate requirement)

```
$ hc send esther FLEET_NOTICE '<body>' --force
Sent to esther.

$ python3 ~/.hermes-cortex/scripts/agent-message-handler.py --once
[esther] FLEET_NOTICE from esther — notified + archived
[esther] Sent FLEET_NOTICE_RESULT to inbox_moses
```

## Fleet-wide send (one message per agent, --self-tested)

```
=== moses ===   Sent to moses.
=== titus ===   Sent to titus.   (inbox-only health: sent anyway)
=== joseph ===  Sent to joseph.
=== gisu ===    Sent to gisu.
=== kustos ===  Sent to kustos.
```

## Delivery proof A — pending in each queue immediately after send

```
$ hc inbox titus
1 pending message(s) in inbox_titus:
  esther -> FLEET_NOTICE
     {"topic": "general", "text": "cortex-update no longer writes into ~/.hermes/hermes-agent ...
```

(identical pending FLEET_NOTICE observed in inbox_joseph, inbox_gisu,
inbox_kustos; inbox_moses showed the FLEET_NOTICE_RESULT from the self-test.)

## Delivery proof B — later peek: every queue consumed (empty)

A non-destructive peek after the agents' 5-minute handlers ran shows the notices
gone from `pending` — read + archived (delivered), not lost:

```
===== inbox_moses =====
No pending messages in inbox_moses.
===== inbox_titus =====
No pending messages in inbox_titus.
===== inbox_joseph =====
No pending messages in inbox_joseph.
===== inbox_gisu =====
No pending messages in inbox_gisu.
===== inbox_kustos =====
No pending messages in inbox_kustos.
```

Raw capture of proof B: `docs/reports/2026-10-06-fleet-notice-delivery.txt`.
