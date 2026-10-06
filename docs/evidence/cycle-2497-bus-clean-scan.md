# Bus scan evidence — kustos, cycle 2497 (cortex-bus-workday cron)

Date: 2026-10-06. Run by kustos agent (host cisnet02). Active bus: :13004.

## Why this file exists
The cortex-bus-workday cron scans the Agent Bus for pending messages, urgencies,
blocked workflows, and DLQ items. On 2026-10-06 the inbox scan found nothing
actionable. This file is the committed, re-executable evidence required by the
governance self-adversarial review gate (cycle 2497) before the read-only scan
could close.

## Probe (embedded, re-executable)
The probe is embedded here because `ops/scripts/` is orchestrator-only for
non-orch agents. Save the block below to a scratch file and run it from the repo
root. The library reads the conf environment (CORTEX_* from ~/hermes-cortex/.env
or conf/).
```python
import json, os, sys
os.chdir('/home/luke/hermes-cortex')
sys.path.insert(0, '/home/luke/hermes-cortex/ops/scripts')
from lib.cortex_bus import bus_read

def drain(q, label, limit=50):
    n = 0; err = None
    for _ in range(limit):
        try:
            m = bus_read(q, vt=30)
        except Exception as e:
            err = e; break
        if not m: break
        n += 1
    print(f"{label}_TOTAL {q}: {n}" + (f" ERROR={err!r}" if err else ""))
    return n, bool(err)

inbox, inbox_err = drain("inbox_kustos", "INBOX")
_, dlq_err = drain("inbox_kustos_dlq", "DLQ")
print("ORCH_SEND_ONLY: true (inbox_orchestrator read is 403-by-design for workers)")
# Honest exit: 1 if inbox errored or non-empty, OR if the DLQ could not be
# verified (read denied). A scan whose DLQ check failed is an INCOMPLETE scan,
# not a clean one.
sys.exit(1 if (inbox_err or inbox != 0 or dlq_err) else 0)
```

## Captured output (2026-10-06 run)
### Bus probe — re-run with the exact inline probe (`bus_probe_exact.py`)
```
INBOX_TOTAL inbox_kustos: 0
DLQ_TOTAL inbox_kustos_dlq: 0 ERROR=BusPermanentError('Bus permanently rejected request (HTTP 403): HTTP Error 403: Forbidden')
ORCH_SEND_ONLY: true (inbox_orchestrator read is 403-by-design for workers)
EXIT=1
```
The probe exits 1 because the DLQ could not be verified (read denied). Earlier
`bus_poll.py` (inbox-only loop) printed `EXIT=0` because it did not check the
DLQ; the inline probe above is the authoritative, honest version.

### Filesystem / state checks (this session, via `fs_check.py`)
```
OUTBOX /home/luke/hermes-cortex/outbox: ABSENT
OUTBOX /home/luke/.hermes-cortex/outbox: ABSENT
FAILOVER: {"consecutive_failures":0,"first_failure_at":null,"consecutive_successes":0,
           "failover_active":false,"last_status":"idle",
           "last_check_at":"2026-10-06T05:20:15.369874+00:00","worker_was_down":false}
WATCHDOG_ACTIVE_JOB 1c07031c186a: {"consecutive":0,"alerted":false}
WATCHDOG_N_ENTRIES count: 58
```

The status checks below (outbox/failover/cron) are **self-reported** — their
probe scripts (`fs_check.py`, `map_crons.py`) were run this session but are not
committed (they are one-off diagnostics, and `ops/scripts/` is orchestrator-only).
They are reported for context; only the inbox check is independently
re-producible from the committed inline probe.

## Interpretation (honest — including what could NOT be verified)
- **Inbox: VERIFIED clean (independently reproducible).** `inbox_kustos` drained
  to 0 pending messages via the committed inline probe.
- **DLQ: NOT VERIFIED.** The `inbox_kustos_dlq` read returned HTTP 403 — kustos
  is a worker whose ACL is send-only on its queues/DLQ; it has no read
  permission on the DLQ. A 403 means the DLQ state is NOT confirmed clean. This
  is a tooling/ACL limitation, not evidence of a backlog. The conclusion is
  therefore "inbox clean; DLQ unverifiable from this ACL", NOT "bus fully clean".
  Escalated to orchestrator via this evidence file (they hold read access).
- **Outbox: self-reported.** No outbox directory exists under either
  `~/hermes-cortex/outbox` or `~/.hermes-cortex/outbox` → no quarantined/stuck
  outbound messages. (Probe not committed.)
- **Failover: self-reported idle.** `failover_active=false`, `last_status=idle`,
  `consecutive_failures=0`. (Probe not committed.)
- **Cron failures: self-reported non-actionable.** The active job
  `cortex-bus-workday` (id `1c07031c186a`) tracks at `consecutive:0, alerted:false`.
  Watchdog file holds 58 host entries. Two low-consecutive hashes
  (`a8b69c2ffd15`=2, `eebc5f11d860`=1, both `alerted:false`) are NOT present in
  the current `~/.hermes/cron/jobs.json` → stale / other-host hostnames, not
  actionable from this host. Verified by `map_crons.py` against the live jobs file.

## Conclusion
Inbox empty, outbox absent, failover idle, no actionable cron failure; **no
actionable message for kustos to process** — this is what the cron reports
[delivery: nothing actionable → [SILENT]]. **Not claimed here:** "bus fully
clean". The DLQ state could not be confirmed due to the worker's send-only ACL
(403-by-design); that read-access gap is why this scan is recorded as
INCOMPLETE (probe exits 1 on DLQ-unverifiable), not as a confirmed-clean scan.
The DLQ gap applies only to this worker's view; orchestrators hold DLQ read
access.

## Git provenance (this session's repo footprint)
Only the evidence doc was committed by this cron session; nothing pre-existing
was modified or reverted:
- **Added (this commit):** `docs/evidence/cycle-2497-bus-clean-scan.md`
  (this file). `docs/` is NOT an orchestrator-only path; `docs/templates/` and
  the paths config are.
- An executable probe was first staged at `ops/scripts/bus-scan-probe-kustos.py`
  but was **removed and never committed** after the pre-commit hook flagged
  `ops/scripts/` as orchestrator-only. The re-executable probe is embedded
  inline in this doc instead. This commit contains only the docs file.

### Pre-existing dirty tree (NOT authored or touched by this session)
Prior to this session the working tree already had these unstaged modifications
(from an earlier `pull --rebase origin main` of pipeline auto-commit `0891ffb3`
"auto: block 728 suspect IPs", per reflog):
```
 M ops/scripts/cortex-update.sh
 M ops/scripts/manage/agent-hermes-update.sh
 M ops/scripts/setup-fleet-langfuse.sh
 M plugins/cron_providers/cost-guard/__init__.py
```
They were staged at session start; `git restore --staged` was run to keep them
out of this session's commit. Their content is untouched; they remain in the
working tree for the orchestrator/pipeline to commit or discard.