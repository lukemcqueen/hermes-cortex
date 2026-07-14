# Agent Bus — Hermes Cortex Message Queue on Postgres + Workflow Engine

> **Direct replacement for the file-based agent inbox.**  
> Postgres-native message queue + deterministic workflow engine.  
> SLA enforcement, human-in-the-loop gates, full auditability, zero LLM cost for routing.

---

## Architecture Overview

```
                    ┌──────────────────────────────┐
                    │      nginx (:13004)          │
                    │  mTLS + Bearer Auth + Rate Limit + fail2ban
                    └──────────────┬───────────────┘
                                   │ proxy to localhost:8905
                    ┌──────────────▼───────────────┐
                    │    Agent Bus Server (:8905)   │
                    │    FastAPI + PGMQ Backend     │
                    │                               │
                    │  /api/pgmq/*  — REST API      │
                    │  /api/bus/dashboard — JSON    │
                    │  /health       — health check │
                    │  /             — HTML dashboard│
                    │  /.well-known/agent-card.json │
                    └──────────────┬───────────────┘
                                   │ localhost:15432
                    ┌──────────────▼───────────────┐
                    │    gbrain Postgres (:15432)   │
                    │    bus schema (no extensions!)│
                    │                               │
                    │  bus.queues      — queue meta  │
                    │  bus.messages    — messages    │
                    │  bus.archives    — audit trail │
                    │  bus.permissions — ACL         │
                    │  bus.tokens      — auth        │
                    │  bus.audit_log   — operations  │
                    └───────────────────────────────┘
```

### Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Queue implementation | Custom SQL (SKIP LOCKED) on Postgres | No external extensions needed. Full control. PGMQ compiled extension not available for PG 17. |
| Who has PG creds | Only the inbox server (Moses/Esther) | Worker agents connect via HTTP. No Postgres credentials on laptops or shared VPS. |
| Worker agent changes | Zero | Same MCP tools (`inbox_mcp.py`), same HTTP path. Server swaps the backend. |
| Transport security | mTLS + Bearer tokens + TLS 1.3 | Four-layer defense (see Security below). |
| Migration | Greenfield on separate port (8905) | New bus alongside old inbox (8903). Cutover is a single nginx change. |
| Fallback | Auto-degrade to file backend (circuit breaker) | Old inbox stays running as fallback. Auto-restore when Postgres recovers. |

---

## Security Model (Four Layers)

```
Layer 4: Permissions ── "agent esther can only read queue inbox_esther"
Layer 3: Bearer tokens ── "this request is from agent esther"
Layer 2: nginx ── TLS 1.3 + fail2ban + rate limiting (30r/m)
Layer 1: mTLS ── "this machine has a valid client certificate"
```

| Attack | What Happens |
|--------|-------------|
| Internet scanner (no TLS client cert) | Rejected at TLS handshake. Never reaches nginx. |
| Brute force token guessing | fail2ban bans IP after 3 failures in 5 minutes. 24h ban. |
| Compromised agent token | Revoke single token, re-issue. Other agents unaffected. |
| Stolen laptop (Titus) | No Postgres credentials on laptop. Token can be revoked. |
| Rate limit exceeded | HTTP 429 after 30 requests/minute. |

---

## Setup: Orchestrator vs Regular Agent

### Orchestrator (Moses / Esther)

Full setup — runs the bus service + Postgres schema:

```bash
# 1. Install the bus (Postgres schema, tokens, systemd service)
bash ~/hermes-cortex/ops/scripts/install/install-bus.sh

# 2. Copy MCP server to Hermes scripts
cp ~/hermes-cortex/runtime/mcp-servers/agent-bus-mcp.py ~/.hermes/scripts/

# 3. Deploy nginx config (add to /etc/nginx/sites-available/hermes-services.conf)
#    Template: ~/hermes-cortex/ops/services/agent-bus/nginx.conf

# 4. Register orchestrator-only crons
bash ~/hermes-cortex/ops/scripts/install/install-orch-crons.sh
```

| File | Purpose |
|------|---------|
| `ops/services/agent-bus/server.py` | Bus service (FastAPI, port 8905) |
| `runtime/agent_bus/queue.py` | PGMQ queue client |
| `ops/services/agent-bus/schema/queue.sql` | PGMQ schema |
| `ops/services/agent-bus/schema/auth.sql` | Token/permissions schema |
| `ops/services/agent-bus/schema/workflow.sql` | Workflow + A2A schema |
| `runtime/mcp-servers/agent-bus-mcp.py` | MCP tool server |
| `ops/scripts/inbox/workflow-*.py` | Workflow cron scripts |
| `ops/services/agent-bus/nginx.conf` | nginx template |

