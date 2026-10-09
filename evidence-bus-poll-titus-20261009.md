# Agent Bus poll evidence — inbox_titus
# Cron job: cortex-bus-automation (absorbed into cortex-bus)
# Queue: inbox_titus (Titus)
# Date: 2026-10-09 (UTC 13:29:46)
# Re-runnable: ./poll-bus-inbox_titus.sh (reads credentials from hermes-inbox.conf)
# Hardened script fails on any non-2xx (curl --fail-with-body -sS, set -euo pipefail).

Final hardened run output:

RUN 2026-10-09 13:29:46 UTC
== GET <CORTEX_BUS_URL>/api/pgmq/peek/inbox_titus ==
{"queue":"inbox_titus","messages":[],"count":0}
== HTTP assertion ==
queue_read_ok (count=0, non-2xx would have exited nonzero above)
EXIT:0

Interpretation: HTTP 200 (implicit — non-2xx would have aborted via --fail-with-body)
with count=0. Queue read succeeded; no pending messages this cycle.