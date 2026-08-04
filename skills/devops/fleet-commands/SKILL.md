---
name: fleet-commands
version: 1.6.0
category: devops
description: "Send operational commands to fleet agents via the PGMQ bus — message format, delivery verification, bus_access expectations, schema-validated EXEC payloads, and cleanup."
platforms: [linux]
author: moses
metadata:
  hermes:
    tags: [bus, fleet, commands, messaging, hc, pgmq]
    related_skills: [agent-bus, hermes-cortex-deployment]
---

# Fleet Commands — Agent Commanding via the Bus

## Overview

Send structured operational commands from the orchestrator (Moses) to any fleet agent's inbox queue on the PGMQ bus. Messages land immediately and are consumed according to each agent's `bus_access` (host/client).

**Architecture rule — three consumption modes:**

| Mode | Who | How | Covers |
|------|-----|-----|--------|
| **In-session** | Moses (orchestrator) | Directly reads its inbox via MCP tools + `hc` CLI during active sessions. | Skill reports, EXEC_RESULT, health pings, incoming requests. |
| **Out-of-session** | Moses | `agent-bus-workday/evening/overnight` LLM crons process `inbox_moses` using the Inbox Message Decision Framework. | Same as in-session, but when no user is chatting. |
| **Fleet handler** | Esther, Joseph, Gisu, Kustos | `agent-message-handler.py` cron (every 5 min, no_agent script) processes their inbox. | UPDATE_REQUEST, EXEC, ROLLBACK_REQUEST, GIT_AUTH_CHECK from orchestrator. |

**Corrected 2026-08-02: Moses DOES run `agent-message-handler.py` on itself** (cron list shows it every 5 min, thousands of runs). It processes `inbox_moses` — `*_RESULT` replies, silent noise subjects (DOCTOR_TEST/STATUS_REQUEST/HEARTBEAT/PING), and any registered data-subjects. **Unknown subjects get ARCHIVED + an error response sent** within minutes of landing. So any NEW inbound message type to `inbox_moses` (fleet agents sending data TO the orchestrator) MUST get a handler branch first, or the payload is destroyed from the live flow. Example: "Skill Stub Recovery" messages (full skill content from agents) were eaten as unknown until the handler was patched to stage them to `state/skill-stub-recovery/` (commit 8a38e486). Design: agents CANNOT write the repo — they send payloads to `inbox_moses`; the handler stages them to a state dir; the orchestrator evaluates/copies later (store-first, evaluate-later).

**Primary tool:** `hc send <agent> <subject> <body>` (admin CLI, operates via docker exec into Postgres)

**Round-trip tool:** `hc exec <agent> <script> [args...]` (sends EXEC, polls up to 5min for EXEC_RESULT)

The `COMMAND:` subject prefix is for human-readable messages (logged/archived, no automated response). For structured task delegation, use the agent-message-handler protocol below.

### Structured Command Protocol (agent-message-handler)

Fleet agents run `agent-message-handler.py` as a cron (`*/5 * * * *`). Source: `ops/scripts/agent/agent-message-handler.py`.

**Message format (sent via `hc send` or `bus.send`):**
```json
{
  "from": "moses",
  "to": "<agent>",
  "topic": "fleet-update",
  "subject": "EXEC",
  "correlation_id": "<unique-uuid>",
  "body": "{\"command\": \"script-name.py\", \"params\": [\"--flag\"], \"timeout\": 60}"
}
```

**correlation_id is required** for idempotency. Messages without one may be silently skipped if `""` is in the handler's processed set.

### Supported Subjects

| Subject | Action | Response | Body Fields |
|---------|--------|----------|-------------|
| `EXEC` | Run script under `~/.hermes-cortex/scripts/` | `EXEC_RESULT` | `command`, `params[]`, `timeout` |
| `UPDATE_REQUEST` | Run `cortex-update.sh` | `UPDATE_RESULT` | `target_sha`, `target_version`, `run_doctor` |
| `ROLLBACK_REQUEST` | Git checkout previous SHA | `ROLLBACK_RESULT` | `target_sha`, `reason` |
| `GIT_AUTH_CHECK` | Verify git can `ls-remote` | `GIT_AUTH_RESULT` | `expected_url` |
| `DIAGNOSTIC_REQUEST` | Run agent-diagnostic.py | `DIAGNOSTIC_RESULT` | `check`, `respond_to_queue` |