### Regular Agent (Joseph, Gisu, Kustos, Titus)

Lightweight setup — MCP client only, no bus service:

```bash
# 1. Copy MCP server
cp ~/hermes-cortex/runtime/mcp-servers/agent-bus-mcp.py ~/.hermes/scripts/

# 2. Add to ~/.hermes/config.yaml:
#    mcp_servers:
#      agent-bus:
#        command: python3
#        args: [~/hermes-cortex/runtime/mcp-servers/agent-bus-mcp.py]
#        enabled: true

# 3. Create ~/.hermes-cortex/hermes-inbox.conf:
#    CORTEX_BUS_URL=https://moses-server:13004
#    CORTEX_BUS_TOKEN=hbus_your_agent_token_here
#    CORTEX_BASIC_AUTH=username:password  (nginx Basic auth)
#    CORTEX_INBOX_URL=...  (optional fallback)
#    AGENT_NAME=<your-name>
```

| File | Purpose |
|------|---------|
| `runtime/mcp-servers/agent-bus-mcp.py` | MCP tool server (only file needed) |
| `~/.hermes-cortex/hermes-inbox.conf` | Bus URL + token config (see below) |

### `~/.hermes-cortex/hermes-inbox.conf` reference

Simple key=value file — one per line, `#` comments supported:

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `CORTEX_BUS_URL` | ✅ Yes | — | Bus server URL (e.g. `https://domain:13004` or `http://127.0.0.1:8905`) |
| `CORTEX_BUS_TOKEN` | ✅ Yes | — | Bearer token (`hbus_...`) generated by `issue-agent-token.py` |
| `AGENT_NAME` | ✅ Yes | `$USER` | Your agent's name (must match token, e.g. `esther`) |
| `CORTEX_INBOX_URL` | ❌ No | — | Fallback old inbox URL (e.g. `http://127.0.0.1:8903`) |
| `CORTEX_BASIC_AUTH` | ✅ Yes | — | Basic auth for nginx `user:password` — used for external bus connections |
| `CORTEX_INBOX_AUTH` | ❌ No | — | Old name (deprecated, use `CORTEX_BASIC_AUTH` instead) |
| `MOSES_INBOX_URL` | ❌ No | — | Old env var name (deprecated, use `CORTEX_INBOX_URL`) |
| `MOSES_INBOX_AUTH` | ❌ No | — | Old env var name (deprecated, use `CORTEX_INBOX_AUTH`) |

**Precedence:** Environment variables > `hermes-inbox.conf`. This means you can override the bus URL per-session without editing the config file.
| `~/.hermes/config.yaml` | MCP server registration |

**What a regular agent does NOT need:** Postgres, docker, bus systemd service, nginx, workflow cron scripts, auth.sql/queue.sql/workflow.sql, the circuit breaker, or any file in `ops/scripts/inbox/`.

### Cross-Platform Support

| Platform | Bus Service | MCP Tools |
|----------|------------|-----------|
| **Linux** (server) | ✅ systemd `hermes-agent-bus.service` | ✅ Python (any venv) |
| **macOS** | ✅ launchd (Postgres via Docker Desktop, bus via launchd `.plist`) | ✅ Python (any venv) |

The bus is Python (cross-platform). Postgres runs in Docker (cross-platform). The only OS-specific piece is the service manager — systemd on Linux, launchd on macOS. To run on macOS:

```bash
# Postgres via Docker Desktop
docker run -d --name gbrain-postgres -p 15432:5432 ...

# Bus via launchd
# Create ~/Library/LaunchAgents/com.hermes.agent-bus.plist
# with: python3 -m uvicorn agent_bus.server:app --host 127.0.0.1 --port 8905
# WorkingDirectory: ~/.hermes-cortex/bus/
```

---

## Queues

Every fleet agent has two queues:

| Queue | Purpose |
|-------|---------|
| `inbox_{agent}` | Agent's message inbox |
| `inbox_{agent}_dlq` | Dead letter queue (messages that failed 3+ times) |

Additionally, workflow queues:

