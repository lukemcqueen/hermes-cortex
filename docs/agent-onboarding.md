# Agent Onboarding — Connecting a Client-Only Agent to the Fleet

> **For agents like Titus, running on a machine with no public server.**
> You connect to Moses's Agent Bus remotely **via the HTTP client only**.
>
> ⚠️ **You do NOT install the bus MCP client.** The `cortex-bus` MCP server
> (`inbox_send`/`inbox_read` tools) is **orchestrator-only** (Moses, Esther) —
> the doctor WARNS if you add it to `config.yaml`. Your only bus access is the
> HTTP client: `~/.hermes-cortex/cortex-bus.conf` + `contact-orchestrator.sh`.

---

## Architecture in One Picture

```
YOU (laptop / local machine)              MOSES (server)
─────────────────────────────             ──────────────
Hermes Agent                             Hermes gateway (:8905)
  ↳ cortex-bus.conf (HTTP client)              ↳ Agent Bus API (PGMQ message store)
  ↳ contact-orchestrator.sh / lib.cortex_bus          ↳ nginx proxy :13004 → :8905
  ↳ calls Moses's Agent Bus via HTTPS      ↳ SSL + Basic Auth
  ↳ NO cortex-bus MCP server in config.yaml
```

**You run the HTTP client. Moses runs the server (Agent Bus). That's it.**

---

## What You Need Before Starting

- **Hermes Agent** installed and working
- **hermes-cortex repo** cloned: `git clone https://github.com/fleet-operator/hermes-cortex.git ~/hermes-cortex`
- **A Telegram chat** (or another delivery channel) where your cron output can land

---

## Step 1 — Get Your Credentials from Moses

Contact Moses (or have the human ask him) with subject:

```
🔧 ONBOARD: titus
```

Once you have credentials in place you can use `contact-orchestrator.sh`, but for the
first contact use your human or the bus URL/curl directly (see
`docs/contact-protocol-how-to-reach-orchestrator.md`).

Moses will:
1. Create an htpasswd entry for you on the nginx gateway
2. Give you your **inbox username** and **inbox password** (the Agent Bus uses the same credentials)
3. Confirm the Agent Bus URL (typically `https://example.com:13004`)

> ⚠ **Do not share credentials.** Every agent has their own username/password.

---

## Step 2 — Do NOT Install the MCP Client

The `cortex-bus` MCP server is **orchestrator-only**. As a client-only agent
you must NOT add it to `~/.hermes/config.yaml`:

```bash
grep -A4 "cortex-bus" ~/.hermes/config.yaml
# Expected: NO output — you should NOT have an cortex-bus MCP entry.
# If you see one, remove it: the doctor WARNS about it on worker hosts.
```

Your bus access is the **HTTP client** instead — `cortex-bus.conf` (Step 3)
plus `contact-orchestrator.sh`. This is what the `agent-message-handler` cron uses
to receive fleet updates, and what you use to message the orchestrator.

---

## Step 3 — Create Your Bus Config (HTTP client)

Create `~/.hermes-cortex/cortex-bus.conf`:

```ini
CORTEX_BUS_URL="https://example.com:13004"
CORTEX_BASIC_AUTH="titus:your-password-here"
AGENT_NAME="titus"
```

Then lock it down:

```bash
chmod 600 ~/.hermes-cortex/cortex-bus.conf
```

> The HTTP client (`contact-orchestrator.sh`, `lib.cortex_bus`, `agent-message-handler`)
> reads this file. Keep it safe — this is your identity on the fleet.
>
> **Escalation path:** the HTTP client targets `inbox_orchestrator` (the
> **shared orchestrator inbox**) by default — visible to **whichever
> orchestrator is available** (Moses, or Esther during failover). Only set
> `CORTEX_INBOX_TARGET=inbox_<agent>` for point-to-point replies to a
> specific orchestrator. Both Moses and Esther read the shared
> `inbox_orchestrator` queue.

---

## Step 4 — Verify You Can Reach the Agent Bus

```bash
curl -s -u "titus:your-password-here" \
  https://example.com:13004/api/pgmq/depth/inbox_titus
```

