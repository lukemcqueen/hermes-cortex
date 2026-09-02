---
name: cortex-bus
version: 1.2.0
category: devops
description: "Agent Bus (PGMQ) operations — queue inspection, DLQ management, message recovery, auth, and health diagnostics. Covers the Postgres-backed message queue that replaces the legacy file inbox."
platforms: [linux]
author: Hermes Cortex
metadata:
  hermes:
    tags: [bus, pgmq, dlq, messaging, queue, postgres, recovery]
    related_skills: [system-remediation, hermes-cortex-deployment]
---

# Agent Bus — PGMQ Operations

## Overview

The Agent Bus is a Postgres-native message queue (`lib/pgmq` implementation with `SKIP LOCKED`) running on port `:8903`, proxied through nginx. All inter-agent communication flows through it. It replaces the old file-based agent inbox.

> **📐 Architecture reference:** See [`docs/reference/cortex-bus-config.md`](../../docs/reference/cortex-bus-config.md) for the full architecture — fleet topology, auth model, ACL/permissions, message consumption patterns, and forwarder design. This skill covers operational diagnostics only.

> **⚠️ Postgres access (post-2026-08-05 migration):** the `legacy Postgres`
> container was replaced by **`mycortex-postgres`** (role/db **`mycortex`**,
> port still `:15432`). All psql examples below use the new container/role:
> `sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex ..."`.
> The old `mycortex` role does NOT exist in the new container — using it fails
> with `FATAL: role "mycortex" does not exist`.

Key architectural facts:
- **Bus server** processes at `~/hermes-cortex/core/cortex_bus/server.py` (module `cortex_bus.server:app`, service `cortex-bus.service`)
- **Queue module** at `~/hermes-cortex/core/cortex_bus/queue.py`
- **Postgres schema** `bus.*` in the shared mycortex database (`:15432`)
- **MCP tools** `mcp__cortex_bus__*` route through the bus via HTTP
- **Health check**: `curl http://127.0.0.1:8903/health` returns 200
- **Bearer token auth**: token from `CORTEX_BUS_TOKEN` in `.env`

## When to Use

- Diagnosing message delivery failures between agents
- Inspecting queue depth or DLQ buildup
- Recovering stuck `processing` messages
- Fixing bus auth or permission issues
- Investigating why an agent isn't receiving messages

## Message Contract (strict input formatting)

Every `/api/pgmq/send` is validated at ingestion (2026-09-02, anti-poisoning/anti-spam at fleet scale). Violations → **400 + reason**; over quota → **429**.

| Field | Rule |
|-------|------|
| `from` | Required, lowercase agent name, **must equal the authenticated sender** (spoofing rejected) |
| `subject` | Required, `^[A-Z][A-Z0-9_]{0,63}$` (`EXEC`, `PING`, `DOCTOR_TEST`, …) |
| `body` | Required, object or string |
| `to` / `correlation_id` / `timestamp` / `type` / `priority` | Optional; `priority` int 0-100 |
| Unknown keys | **Rejected** — no field smuggling |
| Size | 64 KiB max/message |
| Rate | 600 sends/hr/agent (`CORTEX_BUS_RATE_LIMIT_PER_HOUR`), sliding window |

`workflow_step_result` queue uses its own schema (`workflow_id` `step_id` `status` `result` `error`) — agents post step results without an envelope.

Implementation: `core/cortex_bus/validate.py` + `core/cortex_bus/ratelimit.py`, tests in `tests/test_bus_validate.py`. Sending messages: use `bus_send()` / the MCP inbox tools — they build conforming envelopes.

## Diagnosing Bus State

### 1. Queue Overview

```bash
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c \"
SELECT queue_name, state, COUNT(*) as count
FROM bus.messages
GROUP BY queue_name, state
ORDER BY queue_name, state;
\""
```

Shows every queue with its message counts broken down by state:

| State | Meaning |
|-------|---------|
| `pending` | Ready for dequeue — normal state |
| `processing` | Currently dequeued, within visibility timeout |
| `archived` | Successfully processed (or auto-archived) |

### 2. DLQ Inspection (Dead Letter Queue)

Messages that exceeded `max_retries` (default 3) move to `{queue}_dlq`. DLQ messages older than 6 hours are auto-archived by `bus.recover_timeouts()`.

```bash
# DLQ depth by queue
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c \"
SELECT queue_name, state, COUNT(*) as count,
    MIN(enqueued_at)::timestamptz(0) as oldest,
    MAX(enqueued_at)::timestamptz(0) as newest
FROM bus.messages
WHERE queue_name LIKE '%dlq%'
GROUP BY queue_name, state
ORDER BY queue_name, state;
\""

# DLQ message content — who sent it, what about, how many retries
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c \"
SELECT 
    queue_name,
    COALESCE(body->>'from', '(empty)') as sender,
    body->>'subject' as subject,
    body->>'topic' as topic,
    retry_count,
    error,
    enqueued_at::timestamptz(0)
FROM bus.messages
WHERE state = 'pending' AND queue_name LIKE '%dlq%'
ORDER BY queue_name, enqueued_at DESC
LIMIT 50;
\""
```

### 3. Check Queue Schema Integrity

```bash
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c \"
SELECT name, is_dlq, parent_queue, max_retries FROM bus.queues ORDER BY name;
\""
```

Every queue ending in `_dlq` MUST have `is_dlq = true`. If false, the auto-archive and chain-deletion break silently.

### 4. Run Recovery

```bash
# Returns count of messages recovered/archived
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c \"
SELECT bus.recover_timeouts();
\""
```

The `recover_timeouts()` function does three things:
1. **Recovers** processing→pending for messages below `max_retries`
2. **Moves** over-retry processing messages to DLQ (or deletes if already in a DLQ)
3. **Auto-archives** DLQ messages older than 6 hours

### 5. Interpreting Recovery Counts

The `orch-bus-recover-timeouts` cron (every 5m) calls `bus.recover_timeouts()` and reports results. The **silent threshold is 50** — below that, no notification is sent (routine timeouts are normal).

| Recovery count | Meaning |
|----------------|---------|
| 0–5 | Normal — routine visibility timeouts |
| 5–50 | Mild backlog — catching up, no action needed |
| 50+ | Moderate+ backlog — worth investigating |

### 6. Normal DLQ Baselines

DLQ messages < 6 hours old are normal — they auto-archive on each `recover_timeouts()` tick.

| DLQ depth | State |
|-----------|-------|
| < 50 | Normal — transient backlog |
| 50–200 | Moderate — check sender breakdown |
| 200+ | Elevated — investigate with DLQ content query (section 2) |

If messages older than 6 hours are present, `is_dlq` may be broken (see Common Issues below).

The threshold (50) is set in `ops/scripts/orch-bus/orch-bus-recover-timeouts.sh` as `RECOVER_THRESHOLD=50`.

### 7. Health Report Monitoring (`orch-bus-confirmation-poller.py report`)

The `orch-bus-confirmation-alert` cron (every 60m) runs `orch-bus-confirmation-poller.py report` producing a combined bus health report covering message tracker status + queue depths + DLQ health.

**Report behaviour:**
- **Silent when healthy** — no output if no DLQ backlog, no overdue confirmations, no pending messages. Zero stdout = zero notification.
- **Alerts on DLQ backlog** — checks both `depth` (pending) AND `processing` state in DLQ queues. Messages stuck in processing count as a backlog.
- **Reports on overdue confirmations** — tracked messages past their confirmation deadline.

**Common gotcha — processing messages in DLQ hidden from alerts:**
The DLQ alert code in `cmd_report()` at `ops/scripts/orch-bus/orch-bus-confirmation-poller.py` initially only checked `depth > 0` for DLQ queues. Messages in `processing` state were invisible. The fix adds `or processing > 0` to both the marker and `dlq_issues` detection.