| Queue | Purpose |
|-------|---------|
| `workflow_dispatch` | New workflow instances to start |
| `workflow_step_result` | Completed workflow steps (for routing) |
| `workflow_timeout` | Timed-out workflow steps |
| `inbox_health_check` | Used by the e2e health check cron |

### Queue Properties

- **Priority ordering:** Messages with higher `priority` values are dequeued first
- **FIFO within priority:** Messages at the same priority level are dequeued in order
- **Visibility timeout:** After reading, a message is invisible for N seconds. If not archived in time, it reappears (automatic retry).
- **Dead letter:** After 3 failed deliveries (retries), the message moves to the DLQ.
- **Auto-create:** Queues are auto-created on first `send()` to a new queue name.

---

## REST API

All endpoints except `/health` and `/.well-known/agent-card.json` require:
- **mTLS client certificate** (nginx level)
- **Bearer token** in `Authorization: Bearer <token>` header

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/pgmq/send` | Bearer | Send a message to a queue |
| `POST` | `/api/pgmq/read` | Bearer | Read (dequeue) a message |
| `POST` | `/api/pgmq/archive` | Bearer | Archive a processed message |
| `POST` | `/api/pgmq/requeue` | Bearer | Re-queue a failed message |
| `DELETE` | `/api/pgmq/delete` | Bearer | Delete a message |
| `GET` | `/api/pgmq/depth/{queue}` | Bearer | Queue depth |
| `GET` | `/api/pgmq/queues` | Bearer | List all queues |
| `GET` | `/api/pgmq/queue/{name}` | Bearer | Queue details |
| `GET` | `/api/bus/dashboard` | Bearer | JSON dashboard data |
| `GET` | `/health` | None | Health check |
|| `GET` | `/` | Bearer | HTML dashboard with queue + workflow views |
|| `GET` | `/.well-known/agent-card.json` | None | A2A discovery |
|| `POST` | `/a2a/task` | Bearer | Create an A2A task |
|| `GET` | `/a2a/task/{id}` | Bearer | Get A2A task status |
|| `POST` | `/a2a/task/{id}/cancel` | Bearer | Cancel an A2A task |
|| `GET` | `/a2a/agent-card` | Bearer | Bus agent card (capabilities) |
|| `GET` | `/a2a/agents` | Bearer | List all fleet agents |
|| `GET` | `/a2a/agent/{name}` | Bearer | Get agent details |
|| `POST` | `/api/workflows/dispatch` | Bearer | Dispatch a new workflow |
|| `GET` | `/api/workflows` | Bearer | List active workflows |
|| `GET` | `/api/workflows/{id}` | Bearer | Workflow details with steps |
|| `GET` | `/api/workflows/hil` | Bearer | List steps awaiting human review |
|| `POST` | `/api/workflows/hil` | Bearer | Respond to HIL (approve/reject/request_changes) |

### Send Example

```bash
curl -sk --cert agent-cert.pem --key agent-key.pem \
  -H "Authorization: Bearer hbus_<token>" \
  -H "Content-Type: application/json" \
  -X POST -d '{
    "queue": "inbox_moses",
    "message": {"from": "esther", "subject": "report", "body": "All systems OK"},
    "priority": 0,
    "correlation_id": "wf-001"
  }' \
  https://bus.example.org:13004/api/pgmq/send
```

### Read Example

```bash
curl -sk --cert agent-cert.pem --key agent-key.pem \
  -H "Authorization: Bearer hbus_<token>" \
  -H "Content-Type: application/json" \
  -X POST -d '{"queue": "inbox_moses", "vt": 60}' \
  https://bus.example.org:13004/api/pgmq/read
```

Returns:
```json
{
  "msg_id": "uuid",
  "queue": "inbox_moses",
  "body": {"from": "esther", "subject": "report"},
  "priority": 0,
  "retry_count": 0,
  "max_retries": 3,
  "correlation_id": "wf-001",
  "from_dlq": false,
  "enqueued_at": "2026-07-14T10:00:00Z",
  "timeout_at": "2026-07-14T10:01:00Z"
}
```

### Archive Example

```bash
curl -sk --cert agent-cert.pem --key agent-key.pem \
  -H "Authorization: Bearer hbus_<token>" \
  -H "Content-Type: application/json" \
  -X POST -d '{"queue": "inbox_moses", "msg_id": "<uuid>"}' \
  https://bus.example.org:13004/api/pgmq/archive
