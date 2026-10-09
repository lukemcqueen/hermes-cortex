# Agent Bus poll evidence — inbox_titus
# Cron job: cortex-bus-automation (absorbed into cortex-bus)
# Queue: inbox_titus (Titus)
# Date: 2026-10-09 22:21 KST
# Re-runnable via ./poll-bus-inbox_titus.sh (reads credentials from hermes-inbox.conf)

Captured run output (2026-10-09 22:21 KST):

== GET <CORTEX_BUS_URL>/api/pgmq/peek/inbox_titus ==
{"queue":"inbox_titus","messages":[],"count":0}
== HTTP status (curl -w suffix) ==
HTTP:200

Interpretation: HTTP 200 with count=0 — the queue read succeeded (HTTP-layer
probe, not a swallowed 403). No pending messages this cycle.