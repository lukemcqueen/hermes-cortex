# Agent Message Handler Protocol

> How `agent-message-handler.py` processes bus commands on fleet agents (Esther, Joseph, Gisu, Kustos).

## Architecture

```
Orchestrator (Moses)              Fleet Agent (Esther, Joseph, Gisu...)
         │                                    │
  hc exec esther                               │
  → bus.send(inbox_esther, EXEC)               │
         │                                    │
         └──────────── bus ────────────────────┤
                                                │
                                        agent-message-handler.py (*/5 * * * *)
                                        → bus_read(inbox_esther, vt=30)
                                        → parse subject + body
                                        → dispatch to handler
                                        → execute subprocess (no_agent)
                                        → bus.send(inbox_moses, EXEC_RESULT)
```

## Orchestrator split (Moses)

**Moses does NOT run `agent-message-handler.py`.** Previously it did, causing:
- Skill reports stacking as backlog — handler only processes 1 msg/tick
- EXEC commands waiting 40+ min behind backlog
- Infinite loop on idempotency skip (FIXED: now archives on skip)

Moses handles its inbox **in-session** (MCP tools + hc CLI) and **out-of-session** (`cortex-bus-workday/evening/overnight` LLM crons).

## Telegram notifications

On each message consumed, the handler sends to Luke's Telegram DM:
1. **📥 [agent] Received EXEC from moses** — on pickup
2. **✅/❌ [agent] EXEC script.py: exit=N — preview** — after execution

Direct Bot API: reads `TELEGRAM_BOT_TOKEN` + `TELEGRAM_HOME_CHANNEL` from `~/.hermes/.env` (recipient never hardcoded — PII scrub 2026-08-06), with `timeout=10`. Uses `urllib.request` — no `requests` dependency.

## Idempotency

Tracks processed `correlation_id` values in `agent-message-state.json` (`processed_ids` list). On each tick:
1. Read message (vt=30)
2. Send 📥 Telegram notification
3. Check if `correlation_id` in `processed` set
4. If yes → **archive and skip** (FIXED 2026-07-21 — was leaving messages in processing loop)
5. If no → dispatch → archive → send EXEC_RESULT → send ✅/❌ Telegram

**correlation_id must be unique and non-empty.** Messages without one get caught if `""` is in the processed set.

## Message schemas

| Subject | Body | Response |
|---------|------|----------|
| `EXEC` | `{command, params[], timeout}` | `EXEC_RESULT: {success, stdout, stderr, exit_code}` |
| `UPDATE_REQUEST` | `{target_sha, target_version, run_doctor}` | `UPDATE_RESULT: {success, errors[], git_sha_before, git_sha_after}` |
| `ROLLBACK_REQUEST` | `{target_sha, reason}` | `ROLLBACK_RESULT: {success, errors[], rolled_back_to}` |
| `GIT_AUTH_CHECK` | `{expected_url}` | `GIT_AUTH_RESULT: {success, can_access}` |
| `DIAGNOSTIC_REQUEST` | `{check, respond_to_queue}` | `DIAGNOSTIC_RESULT: {results[]}` |
