# Health Queue Backlog — Diagnosis & Remediation

## When to Use This Reference

When health pings accumulate in the `inbox_health_check` PGMQ queue (or the
persisted state file goes stale), or an inbox-method agent (typically Titus)
shows 🔴 unreachable in the hourly report despite healthy pushes.

## Detection

**Symptom 1 — queue depth grows:** `inbox_watch`/`inbox_read` returns a massive
result (2MB+ or hundreds of messages), all with:
- `from: titus` (or another health_method=inbox agent)
- `subject: health`
- `body: {"v": [1,1,1,1,1,1,1,1,1], "h": "t", "t": <epoch>}`

**Symptom 2 — state file stale:** `~/.hermes-cortex/state/inbox-health-state.json`
is missing or holds an old timestamp, and the hourly report shows 🔴 for an
inbox agent whose push script exits 0.

**Normal rate:** 1 health pulse every 10 minutes = ~6/hour = ~144/day.
Accumulation means the drain consumer is not running.

## Architecture of the Health Push Pipeline (current)

```
[Agent Side]
health-vector-push.sh (every 10 min via launchd/systemd/cron)
  └─ reads CORTEX_BUS_URL + CORTEX_BASIC_AUTH from ~/.hermes-cortex/cortex-bus.conf
      └─ POST /api/pgmq/send → queue inbox_health_check
          └─ message: {"from": "titus", "subject": "health", "body": "{...}"}

[Orchestrator Side (Moses)]
orch-clean-health-queue.py (no_agent cron, every 10 min)
  └─ bus_read(inbox_health_check) → bus_archive per ping
      └─ persists latest vector per agent → ~/.hermes-cortex/state/inbox-health-state.json
      └─ updates last-seen → ~/.hermes-cortex/state/last-seen.json

orch-health-report.py (hourly) / dashboard
  └─ reads inbox-health-state.json for inbox-method agents
```

> The retired file-inbox API (`api/inbox`, `api/delete`, anchor-keep DELETE
> pattern, `orch-team-health.py`) is **gone** — see the agent-bus skill for the
> current PGMQ architecture.

## Diagnosis Checklist

### 1. Is the drain cron running?

```bash
hermes cron list | grep orch-clean-health-queue
ls -la ~/.hermes/cron/output/ | grep clean-health-queue | tail -3
```

If the cron hasn't run recently (stale output > 10 min) or shows errors,
the drain is not pruning and the state file goes stale.

### 2. What is the queue depth?

```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT state, COUNT(*) FROM bus.messages WHERE queue_name='inbox_health_check' GROUP BY state;\"
"
```

A healthy queue hovers near 0-2 pending (drained every 10 min). Hundreds of
pending = drain stopped.

### 3. Is the state file fresh?

```bash
cat ~/.hermes-cortex/state/inbox-health-state.json   # per-agent latest vector + ts
cat ~/.hermes-cortex/state/last-seen.json            # laptop grace timestamps
```

If `ts` is older than ~15 min, the drain cron is not seeing new pings.

### 4. Are pings going to the right queue?

Check the push script target. `health-vector-push.sh` must send to queue
`inbox_health_check` with `subject: health` — if it targets a different queue
or topic, the orchestrator never sees them.

### 5. Is `_fetch_inbox_vector` reading the right source?

The agent must be in `agent-registry.json` with `health_method: inbox`, and
`orch-health-report.py` must read `inbox-health-state.json` (or `bus_read`)
— NOT the retired `api/inbox` (404 on the PGMQ bus, fixed 2026-08-04).

### 6. Is health-vector-push.sh running too frequently?

Check the launchd/cron schedule. If it's running more frequently than every
10 minutes, a 10-min drain cycle can't keep up (drain is capped at 50/tick).

## Immediate Remediation

When pings have accumulated to 100+ messages and are all-green:

1. **Drain the backlog** — the drain cron archives up to 50/tick; a manual
   run clears the rest:
   ```bash
   CORTEX_REPO=~/hermes-cortex PYTHONPATH=~/hermes-cortex/ops/scripts \
     python3 ~/hermes-cortex/ops/scripts/orch-bus/orch-clean-health-queue.py
   ```
   (It persists the latest vector per agent as it drains.)

2. **Fix the root cause** — pick from diagnosis above:
   - Restart `orch-clean-health-queue` cron if stopped
   - Fix bus auth (`CORTEX_BASIC_AUTH`/`CORTEX_BUS_TOKEN` in `cortex-bus.conf`) if reads 401
   - Fix agent-registry.json `health_method` if missing
   - Correct push script queue/topic if wrong

3. **Verify fix**: A new health pulse should arrive within 10 min. The next
   drain tick should archive it and refresh `inbox-health-state.json`; the
   next hourly report should show the agent ✅.

## Prevention

- The drain cron should log a warning when it finds >2 pings per tick for the
  same agent (indicates the push schedule outpaced the drain).
- The `orch-bus-confirmation-poller.py report` already flags DLQ/depth issues
  on `inbox_health_check` — keep its alert cron enabled.
- If the state file is missing entirely, the report falls back to a live
  `bus_read` peek, so a fresh ping still shows — but persistence is the
  reliable path.

## Pitfalls

- **Drain stopped silently.** The drain cron prints nothing when healthy
  (silent-when-clean) — a stopped cron is invisible until the queue backlogs
  or the report goes 🔴.
- **Bus auth 401.** A wrong `CORTEX_BASIC_AUTH`/token makes `bus_read` return
  None silently → queue grows, state file never updates. Verify against the
  LOCAL bus (`127.0.0.1:8903`), not the external nginx port.
- **Renamed agent.** If the agent changes names but pings still carry the old
  name, the `from` filter won't match.