### Round-trip with `hc exec` (Recommended)

For EXEC commands, `hc exec` handles the full lifecycle:

```bash
hc exec esther manage/cortex-doctor.py --json
hc exec joseph manage/cortex-doctor.py --quiet
hc exec gisu -- df -h /
```

It generates a `correlation_id`, sends the EXEC, then polls `inbox_moses` every 15s for up to 5min waiting for `EXEC_RESULT`.

#### Schema-validated EXEC (S2)

Since v4 of the agent registry, every EXEC payload is validated against the
`EXEC` JSON Schema before sending and the result against `EXEC_RESULT` by default.
Use `--output-schema` to change the expected result schema:

```bash
# Default: validates result against EXEC_RESULT schema
hc exec kustos manage/cortex-doctor.py --json

# Custom output schema: validates against WAVE_RESULT
hc exec esther manage/setup.sh --output-schema WAVE_RESULT

# RAW mode: skip result validation
hc exec moses -- df -h / --output-schema RAW
```

Available schemas: `EXEC`, `EXEC_RESULT`, `WAVE_RESULT`, `UPDATE_REQUEST`,
`UPDATE_RESULT`. See `ops/scripts/lib/handoff_schema.py`.

If validation fails, `hc exec` prints the violations before the result summary.

### Manual round-trip verification

When using `hc send` instead:

1. Send: `hc send <agent> "<subject>" '<json-body>'`
2. Confirm pending: check queue state
3. Wait: handler runs `*/5 * * * *`
4. Confirm processing → archived
5. Check `inbox_moses` for response

## When to Use

- Sending health-check requests to fleet agents
- Triggering doctor runs on remote agents
- Requesting disk/report/service status from a specific agent
- One-shot operational commands that don't need a full workflow
- Testing bus connectivity to a specific agent

## Precondition: Clean Bus Before Send

**Critical rule: the bus must be clean before sending new commands.** Stale/stuck messages from previous rounds (especially `processing` state messages from crashed handlers) interfere with new commands — the handler crashes trying to process old ones instead of the fresh command.

Before every fleet command round, check for stale UPDATE_REQUESTs, EXECs, and diagnostic messages. Archive them before sending new ones.

**Failure pattern (2026-07-21):**
1. Send UPDATE_REQUEST to all 5 agents
2. Esther's handler crashes — message stuck in `processing`
3. Clean up and resend to 4 agents (excluding Titus)
4. Esther's NEW request lands but old stuck one is still there — now 2 stuck messages
5. User: *"Clean the bus before you send"*

**Fix:** Before any `for agent in ...; do hc send "$agent" ...`, run a bus check and archive stale messages.

## Workflow

### 1. Survey the fleet

Check agent registry for bus_access and role:

```bash
cat ~/.hermes-cortex/state/agent-registry.json | python3 -c "
import json,sys; reg=json.load(sys.stdin)
for k,v in reg.get('agents',{}).items():
    caps = v.get('capabilities', {})
    ba = caps.get('bus_access', '?')
    role = v.get('role', '?')
    print(f'  {k}: bus_access={ba} role={role}')
"
```

### 2. Send the command

```bash
hc send <agent> "COMMAND:<action>" "<descriptive body>"
```

Returns a msg_id on success. Save it for verification and cleanup.

Standard command subjects (human-readable, no automated response):

| Subject | Purpose |
|---------|---------|
| `COMMAND:health-check` | Full system health — CPU/memory/disk/services |
| `COMMAND:doctor-report` | Run cortex-doctor.py, report failures |
| `COMMAND:disk-check` | Disk usage — report partitions above 85% |
| `COMMAND:ping-test` | Test ping — acknowledge receipt |
| `COMMAND:update-repo` | Pull latest, deploy, verify |

**NOTE:** `COMMAND:` messages with no structured JSON body are NOT processed by `agent-message-handler.py`. They land in the queue and are archived as "unknown subject" after the handler reads them. For structured execution, use the EXEC protocol above.