```python
# Before (missed processing messages):
marker = " ⚠️ DLQ" if is_dlq and depth > 0 else ""
if depth > 0: dlq_issues.append(name)

# After (checks both):
marker = " ⚠️ DLQ" if is_dlq and (depth > 0 or processing > 0) else ""
if depth > 0 or processing > 0: dlq_issues.append(name)
```

**Silent-when-clean pattern** — the report collects all data first, then only prints if there's something to report:

```python
# At the end of data collection:
if not overdue and not dlq_issues and not pending:
    return  # completely silent
```

### 8. Cron Alert Design: Silent-When-Clean

A general principle for no_agent cron scripts that produce health/status reports:

- **No output = no notification.** The user should only hear from a cron when there's something to act on.
- **Collect data first, print only if there's a signal.** Build the entire report into variables (`queue_lines`, `dlq_issues`), then check whether anything needs attention before printing.
- **Silence is the default, not a special mode.** The healthy state should produce zero stdout. Don't print "✅ All clean" — that's noise.
- **Thresholds belong in the script, not hardcoded in docs.** The `RECOVER_THRESHOLD` variable in the script defines what's actionable. Docs reference the variable name, not the value.

This pattern applies to: health reports, watchdog crons, depth monitors, alert crons, and any periodically-running agent script that checks system state.

### 9. Stuck Pending Messages at Max Retries

The `recover_timeouts()` function only moves messages from `processing` → pending/DLQ. Messages that were never dequeued while it ran remain in `pending` with their retry count unchanged. This means **messages can sit in `pending` with `retry_count = max_retries` without ever being promoted to the DLQ**.

These are truly stuck: the message was dequeued up to max_retries times, timed out each time, but no agent subsequently dequeued it again, so it never re-entered `processing` state for `recover_timeouts()` to catch.

**Detection query:**
```bash
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c \"
SELECT queue_name, retry_count, COUNT(*) as count,
    MIN(enqueued_at)::timestamptz(0) as oldest,
    MAX(enqueued_at)::timestamptz(0) as newest,
    COALESCE(body->>'from', '(null)') as sender,
    body->>'subject' as subject,
    body->>'topic' as topic
FROM bus.messages
WHERE state = 'pending'
  AND retry_count >= (SELECT COALESCE(max_retries, 3) FROM bus.queues WHERE name = bus.messages.queue_name)
GROUP BY queue_name, retry_count, body->>'from', body->>'subject', body->>'topic'
HAVING COUNT(*) > 0
ORDER BY COUNT(*) DESC
LIMIT 20;
\"" 2>&1
```

**Remediation:**

⚠️ **`bus.dlq_move(msg_id)` does NOT exist in the schema.** Attempting to call it produces `ERROR: function bus.dlq_move(uuid) does not exist`. Use `bus.archive()` instead.

The correct approach requires getting the message ID first, then archiving it individually — `bus.archive()` takes a single `msg_id`.

**Step 1 — Get the stuck message IDs:**
```bash
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c \"
SELECT msg_id::text, queue_name, body->>'subject' as subject,
    retry_count, enqueued_at::timestamptz(0)
FROM bus.messages
WHERE state = 'pending'
  AND retry_count >= (SELECT max_retries FROM bus.queues WHERE name = bus.messages.queue_name)
  AND queue_name = 'inbox_target'
ORDER BY enqueued_at;
\"\" 2>&1
```

**Step 2 — Archive each via `bus.archive()` with explicit `::uuid` cast:**
```bash
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -c \"
SELECT bus.archive('inbox_target', '<msg_id>'::uuid, 'esther-remediation');
\"\" 2>&1
```

Repeat for each stuck message ID. Verify the queue is clean afterward with the detection query from Step 1.

