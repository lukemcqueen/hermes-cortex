# Session: Bus Orchestration, Handler Fixes & Full-Cycle Testing

## Context

Session July 21, 2026. User asked to "test out the new hc messages on the bus to command agents to do something and report back." Multiple corrections followed about not completing the full round-trip, testing on own system first, and understanding bus architecture roles.

## Core Lessons

### 1. Complete the Full Cycle Before Reporting

Testing a bus command requires 6 steps, not 1:
1. Send the command
2. Verify queue delivery (state=pending)
3. Wait for consumer to process it (state=processing)
4. Check for the response/result in your inbox
5. Verify response content matches expectations
6. Archive test messages after verification

**"Message sent" is not a pass.** Reporting after step 1 will be corrected.

### 2. Test on Your Own System First

Before sending any command to a remote fleet agent, test the full cycle locally:

```bash
# Send EXEC to self
hc exec moses cortex-doctor.py --json

# Run handler manually
cd ~/.hermes-cortex && python3 scripts/agent-message-handler.py --once

# Verify response
sg docker -c 'docker exec legacy Postgres psql -U mycortex -d mycortex -c "SELECT queue_name, state FROM bus.messages;"'
```

### 3. Orchestrator vs Fleet Agent Bus Roles

- **Moses (orchestrator):** handles own inbox directly during sessions. Does NOT run `agent-message-handler` cron. Out-of-session bus processing uses `cortex-bus-workday/evening/overnight` LLM crons.
- **Fleet agents (Esther, Joseph, Gisu, Kustos, Titus):** run `agent-message-handler.py` every 5 min. The handler processes commands from Moses and sends results back.
- **Moses does not need a local handler** — the orchestrator is the handler when in session.

### 4. The Handler Is Still on Fleet Agents (with Telegram Notifications)

- `agent-message-handler.py` runs on fleet agents only
- Now sends Telegram notifications: 📥 pickup, ✅/❌ completion
- Telegram uses Bot API directly (reads token from `~/.hermes/.env`)
- Silent on success, logs on failure

## Bus Protocol Reference

### Command Subjects
| Subject | Action | Response Subject |
|---------|--------|-----------------|
| EXEC | Run script under `~/.hermes-cortex/scripts/` | EXEC_RESULT |
| UPDATE_REQUEST | `cortex-update.sh` | UPDATE_RESULT |
| ROLLBACK_REQUEST | `git checkout <sha>` then update | ROLLBACK_RESULT |
| GIT_AUTH_CHECK | `git ls-remote` verification | GIT_AUTH_RESULT |
| DIAGNOSTIC_REQUEST | Run agent-diagnostic.py | DIAGNOSTIC_RESULT |

### EXEC Message Format
```json
{
  "from": "moses",
  "to": "<agent>",
  "topic": "command",
  "subject": "EXEC",
  "correlation_id": "exec-<12-hex>",
  "body": "{\"command\": \"cortex-doctor.py\", \"params\": [\"--json\"], \"timeout\": 30}"
}
```

### Sending Commands
- `hc exec <agent> <command> [args]` — preferred, polls for EXEC_RESULT
- `hc send <agent> <subject> [body]` — fire-and-forget
- Direct `bus.send()` via psql for precise JSON

## Handler Code Changes (commit 81cf0b5)

- **Telegram notifications** added to `agent-message-handler.py` for all subject types
- **Idempotency archive fix** — handler now archives skipped messages (was leaving them in infinite processing loop)
- **Handler cron removed from Moses** — orchestrator no longer runs it locally

## How to Run On-Demand (Moses)
```bash
hc exec moses cortex-doctor.py --json
cd ~/.hermes-cortex && python3 scripts/agent-message-handler.py --once
```

## Previous Session Notes

See also the earlier July 21 session about "pull latest + fix without asking" — the fix-without-asking lesson from that session was expanded this session with the "complete the full cycle" and "test on own system first" rules.

---

## Second Half: Fleet Agent Diagnostics & Crash Guard Fix

After the first half of the session, the user wanted to test the full orchestration across fleet agents. This uncovered two distinct failure patterns.

### Pattern 1: Archive-Failure Loop (Esther)

The handler archives a message after processing, but `bus_archive()` was returning `False` silently. The handler's `archive_message()` wrapper ignored the return value. The message stayed `processing` → VT expired → re-read → idempotency skip → archive fails again → loop forever.

**Fix (commit `c306e3d`):** `archive_message()` now returns `bool` and logs `⚠️ Failed to archive message` on failure.

### Pattern 2: Poll-Once Crash (No Exception Handler)

The dispatch block in `poll_once()` had **zero exception handling**. If any of `process_update_request()`, `send_bus_result()`, or `save_state()` threw an exception, the handler crashed silently — message stuck `processing`, no log, no result returned.

**Fix (commit `df3a419`):** Wrapped the entire dispatch in `try/except`. On any exception, the handler now logs the traceback, archives the message, sends a failure result back to `inbox_moses`, and notifies via Telegram.

### Key Techniques

#### Diagnostic via Telegram (When Bus Is Broken)

When messages are stuck `processing` on a fleet agent, the bus is the broken channel — cannot send EXEC to diagnose. **Send diagnostics via Telegram instead:**

```
Run a full diagnostic and report back:
1. Check handler cron exists and is enabled
2. Read handler state file (~/.hermes-cortex/state/agent-handler-state.json)
3. Check system load / memory / disk
4. Check latest handler output log
5. Run doctor
Return everything as raw output, don't summarize.
```

**Critical: send SEPARATE messages per agent.** Intermingled instructions confuse them.

#### Bus-Level Diagnosis

| Finding | Cause | Fix |
|---------|-------|-----|
| `expired = t`, retry_count climbing | Handler crashes mid-process | Add try/except (commit `df3a419`) |
| `expired = t`, retry_count static | Handler archive fails silently | Check bus connectivity/auth; add archive logging (commit `c306e3d`) |
| DLQ with retry_count=3 | Max retries exhausted | Archive DLQ, fix root cause, re-send |

#### Force-Unstick Processing Messages

`bus.archive()` can return 0 rows on `processing` messages (CTE materialization issue). Workaround: force-recover to `pending` first, then archive.

```sql
UPDATE bus.messages
SET state = 'pending', timeout_at = NULL, retry_count = retry_count + 1
WHERE queue_name = 'inbox_target' AND state = 'processing';
```

### Agent-Specific Issues Found

| Agent | Issue | Fix |
|-------|-------|-----|
| **Kustos** | Missing `AGENT_NAME=kustos` in `cortex-bus.conf` — polled `inbox_cisnet02` instead of `inbox_kustos` | Set AGENT_NAME in config |
| **Esther** | Handler crashed mid-processing (crash pattern, not archive loop) | Push `df3a419` (try/except guard) |

### Corrections Received

- **"Reread your SOUL.md seriously?"** — When asked "I can commit and push this fix if you want" instead of just doing it. Reinforces zero-ask litmus: if you know the fix, `begin_change` is the first tool call.
- **"Next time give me separate messages."** — Sent combined diagnostic for Esther and Kustos. Each agent gets its own standalone message.
- **"You just discovered an issue. Now they need to understand what you know."** — When stuck messages were found, the correct action was to immediately send diagnostic instructions via Telegram, not wait.
- **"You are asking me?"** — When offering to commit a fix instead of just committing. Fix first, ask never.