### 3. Verify delivery

```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT queue_name, state, COUNT(*) as count
FROM bus.messages
WHERE queue_name = 'inbox_<agent>'
GROUP BY queue_name, state;
\""
```

| State | Meaning |
|-------|---------|
| `pending` | Message landed, waiting for agent |
| `processing` | Agent popped it (visibility timeout active) |
| Empty | Already archived or consumed |

### 4. Peek message content

**⚠️ Body is double-encoded JSON.** The PGMQ `body` column stores the entire message as a JSON *string*, not a JSON *object*. Using `body->>'subject'` returns **null** because `body` itself is a string value, not a JSON object with a `subject` key. Always use the double-parse pattern `(body::jsonb #>> '{}')::jsonb` to unwrap:

```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT msg_id::text,
       (body::jsonb #>> '{}')::jsonb->>'from' as sender,
       (body::jsonb #>> '{}')::jsonb->>'subject' as subject,
       (body::jsonb #>> '{}')::jsonb->>'correlation_id' as corr,
       enqueued_at::timestamptz(0)
FROM bus.messages
WHERE queue_name = 'inbox_<agent>' AND state = 'pending'
ORDER BY enqueued_at;
\\\""
```

**Quick reference — always use the double-parse pattern:**
| Wrong (returns null) | Correct |
|---|---|
| `body->>'subject'` | `(body::jsonb #>> '{}')::jsonb->>'subject'` |
| `body->'body'->>'success'` | `((body::jsonb #>> '{}')::jsonb->'body')->>'success'` |
| `body->>'correlation_id'` | `(body::jsonb #>> '{}')::jsonb->>'correlation_id'` |

### 5. Confirm consumption

Check audit log for reads on the target queue:

```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT action, agent_name, queue, COUNT(*) as cnt,
    MIN(created_at)::timestamptz(0) as first_seen
FROM bus.audit_log
WHERE queue = 'inbox_<agent>'
  AND created_at > NOW() - INTERVAL '5 minutes'
GROUP BY action, agent_name, queue
ORDER BY queue, action;
\""
```

### 6. Clean up test messages

After test or one-shot commands, archive to prevent DLQ cycling:

```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -c \"
SELECT bus.archive('inbox_<agent>', '<msg_id>'::uuid, '<cleanup-label>');
\""
```

Labels like `moses-test-cleanup` help identify sources in the audit log.

## bus_access Delivery Matrix

| Access | Received? | How | Agents |
|--------|-----------|-----|--------|
| `host` | ✅ Yes | Runs bus server + polls. Consumes within watch interval (~10m). | moses, esther |
| `client` | ✅ Yes (eventually) | Polls the shared bus. Consumes during next watch cycle. | joseph, kustos, gisu, titus |

> **Note:** Poll agents use `vt=0` peek (non-destructive SELECT) to check for messages. A separate handler cron pops and processes pending messages. If a message stays `pending` across multiple reads, it's waiting for the handler — not stuck.

### Testing protocol: prove it on yourself first

**Hard rule:** Never send a command to a fleet agent until you've proven the identical flow works on yourself (Moses → Moses → your inbox). A test that skips the local step is not a test — it's a gamble.

**Local test checklist:**
1. Send the EXEC/command to `inbox_moses` with a unique `correlation_id`
2. Run the handler manually: `python3 scripts/agent-message-handler.py --once`
3. Verify handler output shows it consumed and processed the message
4. Query `inbox_moses` for the EXEC_RESULT with matching correlation_id
5. Parse the result — confirm exit_code, stdout, success flag all present
6. Archive the test message
7. Only then send to a fleet agent

### Verifying a Specific Agent's Bus Connectivity

When you need to test whether a specific agent (e.g. Esther) can receive and process bus commands, follow this diagnostic flow:

**Step 1 — Check if the agent is alive on the bus**
```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT action, queue, created_at::timestamptz(0)
FROM bus.audit_log
WHERE agent_name = '<agent>' AND created_at > NOW() - INTERVAL '10 minutes'
ORDER BY created_at DESC LIMIT 5;
\""
```
- If you see `read` actions → agent's handler is running and polling
- If you see `archive` → agent consumed messages recently
- If empty → agent's handler is offline or not connected to this Postgres

