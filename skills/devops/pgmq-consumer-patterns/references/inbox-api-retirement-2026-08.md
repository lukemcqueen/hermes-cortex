# Inbox→PGMQ Retirement Sweep — 2026-08-04

Full diagnostic path for the "Titus falsely unreachable" incident, which exposed
a stale-skill proposal and a live consumer bug sharing one root cause: the file
inbox API was retired but consumers/docs were never swept.

## Incident Chain

1. Titus (worker) sent a bus PROPOSAL: `agent-health-monitoring` skill documents
   the retired Moses inbox API (`MOSES_INBOX_URL`/`MOSES_INBOX_AUTH` in
   `~/.hermes/moses-inbox.conf`, `api/inbox?topic=health`, anchor-keep DELETE).
2. Verification found the claim TRUE **and** a live bug: `orch-health-report.py`
   `_fetch_inbox_vector()` still called `GET /api/inbox` — which returns 404 on
   the PGMQ bus server (route table has only `/api/pgmq/*`). Result: Titus (the
   only `health_method: inbox` agent) showed 🔴 in every hourly report despite
   `health-vector-push.sh` exiting 0; `last-seen.json` stale since Jul 15.
3. Second design gap: `orch-clean-health-queue.py` drained `inbox_health_check`
   every 10m and archived pings but persisted nothing — so even a fixed report
   reading the live queue would usually find it empty (hourly vs 10m race).

## Root-Cause Facts (verified, with evidence)

| Claim | Evidence |
|-------|----------|
| `api/inbox` retired | `grep "@app.post\|@app.get" ops/services/agent-bus/server.py` — only `/api/pgmq/*`, `/api/bus/dashboard`, `/health`, `/.well-known/agent-card.json` |
| Push moved to PGMQ | `ops/scripts/health/health-vector-push.sh` reads `CORTEX_BUS_URL`+`CORTEX_BASIC_AUTH` from `~/.hermes-cortex/cortex-bus.conf`, POSTs `/api/pgmq/send` → `inbox_health_check` |
| Report still on old API | `orch-health-report.py` `_fetch_inbox_vector` → `_inbox_request("api/inbox?...")` |
| `orch-team-health.py` gone | `git log --oneline --diff-filter=D -- "**/orch-team-health.py"` → `69e3cf8e` "Remove orch-team-health cron… superseded by fleet-status-watchdog" |
| Migration commit | `0f01556d` "refactor: migrate all scripts/docs from CORTEX_INBOX_URL/AUTH to CORTEX_BUS_FALLBACK_URL/AUTH" |

## The Fix (commit 87df0c73)

1. **`orch-clean-health-queue.py`** — drainer persists: while archiving each
   ping, write `{"<agent>": {"vector": [...], "ts": "<iso>"}}` to
   `~/.hermes-cortex/state/inbox-health-state.json` and update
   `last-seen.json`. Best-effort (OSError swallowed) — archiving already happened.
2. **`orch-health-report.py`** — consumer reads state file first; fallback is a
   live `bus_read("inbox_health_check", vt=60)` peek scanning up to 20 pings,
   matching on `body.from`. Deleted dead `_load_inbox_config`/`_inbox_request`.
3. **Skill docs** — `agent-health-monitoring` SKILL.md + 5 references rewritten:
   architecture diagram, `orch-team-health.py`→`orch-health-report.py`,
   anchor-keep→drain-and-persist, `moses-inbox.conf`→`cortex-bus.conf`,
   pitfall rows pruned/added (silent-404 consumer, drained-before-read).
4. **Onboarding/ops docs** — `api/inbox?limit=3` curl examples → `/api/pgmq/queues` / `/api/pgmq/depth/...`.

## Verification Recipe (reproduce the cron env!)

```bash
# Seed a ping exactly like the producer
PYTHONPATH=~/hermes-cortex/ops/scripts python3 -c "
from lib.cortex_bus import bus_send
import json, time
bus_send('inbox_health_check', {'from': 'titus', 'subject': 'health',
    'body': json.dumps({'v':[1]*9,'h':'t','t':int(time.time())})})"

# Run the drainer AS CRON DOES (direct python3 from another cwd fails hermes_paths import)
CORTEX_REPO=~/hermes-cortex PYTHONPATH=~/hermes-cortex/ops/scripts \
  python3 ~/hermes-cortex/ops/scripts/orch-bus/orch-clean-health-queue.py

# Confirm persistence
cat ~/.hermes-cortex/state/inbox-health-state.json

# Confirm the consumer now reports the agent green
python3 ~/hermes-cortex/ops/scripts/agent/orch-health-report.py
```

## Sweep Checklist (use after ANY transport migration)

- [ ] Route table of the new server: list all `@app.get/@app.post` — note the retired paths
- [ ] `grep -rn "api/inbox\|api/delete\|MOSES_INBOX_URL\|moses-inbox.conf" ops/ scripts/ skills/ docs/`
- [ ] `grep -rn "<removed-script-name>" skills/ docs/` (docs reference deleted scripts for months)
- [ ] Every consumer of the old transport: does it 404 silently? (returns None → false alarm)
- [ ] Every drainer: does a *second* consumer need its data? If yes → persist state
- [ ] Deploy + verify the DEPLOYED copy (SOURCE header ≠ repo raw MD5 — strip header to compare)
