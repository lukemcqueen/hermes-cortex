# Bus Test Plan Framework

## Purpose

A structured framework for formulating a bus test plan by surveying the live system state FIRST, then building test scenarios from the actual configuration — not from assumptions.

## When to Use

- Preparing to test bus connectivity with a new or existing agent
- Diagnosing why a test that "should work" keeps failing
- Verifying bus functionality after a config change or deployment
- Answering "how do we test the bus?" for a fleet agent

## The Survey-First Protocol

**Never write a test command until you know the actual running state.** The bus schema, permissions, and agent registry change over time. Commands written from memory will fail.

### Step 1: Survey the Fleet

```bash
# Who are the agents, what role, what bus_access?
cat ~/.hermes-cortex/state/agent-registry.json | python3 -c "
import json,sys; reg=json.load(sys.stdin)
for k,v in reg.get('agents',{}).items():
    caps = v.get('capabilities', {})
    ba = caps.get('bus_access', '?')
    role = v.get('role', '?')
    hm = caps.get('health_method', v.get('health_method', '?'))
    print(f'  {k}: role={role} bus_access={ba} health_method={hm}')
" 2>&1
```

### Step 2: Check Bus Health

```bash
# Is the bus running at all?
curl -s http://127.0.0.1:8903/health
# Expected: {"status":"ok","backend":"pgmq","queues":NN,"timestamp":"..."}

# Can we authenticate?
TOKEN=$(grep CORTEX_BUS_TOKEN ~/hermes-cortex/.env | cut -d= -f2)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8903/health
# Expected: same as above
```

### Step 3: Check Permissions

```bash
# What queues can each agent read/write?
sg docker -c 'docker exec legacy Postgres psql -U mycortex -d mycortex -c \
"SELECT agent_name, can_read::text, can_write::text, is_admin \
FROM bus.permissions ORDER BY agent_name;"' 2>&1
```

### Step 4: Check Queue State

```bash
# Any backlog? Stuck messages? DLQ accumulation?
sg docker -c 'docker exec legacy Postgres psql -U mycortex -d mycortex -c \
"SELECT queue_name, state, COUNT(*) as count \
FROM bus.messages GROUP BY queue_name, state ORDER BY queue_name, state;"' 2>&1
```

If there are stuck `processing` messages, run recovery first:
```bash
sg docker -c 'docker exec legacy Postgres psql -U mycortex -d mycortex -c \
"SELECT bus.recover_timeouts();"' 2>&1
```

**Critical rule: clean the bus before sending test messages.** Stale messages from crashed handlers interfere with new commands.

### Step 5: Trace the Consumption Pipeline

For each agent you plan to test:

| Agent | Handler? | Poll interval | Best test method |
|-------|----------|--------------|------------------|
| Moses | In-session tools + LLM crons | Immediate/delayed | MCP tools directly |
| Esther | agent-message-handler.py | 5 min | `hc exec esther ...` |
| Joseph | agent-message-handler.py | 5 min | `hc exec joseph ...` |
| Kustos | agent-message-handler.py | 5 min | `hc exec kustos ...` |
| Gisu | agent-message-handler.py | 5 min | `hc exec gisu ...` |
| Titus | ❌ NO handler | N/A | Telegram fallback only |

### Step 6: Build the Test Plan

From the survey output, construct concrete test commands:

**Level 1 — Prove on yourself (Moses → inbox_moses):**
```bash
hc exec moses cortex-doctor.py --json
# Then manually run handler:
cd ~/.hermes-cortex && python3 scripts/agent-message-handler.py --once
```

**Level 2 — Test to host agent (Esther):**
```bash
hc exec esther cortex-doctor.py --json
# Wait ~5min for handler cycle, then check inbox_moses for EXEC_RESULT
```

**Level 3 — Test to client agents (Joseph, Kustos, Gisu):**
```bash
hc exec joseph -- df -h /
hc exec kustos -- uptime
hc exec gisu -- uname -a
```

**Level 4 — External path verification (simulate remote agent):**
```bash
TOKEN=$(grep CORTEX_BUS_TOKEN ~/hermes-cortex/.env | cut -d= -f2)
curl -s -X POST https://example.com:13004/api/pgmq/send \
  -u "bus_user:password" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"queue":"inbox_moses","message":{"from":"test","subject":"external-path-verify","body":{}}}' \
  -k
```

### Step 7: Verify Delivery

```bash
# Check target queue
sg docker -c 'docker exec legacy Postgres psql -U mycortex -d mycortex -c \
"SELECT queue_name, state, COUNT(*) FROM bus.messages \
GROUP BY queue_name, state ORDER BY queue_name, state;"' 2>&1

# Check inbox_moses for EXEC_RESULT
sg docker -c 'docker exec legacy Postgres psql -U mycortex -d mycortex -c \
"SELECT body->>'\''subject'\'' as subject, body->>'\''from'\'' as sender, \
body->>'\''correlation_id'\'' as corr_id, state, enqueued_at::timestamptz(0) \
FROM bus.messages WHERE queue_name = '\''inbox_moses'\'' AND state = '\''pending'\'' \
ORDER BY enqueued_at DESC LIMIT 10;"' 2>&1

# Check audit log
sg docker -c 'docker exec legacy Postgres psql -U mycortex -d mycortex -c \
"SELECT action, agent_name, queue, COUNT(*) as cnt \
FROM bus.audit_log WHERE created_at > NOW() - INTERVAL '\''10 minutes'\'' \
GROUP BY action, agent_name, queue ORDER BY queue, action;"' 2>&1
```

### Step 8: Cleanup

Archive test messages to prevent DLQ cycling:
```bash
sg docker -c 'docker exec legacy Postgres psql -U mycortex -d mycortex -c \
"SELECT bus.archive('\''inbox_moses'\'', '\''<msg_id>'\''::uuid, '\''test-cleanup'\'');"' 2>&1
```

## 6-Checkpoint Verification (Hard Gate)

A bus test is NOT complete until ALL 6 pass:

1. **Send** — message in target queue (pending, correct subject/correlation_id)
2. **Consume** — transitions pending → processing → archived
3. **Process** — command output in handler logs
4. **Respond** — EXEC_RESULT in inbox_moses with matching correlation_id
5. **Read** — orchestrator can query inbox and extract structured result
6. **Inbox-verify** — independently confirm by querying inbox_moses BEFORE reporting

Missing any one checkpoint means the test is incomplete.

## Pitfalls

- ❌ **Testing with `hc send` (docker exec SQL)** — bypasses ALL auth and permission checks. Not representative of agent-facing behavior.
- ❌ **Proving on a fleet agent before proving on yourself** — the most expensive mistake. Always prove on inbox_moses first.
- ❌ **Skipping the cleanup step** — test messages that stay in the queue get picked up by the next handler cycle and can confuse diagnostics.
- ❌ **Assuming Titus processes bus messages** — Titus is push-only (health_method=inbox), no handler cron. Use Telegram for Titus commands.
- ❌ **One message for multiple agents** — each agent gets its OWN test message. Intermingling instructions for multiple agents produces no useful results.