**Step 2 — Check inbox state**
```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \\"
SELECT state,
       (body::jsonb #>> '{}')::jsonb->>'subject' as subject,
       (body::jsonb #>> '{}')::jsonb->>'correlation_id' as corr
FROM bus.messages WHERE queue_name = 'inbox_<agent>'
ORDER BY enqueued_at DESC LIMIT 3;
\\\""
```
- `pending` → message landed but handler hasn't read it yet
- `processing` → handler picked it up (VT active). Check timeout_at. Old processing = stuck handler.
- Empty → clean slate, send fresh

**Step 3 — Send a known-good command**
Use `UPDATE_REQUEST` (tests full read→process→respond→archive cycle) or `EXEC` with `agent-diagnostic.py` (deployed everywhere). Do NOT use `echo`, `whoami`, `df` — these are PATH commands, not scripts. Exit code -1 = "script not found".
```bash
TOKEN=$(grep CORTEX_BUS_TOKEN ~/hermes-cortex/.env | cut -d= -f2)
CORR="test-<agent>-$(date +%s)"
curl -s -X POST http://127.0.0.1:8903/api/pgmq/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"queue\":\"inbox_<agent>\",\"message\":{\"from\":\"moses\",\"to\":\"<agent>\",\"topic\":\"fleet-test\",\"subject\":\"EXEC\",\"correlation_id\":\"$CORR\",\"body\":\"{\\\"command\\\": \\\"agent-diagnostic.py\\\", \\\"params\\\": [], \\\"timeout\\\": 30}\"}}"
```

**Step 4 — Wait for consumption**
The handler checks every 5 min on fleet agents. After ~5 min, re-check audit log for `read` + `archive` actions. A Telegram notification like `📥 [agent] Received EXEC from moses` confirms pickup.

**Step 5 — Verify response (check live queue AND archives)**

Results may be consumed by your own handler within 5 minutes. Always check both `bus.messages` (live) and `bus.archives` (history).

```bash
# Check live queue first
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \\"
SELECT queue_name, state,
       (body::jsonb #>> '{}')::jsonb->>'subject' as subject,
       (body::jsonb #>> '{}')::jsonb->>'correlation_id' as corr
FROM bus.messages WHERE queue_name = 'inbox_moses'
ORDER BY enqueued_at DESC LIMIT 5;
\\\""

# Check archives if live queue is empty
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \\"
SELECT archived_at::timestamptz(0),
       (body::jsonb #>> '{}')::jsonb->>'subject' as subject,
       (body::jsonb #>> '{}')::jsonb->>'from' as sender,
       (body::jsonb #>> '{}')::jsonb->>'correlation_id' as corr
FROM bus.archives
WHERE archived_at > NOW() - INTERVAL '15 minutes'
ORDER BY archived_at DESC LIMIT 5;
\\\""
```
Look for `EXEC_RESULT` or `UPDATE_RESULT` with matching correlation_id.

**If the agent reads but never responds** (audit shows `read` but no result in inbox_moses):
- Check if `bus.send()` from the agent to inbox_moses works (see "half-connectivity" pitfall)
- The agent may have the wrong CORTEX_BUS_URL or auth
- The handler may crash before `send_bus_result()` (check for Telegram ❌ notification from agent)

**Timeline (Esther, 2026-07-23):**
- 12:05 UTC — UPDATE_REQUEST sent, read at 12:05, processed (cortex-update failed on her machine)
- 12:06 UTC — EXEC echo sent, read at ~12:08, exit=-1 (script not found)
- 12:11 UTC — EXEC agent-diagnostic.py sent, result pending
- Key finding: bus transport works (read+archive), handler processes, script execution depends on whether target script exists on that agent

**⚠️ Use a script deployed on ALL agents, not a one-off.**
The EXEC handler runs commands from `~/.hermes-cortex/scripts/` on the target machine. Standard PATH commands like `echo`, `whoami`, `df` are NOT available there. If you test yourself with a locally-created custom script but send a PATH command to fleet agents, the test is asymmetric and they will fail with `exit=-1 "Script not found"`.