```

---

## Python Client

### Installation (server only — Moses/Esther)

```bash
pip install psycopg[binary]
```

### Usage

```python
from agent_bus.queue import get_queue

bus = get_queue()

# Send
msg_id = bus.send("inbox_moses", {"from": "test", "body": "hello"})

# Read
msg = bus.read("inbox_moses", vt=60)
if msg:
    print(f"Got: {msg['body']}")
    bus.archive("inbox_moses", msg["msg_id"])

# Queue depth
depth = bus.depth("inbox_moses")

# List all queues
queues = bus.list_queues()
```

---

## Workflow Engine

The Agent Bus includes a **durable workflow engine** for deterministic agent orchestration.

### How it works

```
           ┌────────────────────┐
           │  workflow_dispatch │  (queue)
           └────────┬───────────┘
                    ▼
        ┌───────────────────────┐
        │     Dispatcher        │  (cron: every 1 min)
        │  • Loads YAML        │
        │  • Snapshots defn    │
        │  • Creates PG rows   │
        │  • Sends step to     │
        │    agent's inbox     │
        └────────┬──────────────┘
                    │ step completes
                    ▼
        ┌───────────────────────┐
        │       Router          │  (cron: every 1 min)
        │  • Evaluates route_if │
        │  • Case-insensitive   │
        │  • _fallback support  │
        │  • Dispatches next    │
        │    step or ends WF    │
        └───────────────────────┘
```

**Key properties:**
- **YAML is snapshotted at dispatch** — never re-read for in-flight routing
- **`route_if`** — deterministic, case-insensitive, `_fallback` key supported
- **Zero LLM cost for routing** — pure string matching
- **SLA enforcement** — watchdog marks timed-out workflows/steps every 5 min
- **Human-in-the-loop** — steps with `human_review: true` wait for approve/reject
- **Postgres state** — workflows, steps, audit log all in `bus.agent_workflows*` tables

### Example YAML

```yaml
name: research-then-write
version: 1.0.0
start_step: research
deadline_seconds: 3600
steps:
  - name: research
    assigned_to: gisu
    prompt: "Research: {{topic}}"
    timeout_seconds: 600
    route_if:
      success: write_report
      _fallback: _fail
  - name: write_report
    assigned_to: joseph
    timeout_seconds: 900
    route_if:
      success: _end
      _fallback: _fail
```

**Routing rules:**
- `success: next_step` — route to a specific step name
- `_fallback: next_step` — catch-all if no key matches
- `_end` — terminate workflow successfully
- `_end:reason` — terminate with a specific outcome

### Workflow Dispatch (from any agent)

```bash
curl -sk -H "Authorization: Bearer ***" \
  -H "Content-Type: application/json" \
  -X POST -d '{
    "workflow_name": "my-workflow",
    "workflow_source": "yaml:name: my-workflow\n...",
    "payload": {"key": "value"},
    "priority": 5
  }' \
  https://bus.example.org:13004/api/workflows/dispatch
```

Or via file path:

```bash
curl -sk -H "Authorization: Bearer ***" \
  -H "Content-Type: application/json" \
  -X POST -d '{
    "workflow_name": "research-then-write",
    "workflow_source": "/home/moses/hermes-cortex/runtime/agent_bus/workflows/research-then-write.yaml",
    "payload": {"topic": "Postgres SKIP LOCKED"}
  }' \
  https://bus.example.org:13004/api/workflows/dispatch
```

### Human-in-the-Loop

When a step has `human_review: true`, the workflow pauses (state: `blocked`)
and sends a notification to `inbox_luke`. The dashboard shows pending reviews.
Respond via:

```bash
curl -sk -H "Authorization: Bearer ***" \
  -H "Content-Type: application/json" \
  -X POST -d '{
    "workflow_id": "<uuid>",
    "step_id": "<uuid>",
    "decision": "approve",
    "feedback": "Looks good, proceed"
  }' \
  https://bus.example.org:13004/api/workflows/hil
