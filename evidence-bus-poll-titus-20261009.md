# Agent Bus poll evidence — inbox_titus
# Cron job: cortex-bus-automation (absorbed into cortex-bus)
# Queue: inbox_titus (Titus)
# Date: 2026-10-09
# Re-runnable: ./poll-bus-inbox_titus.sh (reads credentials from hermes-inbox.conf)
# Script asserts JSON payload shape (count + messages list), NOT count=0; exits 0
# on any successful 2xx authenticated read. Fails on connection error, non-2xx,
# missing/unreadable config, missing URL/AUTH, or malformed JSON payload.

Captured script output (2026-10-09 13:37 UTC):

RUN 2026-10-09 13:37:28 UTC
== GET <CORTEX_BUS_URL>/api/pgmq/peek/inbox_titus ==
{"queue":"inbox_titus","messages":[],"count":0}
queue_read_ok count=0 (any 2xx read is success)
EXIT:0

Interpretation: authenticated read of inbox_titus succeeded (2xx), count=0 —
no pending messages this cycle.