Always self-test with the EXACT same script you will send to fleet agents:
- `agent-diagnostic.py` — deployed everywhere via cortex-update.sh, works on every agent
- Any script listed in `cortex-update.sh`'s `register()` calls

**Failure pattern (2026-07-23):** Self-tested with a locally-created `bus-ping-test.sh` (exit=0). Sent `echo` to Joseph, Kustos, Gisu — all returned exit=-1 "Script not found" because `echo` isn't in their scripts directory. The bus transport was fine; the command was wrong. Fixed by re-sending `agent-diagnostic.py` — all three returned exit=0.

**The 6-checkpoint rule (proven full-cycle):**
1. **Send** → message in target queue (pending, correct subject/correlation_id)
2. **Consume** → transitions pending → processing → archived
3. **Process** → command output in handler logs
4. **Respond** → EXEC_RESULT in inbox_moses with matching correlation_id
5. **Read** → orchestrator queries inbox, extracts structured result
6. **Inbox-verify** → orchestrator independently confirms the response by querying `inbox_moses` BEFORE reporting results to the user

Missing any one checkpoint means the test is incomplete. The user will notice.

**Critical: Telegram is for the user, NOT for you.** The handler sends Telegram notifications to Luke's DM so HE sees fleet activity in real time. When you see/hear about a Telegram notification, that is NOT a substitute for verifying the bus yourself. The Telegram tells you something happened — your own inbox query proves it. Do not report "agent X responded" based on a Telegram you heard about secondhand. Query your inbox, read the EXEC_RESULT/UPDATE_RESULT, then report.

**Testing technique: run handler manually while hc exec polls** — when testing on your own machine, you don't need to wait for the 5-min cron tick. Send the EXEC via `hc exec` in background mode, then immediately run the handler manually:
```bash
hc exec moses cortex-doctor.py --json
# In another terminal or shell:
cd ~/.hermes-cortex && python3 scripts/agent-message-handler.py --once
```
The `hc exec` polls every 15s for up to 5min. The handler processes within seconds. This is the fastest test cycle.

## Fleet Agent Issue Detection & Response

When you discover messages stuck `processing` on a fleet agent (never completes, state never transitions), the orchestrator MUST act immediately — do not wait to be asked or wait for the user to notice.

The bus is effectively broken for that agent (their handler is crashing/hanging), so you cannot reach them via EXEC either. **Send diagnostic instructions via Telegram** (the fallback channel):

```
Run a full diagnostic and report back:
1. Check handler cron exists and is enabled
2. Read handler state file (~/.hermes-cortex/state/agent-handler-state.json)
3. Check system load / memory / disk
4. Check latest handler output log
5. Run doctor
Return everything as raw output, don't summarize.
```

**Critical rule: send SEPARATE messages per agent, not one combined message.** Never combine instructions for multiple agents into one message. Intermingled instructions confuse them and produce no useful results. Each agent gets its OWN standalone diagnostic message. This is a hard rule — the user explicitly corrected this: *"Next time give me separate messages. The agents get confused when they are intermingled."*

After they report back, fix the identified issue (corrupt state file, handler crash, missing cron) and verify the bus recovers before proceeding.

## Pitfalls

- **Poll after send is not optional and not a question.** After dispatching any bus command (EXEC, UPDATE_REQUEST, etc.), the next action is ALWAYS to poll for results. The question "Want me to poll?" has the same answer every time: yes. Replace it with the polling loop. A command that was sent but whose result was never verified is not a completed action — it's a fire-and-forget gamble.
  - Correct: send → immediately poll inbox for result
  - Incorrect: send → ask the user "want me to poll?" → waste a round-trip
  - The user's reaction to this question in session 2026-07-21 was a single word: *"Seriously?"* — meaning the answer was so obvious the question should never have formed.

- **Re-running a collector/sync tool can DESTROY the recovery source — trace read-vs-write before dispatching.** When recovering data via a fleet tool (collect-agent-skills.sh, sync scripts), verify what the tool READS vs WRITES before running it on agents. The 2026-08-02 skill-stub recovery: re-running the old-style collector on agents would have overwritten the full-content `state/skill-contents` cache (the ONLY surviving full copies of 131 truncated skill imports) with stub content, because it regenerates its cache from the deployed (now-stubbed) files. cortex-update does NOT touch `state/skill-contents` (cache survives UPDATE_REQUEST), but the collector cron WOULD rewrite it. See `references/2026-08-02-skill-stub-recovery.md` for the hazard, the stub-guard fix, the read-only audit tool pattern, and the recovery sequence.