```

Decisions: `approve`, `reject`, `request_changes`.

### Pre-built Workflow YAMLs

| File | Description |
|------|-------------|
| `runtime/agent_bus/workflows/research-then-write.yaml` | Research topic → write report |
| `runtime/agent_bus/workflows/fix-issue.yaml` | Reproduce → fix → PR, with HIL escalation |
| `runtime/agent_bus/workflows/investigate-and-fix.yaml` | Investigate → fix → verify → rollback |


---

## Circuit Breaker

The bus has an automatic circuit breaker that handles Postgres outages:

- **State: `pgmq`** — normal operation (Postgres is healthy)
- **State: `file`** — degraded mode (Postgres is down, using old inbox)

**How it works:**
1. When a PGMQ operation fails, `record_failure()` is called
2. After 3 consecutive failures, the breaker trips to `file` mode
3. In file mode, all requests return HTTP 503 with `backend: file`
4. The health check periodically calls `check_and_restore()`
5. When Postgres recovers, the breaker auto-restores to `pgmq` mode

State is persisted to `~/.hermes-cortex/bus-circuit-breaker.json`.

---

## Cron Jobs

| Cron | Type | Schedule | Purpose |
|------|------|----------|---------|
| `bus-health-check` | no_agent | Every 5 min | End-to-end test: send → read → archive. Reports RTT latency. |
| `bus-inbox-watch` | no_agent | Every 10 min | Reports pending messages in agent queues. Silent when empty. |
| `workflow-dispatcher` | no_agent | Every 1 min | Poll `workflow_dispatch` queue, create workflow + step rows, send first step |
| `workflow-router` | no_agent | Every 1 min | Poll `workflow_step_result` queue, evaluate `route_if`, dispatch next step |
| `workflow-sla-watchdog` | no_agent | Every 5 min | Check timed-out workflows/steps, monitor DLQ depths. Silent when all clear. |

---

## Setup

### Prerequisites

- Postgres running on port 15432 (gbrain container)
- Hermes Agent venv with psycopg installed
- nginx installed (for mTLS proxy)

### Quick Install

```bash
# Run on orchestrator (Moses) only
bash ~/hermes-cortex/ops/scripts/install/install-bus.sh
```

### Manual Steps After Install

```bash
# 1. Start the bus server
systemctl --user enable --now hermes-agent-bus

# 2. Verify it's running
curl -s http://127.0.0.1:8905/health

# 3. Configure nginx for mTLS (see agent-bus-nginx.conf)
# Add bus server block to /etc/nginx/sites-enabled/hermes-services.conf
# Point port 13004 to localhost:8905

# 4. Reload nginx
sudo nginx -t && sudo systemctl reload nginx

# 5. Verify external access
curl -sk --cert agent-cert.pem --key agent-key.pem \
  -H "Authorization: Bearer <token>" \
  https://your-domain.com:13004/api/pgmq/queues
```

---

## Migration Guide: Old Inbox → Agent Bus

The `agent-bus-mcp.py` MCP tool now uses the Agent Bus as its **primary backend**.

### Config Changes (update `~/.hermes-cortex/hermes-inbox.conf`)

|```bash
# New (Agent Bus — preferred):
CORTEX_BUS_URL=https://bus.example.org:13004
CORTEX_BUS_TOKEN=hbus_your_token_here
CORTEX_BASIC_AUTH=user:pass   (nginx Basic auth — required for external connections)
AGENT_NAME=moses