**Bulk fallback (bypasses proper archive function — use only when you're sure all are orphaned):**
```bash
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -c \"
UPDATE bus.messages SET state = 'archived', archived_at = NOW()
WHERE state = 'pending'
  AND retry_count >= (SELECT max_retries FROM bus.queues WHERE name = bus.messages.queue_name)
  AND queue_name = 'inbox_target';
\"\" 2>&1
```

> **Why individual archiving:** `bus.archive()` logs the action via `bus.audit()` and handles DLQ chain metadata correctly. The direct UPDATE is faster for bulk cleanup but skips audit logging — acceptable for known-orphaned messages where you want to clear a backlog fast.

**Root cause:** Target agent stopped dequeuing. The message was picked up by visibility timeout (default 30s), retried, exhausted max_retries, and the agent never dequeued it again. Fix by clearing backlog or restarting the agent's consumer.

### 10. Raw-Field Wrapper Messages

Some bus senders wrap the payload inside a `raw` field, producing messages like:
```json
{"raw": "{\"from\": \"moses\", \"to\": \"moses\", \"topic\": \"health\"}"}
```

This means `body->>'from'` evaluates to `NULL` at the top level. The sender data is nested inside `body->'raw'->>'from'` after a JSON decode of the inner string.

**Detection query:**
```bash
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c \"
SELECT COUNT(*) as count, queue_name
FROM bus.messages
WHERE state = 'pending'
  AND body->>'from' IS NULL
  AND body ? 'raw'
GROUP BY queue_name
ORDER BY COUNT(*) DESC;
\"" 2>&1
```

**Reading actual content:**
```bash
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c \"
SELECT msg_id, queue_name,
    body->'raw'->>'from' as actual_sender,
    body->'raw'->>'subject' as actual_subject,
    body->'raw'->>'topic' as actual_topic,
    enqueued_at::timestamptz(0)
FROM bus.messages
WHERE state = 'pending'
  AND body->>'from' IS NULL
  AND body ? 'raw'
ORDER BY enqueued_at DESC
LIMIT 20;
\"" 2>&1
```

### 11. Fleet-Wide Queue Scan During Inbox Processing

When an inbox-processing cron runs, scan all queues for a fleet-wide health picture — even though you can only act on your own queue. This surfaces backlogs in other agents.

```bash
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c \"
SELECT queue_name, state, COUNT(*) as count,
    MIN(enqueued_at)::timestamptz(0) as oldest,
    MAX(enqueued_at)::timestamptz(0) as newest
FROM bus.messages
GROUP BY queue_name, state
ORDER BY queue_name, state;
\"" 2>&1
```

Compare depths:
- **0:** Clean
- **1–50:** Normal backlog
- **50–200:** Moderate — flag in report
- **200+:** Elevated — escalate

**Note:** PSQL access is via local `sg docker` gateway. For remote agents, use the bus API at `/api/pgmq/queues` (lists all queues but not per-message detail).

## Common Issues

### DLQ Messages Accumulating Without Auto-Archive

**Symptom:** DLQ depth grows without bound, old messages (6h+) stay in `pending` state.

**Root cause:** The `is_dlq` flag was not set on DLQ queues — `bus.recover_timeouts()` Step 3 (auto-archive) checks `WHERE q.is_dlq = true` and silently skips queues where it's false. Also Step 2 cannot chain-delete exhausted DLQ messages, causing `_dlq_dlq` accumulation.

**Fix:**
```bash
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -c \"
UPDATE bus.queues SET is_dlq = true WHERE name LIKE '%_dlq%' AND is_dlq = false;
\"" 2>&1

# Run recovery to immediately clear old messages
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c \"
SELECT bus.recover_timeouts();
\""
```

After fix, the cron `orch-bus-recover-timeouts` (every 5m) auto-maintains the DLQ. Verify with queue overview query.

**Prevention:** The queue creation code at `core/cortex_bus/queue.py:create_queues_for_agent()` already sets `is_dlq = true` — the bug only affects queues created before the column was added to the schema.

### recover_timeouts Fails with messages_queue_name_fkey (missing DLQ row)

**Symptom:** `orch-bus-recover-timeouts` cron (every 5m) fails with `Script exited
with code 1`; running the function directly shows:
`ERROR: insert or update on table "messages" violates foreign key constraint
"messages_queue_name_fkey" — Key (queue_name)=(inbox_orchestrator_dlq) is not
present in table "queues".`

**Root cause:** a queue exists in `bus.queues` but its `<queue>_dlq` row was
never seeded. The seed creates `inbox_orchestrator` without its DLQ
(`core/cortex_bus/schema/auth.sql`, 2026-08-12), while agent inboxes get DLQs
via `create_queues_for_agent()`. `recover_timeouts()` Step 2b moves exhausted
processing messages to `queue_name || '_dlq'` — the FK fails and **kills the
whole run**, so the cron never recovers anything.

**Fix (2026-08-12):** two layers, both in the repo:
1. **Seed** — `auth.sql` now inserts `inbox_orchestrator_dlq` (`is_dlq=true`,
   `parent_queue='inbox_orchestrator'`) next to the shared inbox.
2. **Defensive** — `recover_timeouts()` Step 2b now auto-creates any missing
   `_dlq` queue row before the move:
   ```sql
   INSERT INTO bus.queues (name, is_dlq, parent_queue)
   SELECT DISTINCT m.queue_name || '_dlq', true, m.queue_name
   FROM bus.messages m
   LEFT JOIN bus.queues q ON q.name = m.queue_name || '_dlq'
   WHERE q.name IS NULL AND m.state = 'processing'
     AND m.timeout_at < now() AND m.retry_count >= m.max_retries
   ON CONFLICT (name) DO NOTHING;
   ```

**Apply to a live DB** (schema changes deploy via file copy, not auto-applied):
```bash
sg docker -c "docker exec -i mycortex-postgres psql -U mycortex -d mycortex -v ON_ERROR_STOP=1 -f -" < core/cortex_bus/schema/queue.sql
sg docker -c "docker exec -i mycortex-postgres psql -U mycortex -d mycortex -v ON_ERROR_STOP=1 -f -" < core/cortex_bus/schema/auth.sql
```

**Verify:** `SELECT bus.recover_timeouts();` returns a number (not an error), and
`SELECT name FROM bus.queues WHERE name = '<queue>_dlq';` exists for every
non-DLQ queue. Check for other missing DLQ rows: `SELECT name FROM bus.queues
WHERE is_dlq = false AND name || '_dlq' NOT IN (SELECT name FROM bus.queues)`.

### All Bus Tools Return 401 (Not 200)

The MCP bus tools (`mcp__cortex_bus__*`) return HTTP 401 when:
1. `CORTEX_BUS_TOKEN` in `.env` doesn't match the hash in `bus.tokens` table
2. The token is missing entirely from the PG table

**Diagnostic:**
```bash
# Check which tokens exist
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -c \"
SELECT agent_name, substring(token_hash::text, 1, 20) as token_prefix, rotated_at
FROM bus.tokens ORDER BY agent_name;
\""

# Verify your .env token matches
grep CORTEX_BUS_TOKEN ~/hermes-cortex/.env
```

### Bus Unreachable (Connection Refused)

**Symptom:** `curl http://127.0.0.1:8903/health` fails.

**Check:**
```bash
# Is the bus process running?
ss -tlnp | grep 8903

# Is the systemd service active?
systemctl --user status cortex-bus.service

# Restart if needed
systemctl --user restart cortex-bus.service
```

Note: The bus at `:8903` is a direct local connection. It's also proxied through nginx at the orchestrator's bus port (e.g. `:13004` for Moses, `:14004` for Esther) with Bearer auth. The MCP tools route through nginx, not directly.

## Forwarder: role-aware PEER resolution (2026-08-03)

**Symptom:** Esther's `orch-bus-forwarder.py` silently self-synced (Esther↔Esther) — the "mirror of Moses' bus" never existed, and the forwarder skipped sync since Jul 31 (`peer_downed_at` stuck).

**Root cause:** `PEER_URL` defaulted to `CORTEX_BUS_FALLBACK_URL` — which on Esther's host is HER OWN external URL (`:14004`). The fallback URL is "my bus when primary is down", NOT "the other orchestrator".

**Fix (commit `fc9aafdb`):** role-aware peer resolution in both module-level and `main()` config resolution:
- On **Esther**: peer = Moses = `CORTEX_BUS_URL` (`:13004`)
- On **Moses**: peer = Esther = `CORTEX_BUS_FALLBACK_URL` (`:14004`)
- `PEER_AUTH` falls back to `CORTEX_BASIC_AUTH` (nginx Basic creds — external peer = nginx, Bearer gets 401)

**Verify:** run the forwarder; state file `~/.hermes-cortex/state/bus-forwarder-state.json` should show `peer_downed_at` cleared and "Peer recovered — drained N→local, N→peer".

**Config resolution (commit `c8c54b4b`, 2026-08-05):** the forwarder reads its
config (LOCAL_URL/TOKEN, PEER_URL/AUTH/TOKEN) in **env → `cortex-bus.conf` →
`~/.hermes-cortex/.env`** order. Before this fix it read `os.environ` ONLY
despite the docstring claiming conf/.env fallback — so cron runs (no env)
resolved empty `PEER_URL`/`PEER_AUTH`/`LOCAL_TOKEN` and the LOCAL→PEER drain
failed silently (failover messages sat on the backup bus even after the primary
returned). Symptom: `orch-bus-forwarder-sync` cron reports `LOCAL→PEER: N
failed` every tick, or `total_local_to_peer` stops advancing. Fix keeps every
config key resolvable from the conf in a bare env; `_load_config_file` /
`_resolve_var` are defined above the config block (were after use — NameError
at import). Verify: run the forwarder in a bare env and confirm `PEER_URL`
resolves from `cortex-bus.conf`; a manual drain run pushes stranded messages
(`total_local_to_peer` increments) and worker inboxes empty locally.

**ACL prerequisite (2026-08-03):** the backup orchestrator's `orch-bus-forwarder`
mirrors ALL `inbox_*` queues to the peer, so its `bus.permissions` row on the
PRIMARY's bus needs every inbox queue in `can_read` + `can_write`. Without it,
LOCAL→PEER drain fails with `403 — Agent 'esther' does not have write access to
queue 'inbox_gisu'` (per-queue ACL at `core/cortex_bus/server.py`
`_check_permission`). Grant SQL: `docs/esther-bus-setup.md` Step 7. Symptom:
`orch-bus-forwarder-sync` cron alerts `LOCAL→PEER: N failed` every tick while
the messages sit in the local queues indefinitely.

## Dedup: consumed copies are never re-forwarded (2026-08-12)

**Symptom:** a single `hc send gisu EXEC "…cortex-doctor.py…"` produced **3
identical EXECs** in `inbox_gisu` with the same `correlation_id`
(`send-ba7f68e22d6a`) at 00:04/00:06/00:11 KST. Gisu's handler archived all
three (corr-idempotent), but the duplicate-delivery race left a task row
pending ~10h. The same window showed duplicated UPDATE_REQUESTs / EXECs on
**every** agent's inbox (joseph 3×, kustos/titus/moses 2–3×).

**Root cause:** `_sync_direction` in `orch-bus-forwarder.py` skipped a message
whose dedup key already existed on the destination **without recording it in
`seen`** — the old comment said "the mirror should warm it again next tick".
But when the real consumer (the worker's `agent-message-handler`) archives the
destination copy, the next tick re-forwarded the lingering backup copy back to
the primary: fresh `msg_id`, same `corr`. Repeat every consumer tick.

**Fix:** the dest-hit skip now does `seen.add(dkey)` — each logical message
forwards at most once per direction per host. A consumed copy is a DELIVERED
message, not a gap to re-warm. Regression test:
`tests/test-bus-forwarder-dedup.py` (RED on old code, GREEN on fix).

**`hc bus` on hosts without the local bus schema (2026-08-12):** `hc bus`
reads the LOCAL Postgres via `docker exec` — on hosts whose `mycortex-postgres`
lacks `bus.messages`/`bus.queues` (or container down), `cmd_bus` used to
traceback with `UnboundLocalError` because the queue-summary block was skipped.
Fixed in `6876e47c`: `total_pending`/`total_proc` initialized up front,
`local_db_ok` flag set on error, and the final branch prints
`⚠️ Local bus DB unavailable` instead of crashing or a false "No activity".
`hc bus --all` never crashed (different branch) — that's why it slipped
through. The remote bus itself is healthy; use `hc status`/`hc depth` for the
fleet view.

**Inspect for duplicates** (per-agent, recent window):
```bash
cd ~/hermes-cortex/ops/scripts && python3 -c "
import sys, json; sys.path.insert(0, '.')
from lib.cortex_bus import bus_archives
for a in ('gisu','joseph','kustos','titus','moses'):
    arch = bus_archives(f'inbox_{a}', limit=400, since_minutes=720)
    corrs = {}
    for m in arch:
        b = m.get('body') or {}; c = b.get('correlation_id') or '?'
        corrs.setdefault((c, b.get('subject')), 0)
        corrs[(c, b.get('subject'))] += 1
    dups = {k: v for k, v in corrs.items() if v > 1}
    print(a, 'duplicates:', len(dups))
"
```

## Token rotation (Bearer, `hbus_*`)

- **Hash scheme:** `bus.tokens.token_hash` = `hashlib.pbkdf2_hmac("sha256", token, b"hermes-bus-salt", 100000).hex()` (`core/cortex_bus/auth.py hash_token`).
- **Rotate:** generate `"hbus_" + secrets.token_hex(32)` → update `~/hermes-cortex/.env` AND `~/.hermes-cortex/cortex-bus.conf` (both carry `CORTEX_BUS_TOKEN`; the forwarder's `LOCAL_TOKEN` reads the conf) → `UPDATE bus.tokens SET token_hash='<pbkdf2(new)>', rotated_at=NOW() WHERE agent_name='<agent>'` → verify Bearer against the LOCAL bus (`127.0.0.1:8903`): new → 200, old → 401.
- **Verify Bearer on the LOCAL bus only.** Testing Bearer against the external nginx port (`:13004`/`:14004`) is meaningless — nginx validates Basic auth and sets `X-Forwarded-User`; a Bearer header sent through nginx is ignored (401 for missing Basic). A token that "401s" through nginx can still be LIVE on the local bus.
- **Identity mapping pitfall:** a token found in another agent's docs/config may be a DIFFERENT agent's row — the esther setup guide carried MOSES' token (esther's `.env` seeded with it), so it authenticated as moses with full queue privileges. Before rotating, look up the identity by hash: `SELECT agent_name FROM bus.tokens WHERE token_hash='<pbkdf2(leaked)>' AND is_active=true`. Rotate the MAPPED row (or sync it to the owner's real token hash).
- **Peer-bus consistency:** each orchestrator's Postgres is independent; if the peer's token row on your bus doesn't match his real token, sync it from his bus (`SELECT token_hash FROM bus.tokens WHERE agent_name='moses'` on his host, then UPDATE your row) so a leaked token dies on your bus too.
- **Rotation order (configs first):** update consumer configs (`.env`, `cortex-bus.conf`) BEFORE the token table so the forwarder/MCP never hit a dead token mid-rotation.

## Stale-mirror sweep — backup bus no longer grows forever (2026-08-14)

**Symptom:** `inbox_orchestrator` (or any `inbox_*`) on the BACKUP orchestrator's
bus accumulates pending messages monotonically — 74→94→196 over days, 3rd
fleet sighting (joseph escalation). The primary bus stays clean; the backup's
own queue-depth watchdogs never cover it (depth-watchdog checks only own
inbox; confirmation-poller checks only the primary URL).

**Root cause:** the backup bus is a warm-standby MIRROR: the forwarder copies
pending messages from the primary (PEER→LOCAL) and nothing consumes them while
the primary is up (the backup's handler polls the primary by design). The
2026-08-12 dedup fix (record dest-hit in `seen`) stopped duplicate
re-forwarding but stranded every mirrored-back copy forever: a copy whose
dedup key was in `seen` was skipped every tick and NEVER archived.

**Fix (commit `ea833284`):** stale-mirror sweep in `_sync_direction` — on a
BACKUP source (`can_archive_source=True`), a copy whose key is already in
`seen` (forwarded once or dest-hit-confirmed) is archived once the peer
CONFIRMS it no longer holds the original (consumed). Failover-safe:
`_dest_has_key` is tri-state (True/False/None); a copy is kept when the
original is still pending on the primary, or when the peer is unreachable
(None — never archive blind during an outage; the local copy may be the only
snapshot of an unconsumed message). Tests 4-6 in
`tests/test-bus-forwarder-dedup.py` (RED on old code, GREEN on fix).

**Diagnostic:** `SELECT queue_name, state, COUNT(*) FROM bus.messages GROUP BY 1,2`
on the backup's Postgres — a growing `pending` count of `topic='reports'`
mirrors (skill/learning reports, each ×2: original + mirror) is the signature.

## Shared orchestrator inbox (`inbox_orchestrator`, 2026-08-03)

Workers' fix requests to `inbox_moses` are **invisible to Esther** — each agent
only polls its own inbox. The backup orchestrator literally cannot see worker
escalations when the primary is down. Fix: a shared `inbox_orchestrator` queue
both orchestrators read/write — now the **default target** for all agent →
orchestrator traffic:

- **Schema:** `core/cortex_bus/schema/auth.sql` seeds the queue idempotently (also auto-creates on first send)
- **Handler:** `agent-message-handler.py` on orchestrators polls `inbox_orchestrator` as a secondary queue — **archive from the SOURCE queue** (`source_queue`, not the hardcoded own-inbox name)
- **Workers:** `contact-orchestrator.sh` defaults to `inbox_orchestrator` (override with `CORTEX_INBOX_TARGET` only for point-to-point replies)
- **Docs:** ACL table in `docs/bus-architecture.md` + `docs/reference/cortex-bus-config.md` (orchestrators read `inbox_orchestrator`; workers `can_send` it)

**ACL model:** BOTH buses use the canonical **per-queue array** ACLs
(`can_read`/`can_write` `TEXT[]` + `is_admin`) in `bus.permissions` — unified
2026-08-04. The old boolean model (`can_send`/`can_archive`/`can_requeue`,
`ops/services/cortex-bus/server.py`) is **deleted**. If a 403 appears, check
the agent's `can_write` array, not boolean flags.

## References

- `references/forwarder-peer-resolution.md` — role-aware PEER fix detail (2026-08-03)
- `references/credential-rotation.md` — credential leak response & rotation playbook: bearer-vs-Basic exposure model, live-test baseline method, Basic-auth (htpasswd) rotation blockers on orchestrator hosts, scrub caveats, concurrent-session git safety (2026-08-03)
- `references/dlq-monitor-fix.md` — DLQ alert fix: processing state detection + silent-when-clean pattern for `orch-bus-confirmation-poller.py report`
- `references/cross-server-architecture.md` — Per-server independent Postgres architecture: why local `inbox_moses` sends don't reach the orchestrator, fleet port map, and correct curl pattern for cross-server messages
- `core/cortex_bus/queue.py` — Queue creation, DLQ logic, send/read/archive
- `core/cortex_bus/server.py` — HTTP API, auth, dashboard
- `docs/orch-bus-setup.md` — Architecture, security model, deployment guide, DLQ maintenance section
- `docs/esther-bus-setup.md` — Maintenance steps, changelog (DLQ fix, threshold changes, pipeline updates)