- **Answer the pointed verification question, then act — don't re-prove.** When the user asks "is the collection script correct?" they want the direct answer: trace the read/write paths, check the skip-logic target, state the hazard in one pass, then fix. Repeated rounds of re-proving (bus archives, git history, extra tests) after the problem is acknowledged draw a "just fix it, I don't need more proof" correction. One targeted verification of the hazard, then the fix.

- **Send separate messages per agent** — when multiple agents have the same issue, send each one its OWN standalone diagnostic message. Do not combine them into one message with agent names listed. Agents get confused when instructions for other agents are intermingled with theirs.

- **`bus_archive()` can fail silently** — `bus_archive()` catches all exceptions and returns `False` on failure (network, auth, timeout). Before the fix (commit `c306e3d`), `archive_message()` ignored the return value, so failed archives left messages in `processing` forever. The cycle: handler reads (vt=30) → processes → archive returns False silently → message stays `processing` → VT expires → re-read → idempotency skip → tries to archive again → fails → loops. **Fix:** handler now logs `⚠️ Failed to archive message` when archive fails.\n- **Missing `AGENT_NAME` in cortex-bus.conf** — handler determines which queue to poll from `AGENT_NAME` in `cortex-bus.conf`. If unset, it falls back to hostname, polling the wrong queue (e.g. `inbox_cisnet02` instead of `inbox_kustos`). Commands land in the correct queue but the agent never reads them. **Fix:** set `AGENT_NAME=<agent>` in cortex-bus.conf.\n- **COMMAND: prefix is not structured execution** — `COMMAND:health-check` messages land in the queue but are archived as "unknown subject" by the handler. For automated execution, use EXEC with a proper JSON body.
- **Handler drains up to 25 messages per 5-min tick** — `agent-message-handler.py` processes up to **25 messages per 5-min tick** on fleet agents (esther, joseph, gisu, kustos) AND on Moses (corrected 2026-08-02 — the orchestrator's cron list includes it). Previously (pre-2026-07-23, commit `9946158`) it processed only 1/tick, causing a 5+N-minute backlog for structured commands queued behind Learning Reports or health pings. Now the handler drains the queue on every tick, so backlog is rare. If commands still appear delayed, the agent has >25 backlogged messages or the handler fell behind.
- **correlation_id must be unique and non-empty** — messages without a `correlation_id` or with an empty one get caught by the idempotency check if `""` is in the processed set. Always generate a unique UUID.
- **Idempotency gap (FIXED 2026-07-21)** — previously, the handler skipped already-processed messages without archiving them, causing an infinite recovery→re-read→skip loop. Now the handler archives on idempotency skip. If you see messages stuck in `processing` forever, run `SELECT bus.recover_timeouts()` to flush them.
- **Verify the full send→execute→respond cycle** — sending a message successfully (`msg_id` returned) is only half the test. The command isn't complete until you verify the agent consumed it AND sent a result back. Check `inbox_moses` for `EXEC_RESULT` / `UPDATE_RESULT` with the matching correlation_id. The user will call out incomplete work if you only verify the send half.
- **recover_timeouts may return 0 with stuck messages** — `bus.recover_timeouts()` can return 0 even when `processing` messages have expired `timeout_at` timestamps (known PostgreSQL CTE materialization issue). Force-recover manually:
  ```sql
  UPDATE bus.messages 
  SET state = 'pending', timeout_at = NULL, retry_count = retry_count + 1
  WHERE state = 'processing' AND timeout_at < NOW();
  ```
- **Telegram notifications from handler** — the handler now sends Telegram notifications to Luke's DM on pickup (📥 `[agent] Received EXEC from moses`) and completion (✅/❌ `[agent] EXEC script.py: exit=N — output preview`). Uses Telegram Bot API directly: reads `TELEGRAM_BOT_TOKEN` from `~/.hermes/.env`, sends to chat_id `1270130526` with `timeout=10`. Not `hermes send` (may time out when gateway has MCP issues).
- **`hc send` is local only** — it uses `docker exec` to reach Postgres directly on this machine. Cannot send to remote agents from another machine. Remote agents connect via the nginx proxy (port 13004) with Basic auth.

- **Fleet dispatch BLOCKS silently without `--self-tested` — the warning is a gate, not a note.** `hc send <agent> UPDATE_REQUEST <body>` (no flag) prints *"Use --self-tested only AFTER the self-test is verified"* and sends NOTHING — the message never lands (bus stays empty). Verified 2026-08-02: 5 sends without the flag → zero messages in any inbox; re-issuing all 5 with `--self-tested` → all 5 landed `pending`. The required sequence is: (1) prove the identical flow on yourself — `hc send moses UPDATE_REQUEST <body>`, run `python3 scripts/agent-message-handler.py --once`, verify consumed/archived in `bus.archives`; (2) THEN re-issue the fleet loop with `--self-tested`. Self-test first, flag second — the flag exists to force exactly that order.
- **Direct API auth quirks** — the PGMQ `/api/pgmq/archive` endpoint may return "Invalid or expired token" when the Bearer token has whitespace/quote issues from shell extraction. The `hc` tool avoids this by going through psql directly. Use `bus.archive()` via psql for reliable cleanup.
- **Titus receives bus messages like every other agent (corrected 2026-08-02)** — Titus has `bus_access: client`, but that does NOT make him push-only. UPDATE_REQUESTs, COMMAND: notes, and EXEC payloads sent to `inbox_titus` land `pending` and are consumed by his `agent-message-handler.py` cron on the normal 5-min cycle — exactly like joseph/gisu/kustos. **Always include Titus in the fleet dispatch loop.** The user explicitly corrected this: *"titus gets messages just like everyone else."* (The earlier "push_only agents never poll — use a forwarder" pitfall was wrong and has been removed; `hc send titus ... --self-tested` delivers and he processes normally.)\n- **Active consumers archive immediately** — agents with `bus_access: host` that have a message handler will read and archive the message. You may not see it in `pending` if you check late.

- **`poll_once()` has no exception handler** — the dispatch block in `agent-message-handler.py` (lines 591–670) has no top-level try/except. If any of `process_update_request()`, `send_bus_result()`, or `save_state()` throws an unhandled exception, the handler **crashes silently** — message stays in `processing`, no log, no result returned. Unlike the archive-failure loop, no "Skipping already-processed" pattern appears. See `references/stuck-agent-diagnostics.md` → "The Poll-Once Crash Pattern" for diagnosis and fix.

- **`bus.archive()` may return 0 rows on processing messages** — known PostgreSQL CTE materialization issue. `bus.archive()` can return "0 rows" even when the message exists and matches the msg_id/queue_name. This is transient — retry or use the direct UPDATE to `pending` first, then archive.

- **Test with same script on yourself first** — the testing protocol section above covers this. The #1 recurring failure: self-test with a locally-created script, send a different command (e.g., `echo`) to fleet. Always self-test with the exact same script you will send to fleet agents. `agent-diagnostic.py` is deployed everywhere — use it.

- **Early archive must be before any processing** — the handler's `poll_once()` archives the message immediately after `read_inbox()` returns, before JSON parsing, notification, idempotency checks, or dispatch. If the handler crashes between the read and the archive, the message stays `processing` and loops on VT expiry. This was the root cause of Esther's stuck EXEC messages. Fix committed in `c7231c3`: moved `archive_message()` to right after `msg_id`/`correlation_id` extraction, before any logic that could crash.

- **Visibility timeout (VT) must cover max processing time** — the handler reads with `vt=120` (commit `feb8ef1`). Previously `vt=30` caused UPDATE_REQUEST to silently fail: handler popped the message (30s VT), started `cortex-update.sh` (43s), VT expired mid-update, message went back to `pending`, handler lost its lock, archive failed, and the UPDATE_RESULT was never sent. The 120s VT comfortably covers cortex-update + doctor + overhead (~96s total). When debugging stuck `processing` messages, always check `timeout_at` vs current time — if the VT has expired, the handler's processing time exceeds the VT.
- **cortex-update.sh exit=1 with empty stderr = soft success** — `cortex-update.sh` uses `set -euo pipefail` and `needs_update()` returns 1 for files already up to date (hashes match). This return code propagates as the script's exit code even though the update completed successfully. Fix (commit `821cdfd`): `run_cortex_update()` treats exit=1 as success when stderr is empty. If you see `UPDATE_RESULT success=false` with error `"cortex-update failed: "` (empty detail), check the handler cron log — the script likely completed normally.

- **Always check BOTH live queue AND archives for responses** — EXEC_RESULT/UPDATE_RESULTs land in `inbox_moses` but your own handler may consume and archive them within 5 minutes (the `*_RESULT` handler archives silently, commit `4188d70`). If you only query `bus.messages` (live queue) and see nothing, the result may already be in `bus.archives`. Always query both before concluding a result didn't arrive:
  ```bash
  # Both queries use the double-parse pattern
  sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \\\"SELECT state, (body::jsonb #>> '{}')::jsonb->>'subject', (body::jsonb #>> '{}')::jsonb->>'correlation_id' FROM bus.messages WHERE queue_name = 'inbox_moses' ORDER BY enqueued_at DESC LIMIT 3;\\\"\"
  sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \\\"SELECT archived_at::timestamptz(0), (body::jsonb #>> '{}')::jsonb->>'subject', (body::jsonb #>> '{}')::jsonb->>'correlation_id' FROM bus.archives WHERE archived_at > NOW() - INTERVAL '15 minutes' ORDER BY archived_at DESC LIMIT 5;\\\"\"
  ```

- **bus_send returns None while bus_read works** — agents can consume UPDATE_REQUESTs (bus_read succeeds) but never send back UPDATE_RESULTs (bus_send returns None). This "half-connectivity" pattern has been seen on Joseph, Gisu, and Kustos. See `references/2026-07-21-bus-send-silent-failure.md` for diagnostic steps and known root causes.

- **When ALL agents fail the same way, it's systemic, not config-specific** — on 2026-07-22, ALL 5 fleet agents consumed UPDATE_REQUESTs (bus_read + archive worked) but NONE sent back UPDATE_RESULTs. This is NOT five coincidental config failures. When the pattern is universal:
  1. The handler code path is common — check send_bus_result itself
  2. Bus infrastructure may be the issue — check if inbox_moses is accepting writes
  3. An environment variable common to all agent crons (e.g. CORTEX_BUS_URL from systemd) may be overriding the config file
  4. Test bus_send from the cron environment, not interactive shell — cron may have different $PATH, $HOME, or $CORTEX_BUS_URL

- **send_bus_result failure needs Telegram fallback** — when bus_send fails (returns None), send_bus_result currently only logs "Failed to send" and returns False. The orchestrator has NO way to know the agent successfully completed the work. Fix: the handler should also call notify_telegram() when send_bus_result fails, so the orchestrator knows via the fallback channel. This converts a silent failure into a visible alert, giving the orchestrator actionable information even when the bus is broken.

- **Schema validation requires runtime deployment** — `hc exec` and `orch-bus-fleet-dispatch.py` validate payloads against `handoff_schema.py` at runtime. If the script errors with `ImportError: No module named 'handoff_schema'`, the module hasn't been deployed. Run `cortex-update.sh` to deploy. The validation is best-effort — missing schemas are skipped with a log message, execution continues.

- **Testing bus_send from interactive shell != handler's bus_send** — multiple agents confirmed bus_send works when run manually from the command line, but the handler's bus_send returns None when run via cron. Possible root causes:
  1. Cron has different $CORTEX_DEPLOY_HOME pointing to a different config file
  2. Cron has different $CORTEX_BUS_AUTH env var overriding config
  3. Cron runs with different $HOME resolving ~/.hermes-cortex/cortex-bus.conf differently
  4. The deployed cortex_bus.py at ~/.hermes-cortex/scripts/lib/cortex_bus.py differs from the repo version
  **Diagnostic:** compare env output from cron vs interactive shell, and check diff between deployed and repo cortex_bus.py.