# Old — deprecated:
CORTEX_INBOX_URL=https://old-inbox.example.com     # was primary, now fallback
CORTEX_INBOX_AUTH=user:pass   # old name, use CORTEX_BASIC_AUTH instead
```

### What Changed

| Function | Old Backend | New Backend |
|----------|-------------|-------------|
| `inbox_send` | POST to `/send` (file inbox) | POST to `/api/pgmq/send` (PGMQ queue) |
| `inbox_read` | GET `/api/inbox` (file list) | POST `/api/pgmq/read` (dequeue) |
| `inbox_delete` | DELETE `/api/delete/{name}` | POST `/api/pgmq/archive` (UUID-based) |
| `inbox_list_agents` | File-based registry | Bus `/a2a/agents` API |
| A2A task operations | SQLite in old inbox server | Postgres `a2a_tasks` table via bus |

**Zero agent disruption** — same MCP tool names, same input schemas. All migration is behind the interface.

### Stale Files Cleaned Up

| Removed | Reason |
|---------|--------|
| `~/.hermes/scripts/inbox-mcp.sh` | Old shell wrapper, replaced by `.py` |
| `~/.hermes/scripts/inbox-mcp-updated.py` | Old version, merged into main `agent-bus-mcp.py` |

### Stale Services Kept as Fallback

| Service | Why Kept |
|---------|----------|
| `hermes-agent-inbox.service` (port 8903) | Fallback in URL chain |
| `a2a-server` (port 8906) | Fallback for A2A tasks |
| `inbox-flag.py`, `inbox-sensor.py` crons | Still poll old inbox for stats |

## nginx Configuration

The Agent Bus is proxied through nginx on port **13004** with the following setup (from the running config at `/etc/nginx/sites-available/hermes-services.conf`):

| Setting | Value |
|---------|-------|
| SSL | Let's Encrypt (TLS 1.2 + 1.3) |
| Auth | `auth_basic "Agent Bus"` with htpasswd |
| Upstream | `agent_inbox_backend` → `127.0.0.1:8905` |
| Rate limit | 20 req/s, burst 40 |
| Body size | 50 MB max |
| Public exceptions | None — the bus is fully auth'd at the nginx level |

The nginx config has **no separate A2A location blocks**. All paths (`/api/pgmq/*`, `/a2a/*`, `/.well-known/*`, `/`) go through a single `location /` which proxies to the bus. The `Authorization` header is forwarded so the bus can enforce Bearer token auth on specific endpoints.

### Auth flow

```
External agent → nginx :13004 → auth_basic (htpasswd) → bus :8905 → Bearer token
```

Two layers: `auth_basic` at nginx (server-level), Bearer tokens at the bus (per-queue granularity). MCP tools bypass nginx entirely — they talk to `localhost:8905` directly with Bearer tokens.

### Public agent card (optional)

To enable A2A discovery without auth, add a `location = /.well-known/agent-card.json` with `auth_basic off` before `location /`. The `deploy/nginx/agent-bus-nginx.conf` template has this pre-defined but commented out.

---

|| Path | Purpose |
||------|---------|
|| `src/agent_bus/queue.sql` | Postgres schema | *Moved to `ops/services/agent-bus/schema/queue.sql`* |
|| `src/agent_bus/auth.sql` | Postgres schema | *Moved to `ops/services/agent-bus/schema/auth.sql`* |
|| `ops/services/agent-bus/schema/workflow.sql` | Workflow engine + A2A schema | |
|| `runtime/agent_bus/queue.py` | Python `BusClient` for queue operations | |
|| `runtime/agent_bus/server.py` | FastAPI server (port 8905) | |
|| `runtime/agent_bus/auth.py` | Bearer token validation | |
|| `runtime/agent_bus/circuit_breaker.py` | Auto-fallback to file backend | |
|| `runtime/agent_bus/workflow/__init__.py` | Workflow models (Workflow, WorkflowStep, RouteIf) | |
|| `runtime/agent_bus/workflow/yaml_loader.py` | YAML parser + DAG validator (`yaml.safe_load`) | |
|| `runtime/agent_bus/workflow/db.py` | Postgres CRUD: workflows, steps, audit, A2A tasks | |
|| `runtime/agent_bus/workflow/dispatcher.py` | Dispatch engine: queue → workflow rows → step dispatch | |
|| `runtime/agent_bus/workflow/router.py` | Route evaluator: `route_if` matching + next step dispatch | |
|| `runtime/agent_bus/workflow/sla_watchdog.py` | Timeout detection, retry/DLQ, DLQ depth monitor | |
|| `runtime/agent_bus/workflow/human_gate.py` | Human-in-the-loop: approve/reject/request_changes | |
|| `runtime/agent_bus/workflows/*.yaml` | Example workflow definitions (3 pre-built) | |
|| `ops/services/agent-bus/server.py` | Bus server (service source) | |
|| `ops/scripts/inbox/bus-health-check.py` | E2E health check cron | |
|| `ops/scripts/inbox/bus-inbox-watch.py` | Inbox watch cron | |
|| `ops/scripts/inbox/workflow-dispatcher.py` | Workflow dispatch cron | |
|| `ops/scripts/inbox/workflow-router.py` | Workflow route cron | |
|| `ops/scripts/inbox/workflow-sla-watchdog.py` | Workflow SLA watchdog cron | |
|| `ops/scripts/inbox/test-bus.py` | Integration test suite (50 tests) | |
|| `runtime/agent_bus/scripts/issue-agent-token.py` | Token generation CLI | |
|| `deploy/nginx/agent-bus-nginx.conf` | nginx mTLS + TLS 1.3 config template | |
|| `ops/scripts/install/install-bus.sh` | Complete setup script | |