**Expected:** `{"depth": N}` — your queue depth (may be 0 — that's fine).
**If you get 401/403:** your credentials are wrong — ask Moses to regenerate.
**If you get connection refused:** either the URL is wrong or Moses's nginx is down.

---

## Step 5 — Inbox Polling (via agent-message-handler, not MCP)

The MCP client gives you **tools** to read messages — but you don't have the
MCP client (Step 2). Instead, the `agent-message-handler` no_agent cron polls
your inbox every 5 minutes, processes fleet commands (UPDATE_REQUEST etc.), and
replies via the HTTP client. This is installed by default — verify:

```bash
cronjob action=list   # or: hermes cron list
# Expected: agent-message-handler running every 5 min
```

If it's missing, create it:

```bash
cronjob action=create schedule="*/5 * * * *" \
  name="agent-message-handler" \
  script=agent-message-handler.py \
  no_agent=true \
  deliver=local
```

> ⚠ Do NOT create a cron named `process-mcp-agent-inbox-messages` or any cron
> that calls `inbox-watch`/`inbox_read` MCP tools — those are orchestrator-only
> and will fail without the MCP client. See **`docs/bus-architecture.md`** for
> the role matrix (canonical "who has what").

---

## Step 5b — Set Up Metrics Push to VictoriaMetrics (Optional but Recommended)

Once you have bus connectivity and a poll cron running, the next most valuable
thing is pushing system metrics to the central monitoring stack. This lets Moses
(and you) see your agent's health, resource usage, and activity on Grafana
dashboards without depending on bus message delivery.

> **🪪 Scope:** This section has two audiences:
> - **General agents** — the `push-metrics.sh` script and `hermes cron create`
>   pattern works for any VictoriaMetrics endpoint. Replace the URL with yours.
> - **Luke's deployment** — sections marked `⚡` reference the Moses fleet's
>   central VictoriaMetrics server. Everything unmarked is universal.

### What you get

After setup, your agent pushes these metrics every 5 minutes:

| Metric | Example value | What it measures |
|--------|---------------|------------------|
| `node_cpu_usage_percent{agent="titus"}` | 23.5 | CPU usage snapshot |
| `node_memory_used_percent{agent="titus"}` | 62.1 | RAM usage percentage |
| `node_disk_used_percent{agent="titus"}` | 45 | Root disk usage |
| `node_uptime_seconds{agent="titus"}` | 604800 | System uptime |

### Option A: Bash (simple, no Python deps)

The repo ships a standalone bash script at
`~/hermes-cortex/ops/scripts/manage/push-metrics.sh` that collects system
metrics and POSTs them in Prometheus text format.

Set it up as a `no_agent` cron (zero LLM token cost):

```bash
# Copy the script to the cron runtime directory
cp ~/hermes-cortex/ops/scripts/manage/push-metrics.sh ~/.hermes/scripts/

# ⚡ Create the cron (replace URL with your VictoriaMetrics server)
VICTORIA_URL="http://your-central-server:8428/api/v1/import/prometheus"

hermes cron create --name agent-push-metrics \
  --schedule "every 5m" \
  --no-agent \
  --script push-metrics.sh \
  --deliver local
```

> ⚡ **For Luke's fleet (Moses server):** The central VictoriaMetrics runs on
> Moses's machine at `http://<moses-ip>:8428`. Run the cron with:
> ```
> VICTORIA_METRICS_URL="http://<moses-ip>:8428/api/v1/import/prometheus" \
>   bash push-metrics.sh
> ```
> The `VICTORIA_METRICS_URL` env var sets the push target. The script defaults
> to `localhost:8428` — set this only if your agent is NOT on the same machine
> as VictoriaMetrics.

Verify metrics are flowing:

```bash
# Push once manually (dry run without cron)
AGENT_NAME="titus" bash ~/hermes-cortex/ops/scripts/manage/push-metrics.sh

# ⚡ Ask Moses to check (or query VictoriaMetrics directly if you have access):
curl -s "http://<victoria-host>:8428/api/v1/query" \
  --data-urlencode 'query=node_cpu_usage_percent{agent="titus"}'
```

Expected: HTTP 204 on push, JSON result with your metric on query.

### Option B: Python (custom metrics with prometheus_client)

For agents that need custom metrics (bus queue depths, cron run times, task
counts), use `prometheus_client` and POST to the same endpoint:

```python
from prometheus_client import Counter, Gauge, generate_latest
import urllib.request

# ⚡ Point to your VictoriaMetrics server
VICTORIA_URL = "http://<victoria-host>:8428/api/v1/import/prometheus"

# Define your metrics
tasks_processed = Counter("agent_tasks_processed_total",
    "Tasks processed", ["agent"])
disk_usage = Gauge("agent_disk_usage_percent",
    "Disk usage", ["agent"])

# Collect and push
payload = generate_latest()
req = urllib.request.Request(
    VICTORIA_URL,
    data=payload,
    headers={"Content-Type": "text/plain; version=0.4.0"},
    method="POST"
)
with urllib.request.urlopen(req, timeout=10) as resp:
    assert resp.status == 204  # success
```

The format is identical to Prometheus exposition format — any standard
Prometheus library works with VictoriaMetrics.

### How the push model works

```
Your Agent                          ⚡ Central VictoriaMetrics Server
─────────────────                   ┌──────────────────────────────┐
                                    │  port 8428                   │
push-metrics.sh (every 5m)          │  accepts Prometheus text     │
  └─ collects cpu/mem/disk         │  at /api/v1/import/prometheus│
  └─ POSTs Prometheus format ─────▶│  (same format Prometheus     │
     Content-Type: text/plain      │   would scrape)              │
     "node_cpu_usage_percent 23.5" │  → HTTP 204 (stored)         │
                                    │                              │
  No inbound ports needed.          │  Grafana at :3030            │
  No firewall changes.              │  Query with PromQL           │
  Works behind NAT.                 └──────────────────────────────┘
```

Key advantage: your agent **pushes** to a central endpoint. No need for the
central server to reach into your network.

### What it costs

- **Bash script**: Zero — `no_agent` mode, no LLM tokens
- **Python with prometheus_client**: ~1µs per metric operation
- **Network**: ~1KB per push, every 5 minutes = ~8MB/month

### Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| `curl: Connection refused` | VictoriaMetrics server is down or URL is wrong |
| `HTTP 204` returned but no data in Grafana | Wait up to 30s for ingestion. Check with `curl .../api/v1/query` |
| Push script not found in cron | Script must be a real file copy in `~/.hermes/scripts/`, not a symlink |
| `AGENT_NAME` shows as `hostname` instead of your agent name | Set `VICTORIA_METRICS_AGENT_LABEL=titus` env var, or the script uses `hostname` |

### ⚡ Luke's fleet: existing agents

| Agent | Push status | Notes |
|-------|-------------|-------|
| Moses | ✅ Every 5m via `agent-moses-push-metrics` cron | Serves as reference implementation |
| Titus | ⬜ Not yet — add your own | Follow Option A above |
| Joseph | ⬜ Not yet | Add with `VICTORIA_METRICS_URL=http://moses:8428/...` |
| Kustos | ⬜ Not yet | Same URL as Joseph |
| Esther | ⬜ Not yet | Orchestrator backup — same URL pattern |

---

Your SOUL.md is your identity file — other agents (and you) read it to understand
who you are, what you do, and how you operate.

Copy the template:

```bash
cp ~/hermes-cortex/docs/templates/SOUL.md ~/.hermes/SOUL.md
# Or create it from scratch
```

At minimum, every SOUL.md must include:

| Section | What it's for |
|---------|---------------|
| Identity | Who you are, what machine you run on |
| Core Mission | Your purpose in the fleet |
| Communication Style | How you talk (direct, evidence-led, etc.) |
| Behavioral Principles | Loop governance, Agent Bus decision framework, honesty |
| Scriptural Insight | One behavioral commitment shaped by Scripture |

**Essential behavioral principles for a client-only agent:**

1. **Loop governance always** — `begin_change` → work → `cycle_query` → `feedback` → `end_change`. No exceptions.
2. **HTTP client, not MCP** — your ONLY bus access is `contact-orchestrator.sh` + `cortex-bus.conf`. Never install the `cortex-bus` MCP server; the doctor warns about it.
3. **Health via Agent Bus (HTTP)** — you have no HTTP health endpoint. Report health by sending JSON pings to the orchestrator via `curl` (Step 7), or `contact-orchestrator.sh` for messages.
4. **Poll, don't wait** — `agent-message-handler` cron is your ears. It runs every 5 min.

See existing SOUL.md files for reference:
- `~/.hermes/SOUL.md` (moses)
- `~/.hermes/SOUL.md` (gisu)
- `~/.hermes/SOUL.md` (kustos)

---

## Step 7 — Send Your First Health Ping

Once everything above is working, introduce yourself to the fleet by sending
a health ping to Moses. Use `curl` directly against the Agent Bus API —
this is the recommended approach for regular health pings:

```bash
curl -s -u "titus:your-password-here" \
  -X POST "https://example.com:13004/api/send" \
  -H "Content-Type: application/json" \
  -d '{
    "from": "titus",
    "subject": "🟢 Health: nominal",
    "body": "{\"v\":[1,1,1,1,1,1,1,1,1],\"h\":\"titus\",\"t\":'\"$(date +%s)\"'}",
    "topic": "health",
    "priority": "normal"
  }'
```

> **⚠️ Critical: `topic` must be `"health"` exactly.** Not `"general"`, not `"#health"`.
> Moses's health poller (`orch-fleet-watchdog`) queries for `topic=health` and ignores
> everything else. Pings sent to the wrong topic will get 200 OK responses but
> never be processed — they just sit in the inbox unseen.

Moses's `orch-fleet-watchdog` cron (every 5 min) will pick this up on its next
tick, parse the health vector, and your agent appears on the fleet dashboard.

**What the fields mean:**
| Field | Meaning |
|-------|---------|
| `from` | Your agent name (must match htpasswd username) |
| `topic` | **Must be `"health"`** — the bus routing key |
| `body` | A JSON **string** containing the health vector. Inner quotes are escaped. The body has three sub-fields: |
| `body → v` | 9-element health vector — see table below |
| `body → h` | Your hostname |
| `body → t` | Unix timestamp of the ping (use `$(date +%s)`) |

**Health vector format:**

```json
{"v":[1,1,1,1,1,1,1,1,1],"h":"titus","t":1712345678}
```

Each index in the `v` array:
| Index | Service | 1 = healthy | -1 = degraded |
|-------|---------|-------------|---------------|
| 0 | resources | CPU/mem/disk within limits | Threshold breached |
| 1 | services | All services running | One or more stopped |
| 2 | no_errored_crons | No cron failures | Errored crons detected |
| 3 | no_stale_crons | All crons running | Stale crons detected |
| 4 | nginx | nginx running | nginx down |
| 5 | ollama | Ollama responding | Ollama unreachable |
| 6 | gbrain | gbrain healthy | gbrain issues |
| 7 | disk_ok | Disk space OK | Low disk space |
| 8 | gbrain_sources_ok | All sources synced | Sync failures |

A healthy laptop sends all 1s. An issue like cron errors:
```json
{"v":[1,1,-1,1,1,1,1,1,1],"h":"titus","t":1712345678}
```

### Verify it's working

After sending a ping, wait for the next `orch-fleet-watchdog` tick (up to 5 min)
and check one of:

1. **Health queue** — your ping arrives (check via curl):
   ```bash
   curl -s -u "titus:your-password" \
     "https://example.com:13004/api/pgmq/depth/inbox_health_check"
   ```
   Depth > 0 means your ping is pending (drained every 10 min by `orch-clean-health-queue`).

2. **Agent health data** (Moses can check):
   ```bash
   python3 -c "import json;d=json.load(open('~/.hermes-cortex/state/inbox-health-state.json'));print(d.get('titus'))"
   ```
   A dict with `vector` + `ts` means your latest ping was drained and recorded.

3. **Dashboard** — open the Cortex Dashboard URL. Your agent card should appear
   alongside the other agents, green if all services are 1.

### Advanced: Rich format (optional)

Instead of the compact vector, you can send a detailed breakdown. The body
contains a JSON object with `"type": "health-report"`:

```bash
curl -s -u "titus:your-password" \
  -X POST "https://example.com:13004/api/send" \
  -H "Content-Type: application/json" \
  -d '{
    "from": "titus",
    "subject": "🟢 Health: detailed",
    "body": "{\"type\":\"health-report\",\"healthy\":true,\"platform\":\"macOS\",\"hostname\":\"titus\",\"services\":[{\"name\":\"ollama\",\"status\":\"running\"}],\"resources\":{\"cpu_pct\":23,\"mem_pct\":62,\"disk_pct\":45},\"issues\":[]}",
    "topic": "health",
    "priority": "normal"
  }'
```

This gets parsed into the same 9-element vector for the dashboard, with extra
metadata preserved for the dashboard endpoint.

## Health Pings — Anchor Pattern

This section explains how Moses processes your health pings.

### How it works

Every 5 minutes, `orch-fleet-watchdog` (a no_agent script, runs at $0 cost):

1. Reads all `#health`-topic messages from your agent in the inbox
2. **Keeps the oldest message** (the *anchor*) — this stays as proof you were alive
3. **Deletes all newer health pings** — they confirmed liveness but are redundant once consumed
4. Parses the anchor body into a health vector and writes it to the fleet dashboard

**When you're alive:** The anchor sits in the inbox. Orch-team-health reads it
every tick and the dashboard shows green.

**When you sleep (lid closed, no network):** The anchor stays. Orch-team-health
reads it every tick — same anchor, same data. Dashboard stays green. **No false
alerts.** The anchor is your permanent "I was alive" marker.

**When you come back:** New pings arrive. The anchor stays (still the oldest),
newer pings are cleaned up. Dashboard stays green.

### Ping cadence

| You | Recommended interval |
|-----|-------------------|
| Routine health ping | Every **5 minutes** |
| On state change | Immediately (service down, disk full, etc.) |

Ping more or less often — it doesn't matter. Only the oldest message (anchor)
and the most recent check matter.

### Key points

- **Your first ping becomes the permanent anchor.** It stays in the inbox
  indefinitely until you restart your agent (a newer anchor takes its place).
- **You never accumulate pings.** Moses deletes consumed ones on every tick.
- **Laptop sleep is invisible.** The anchor keeps the dashboard green. No alerts.
- **No token cost.** The health pipeline is `no_agent` — no LLM involved.

## Step 8 — Register with the Fleet (Moses's Side)

This step happens **on Moses's machine**, not yours. Moses will:

1. Add you to `~/.hermes-cortex/state/agent-registry.json`:

```json
"titus": {
  "name": "Titus",
  "role": "dev-agent",
  "hostname": "titus",
  "is_server": false,
  "accessible": true,
  "health_method": "inbox",
  "platform": "macOS",
  "description": "Titus — macOS developer machine. NOT a server — do not poll. Pushes health vector to Agent Bus.",
  "inbox_user": "titus",
  "inbox_watch_schedule": "every 10m",
  "inbox_deliver": "local"
}
```

2. Create your htpasswd entry (if not done in Step 1)
3. Confirm you appear in the fleet roster

---

## Daily Life as a Client Agent

| Activity | How it works |
|----------|-------------|
| **Receiving instructions** | Moses sends Agent Bus messages → your poll cron picks them up → you process them |
| **Reporting results** | `contact-orchestrator.sh "✅ Done: <summary>"` → the orchestrator reads it on the next tick |
| **Reporting health** | Send JSON health pings via `curl` to `.../api/send` with `topic: "health"` (exact). Oldest ping stays as anchor, newer ones deleted. See [Step 7](#step-7--send-your-first-health-ping). |
| **Reporting metrics** | `push-metrics.sh` cron pushes CPU/memory/disk every 5m to VictoriaMetrics. No action needed after setup — it runs silently in background. See [Step 5b](#step-5b--set-up-metrics-push-to-victoriametrics-optional-but-recommended). |
| **Requesting cron changes** | `contact-orchestrator.sh "🔧 CRON: create|update|remove <name>"` — see `cron-request-protocol` skill |
| **Asking for help** | `contact-orchestrator.sh "🔴 Blocked: <issue>"` — the orchestrator investigates |
| **Talking to other agents** | Via the orchestrator: send `contact-orchestrator.sh "REPORT: ..."`; only Moses can route cross-agent |

---

## Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| `inbox_read` returns empty but you know messages exist | Your poll cron hasn't run yet. Wait for the next tick or run it manually: `cronjob action=run job_id=<id>` |
| `inbox_send` returns 401 | Wrong credentials in `~/.hermes-cortex/.env`. Double-check with Moses. |
| `inbox_send` returns connection refused | Moses's nginx is down. Check with the human. |
| Cron never delivers to Telegram | Your `--deliver origin` points to a chat that isn't connected. Check `hermes` settings. |
| You don't see your own SOUL.md | Only Moses has access. Your SOUL.md lives at `~/.hermes/SOUL.md` |
| Pings get 200 OK but dashboard stays red | You're sending to the wrong topic. Check: your POST body must have `"topic":"health"` (not `general`, not `#health`). Moses's poller only reads `topic=health`. |
| Metrics push returns 204 but no data in Grafana | VictoriaMetrics may be on a different host than Grafana expects. Check datasource URL in Grafana matches VM endpoint. |
| Metrics push returns connection refused | Central VictoriaMetrics is unreachable. Check the URL or ask Moses if the stack is running. |

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `~/.hermes-cortex/cortex-bus.conf` | Your bus credentials and agent identity (HTTP client) |
| `~/.hermes/config.yaml` | Hermes config — MCP server entry lives here |
| `~/.hermes/SOUL.md` | Your identity document — copy from `docs/templates/SOUL.md` |
| `~/hermes-cortex/mcp-servers/cortex-bus-mcp.py` | The MCP client that talks to the Agent Bus (PGMQ) — **orchestrators only; do NOT install on worker hosts** |
| `~/hermes-cortex/ops/scripts/manage/push-metrics.sh` | Standalone metrics push script — system-level Prometheus metrics to VictoriaMetrics |
| `~/hermes-cortex/core/cortex_bus/metrics.py` | Python metrics module — prometheus_client definitions + push client for custom metrics |
| `~/hermes-cortex/ops/install/deploy/docker-compose.victoria-metrics.yml` | VictoriaMetrics + Grafana Docker compose (central stack, runs on Moses) |
| `~/hermes-cortex/ops/install/deploy/agent-registry.template.json` | Fleet registry template |

---

## What You DON'T Need

- ❌ A public IP or domain
- ❌ nginx installed or configured
- ❌ SSL certificates
- ❌ An Agent Bus API backend (Moses runs that)
- ❌ A health HTTP endpoint
- ❌ systemd services or daemon management

All you need is Hermes Agent, the repo, the MCP client, credentials, and a cron.

**Metrics push** follows the same pattern — no extra infrastructure needed:
- ❌ No public IP or inbound ports (your agent pushes outbound)
- ❌ No API backend to run (the central VictoriaMetrics exists on the orchestrator)
- ❌ No additional authentication (HTTP POST to the central URL — no secrets to manage if the endpoint is internal)
- ❌ No Python dependencies for the simple case (bash script is zero-dependency)

---

## Cloud Deployment (Server Agents)

If you're setting up a **server agent** (Joseph, Esther, Kustos, Gisu) rather than a client-only agent, see:

| Resource | What it covers |
|----------|---------------|
| [`docs/cloud-deploy.md`](cloud-deploy.md) | Full runbook: AWS EC2 + Hetzner Cloud — instance sizing, security groups, DNS, SSL, verification, recovery |
| [`ops/deploy/cloud-init.yaml`](../ops/deploy/cloud-init.yaml) | Bootstrap a fresh Ubuntu 24.04 VM → running Hermes agent in one user-data paste |
| [`ops/deploy/ansible/provision.yml`](../ops/deploy/ansible/provision.yml) | Ansible playbook for idempotent provisioning (16 tasks, Docker, Ollama, Hermes, Langfuse, nginx) |

**Principle:** Local/private-first. Cloud deployment is available for migration or scaling, not a replacement for local operation.

---

## Shared Database (gbrain Postgres)

Every fleet agent has access to the shared **gbrain Postgres** database running on Moses's server. It provides:

- **Agent Bus** (PGMQ message queues) — inbox/outbox for fleet communication
- **`bus.todos`** — durable, fleet-visible todo persistence (via `todo-db.py`)
- **`bus.loop_governance`** — shared cycle scoring across agents

You don't need to install or manage Postgres yourself — your `cortex-update.sh` deploys the DB schemas automatically as part of the full stack.

**Verify your DB connectivity:** The doctor checks this:

```bash
python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py
```

Look for `Todo DB connectivity` — should show `PASS` with your pending item count.

**First sign something's wrong:** If `todo-db.py pending` returns errors on session start, gbrain Postgres may be down on Moses's end.

---

## Done ✅

You're connected. From now on:

1. Your poll cron checks the inbox every hour
2. Moses can send you tasks, and you'll pick them up on the next tick
3. You send results and health pings back through the Agent Bus
4. You never worry about servers, ports, or nginx

Welcome to the fleet.
