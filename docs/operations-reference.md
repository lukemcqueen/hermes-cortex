# Operations Reference (Luke's Deployment)

This document contains operations-specific guidance for running Hermes Cortex
across Luke's multi-machine fleet. It was relocated from `AGENTS.md` to keep
the root agent guidelines focused on general Hermes Cortex usage.

---

## Agent Bus Architecture (previously Agent Inbox)

### The Agent Bus — PGMQ-based Postgres queue system

The **Agent Bus** (previously Agent Inbox) replaces the file-based inbox with a Postgres-native message queue.
Port **8905**, powered by `bus` schema on gbrain Postgres (port 15432).

**Key differences from the legacy file-based inbox:**

| Feature | Old Inbox (file-based) | Agent Bus (PGMQ) |
|---------|-----------------------|-------------------|
| Storage | Markdown files | Postgres (`bus.messages` table) |
| Auth | Basic auth (shared htpasswd) | Bearer tokens + mTLS (per-agent) |
| Routing | LLM-controlled cron ($156/yr) | Deterministic (`route_if` string match) |
| SLA | None | Visibility timeout + DLQ + recovery |
| Observability | Logs only | SQL views + JSON dashboard |
| Port | 8903 (server.py) | 8905 (systemd service) |
| Nginx | 13004 → 8903 (old inbox) | 13004 → 8905 (after cutover) |

**Service:** `cortex-bus.service` — systemd user service, auto-starts on boot.
**Circuit breaker:** Auto-degrades to old inbox if Postgres is unavailable (3 failures → file fallback).

### Old Inbox (file-based, deprecating)

The original legacy agent inbox (file-based) still runs on port **8903** for backward compatibility. It will be kept in read-only mode
or removed entirely after all agents are confirmed on the bus.

### Two layers, not one

| Layer | What it does | Who runs it |
|-------|-------------|-------------|
| **API backend** (Agent Bus :8905 + nginx) | Stores messages, serves the HTTP API | **Only Moses and Esther** (the gateway does this automatically) |
| **MCP client** (`cortex-bus-mcp.py` in Hermes config) | Provides `inbox_send`/`inbox_read`/`inbox_watch` tools to the agent | **Orchestrators only** (Moses, Esther) — the doctor enforces this (`ORCH_ONLY_MCP_SERVERS`); workers use `contact-orchestrator.sh` / `lib.cortex_bus.bus_send` over HTTP instead |

The confusion is that "agent inbox" sounds like one thing. It's two (and was formerly known as the Agent Inbox):
1. The **server** that holds the messages → only Moses & Esther
2. The **client tool** that lets an agent send/read messages → orchestrators use the MCP tools (`inbox_send`/`inbox_read`); workers use the HTTP path (`contact-orchestrator.sh` / `lib.cortex_bus.bus_send`) — no MCP entry in config.yaml

### Architecture diagram

```
MOSES / ESTHER (bus servers)     ORCHESTRATORS ONLY (MCP client)        WORKERS (HTTP path)
─────────────────────────────      ─────────────────────────────────────  ───────────────────────────
Hermes gateway (:8905)         ~/.hermes/config.yaml                  ~/.hermes-cortex/cortex-bus.conf
 ↳ built-in Agent Bus API        ↳ mcp_servers.agent-bus               ↳ CORTEX_BUS_URL + CORTEX_BASIC_AUTH
 ↳ stores messages (PGMQ)        ↳ runs cortex-bus-mcp.py as subprocess  ↳ contact-orchestrator.sh / lib.cortex_bus.bus_send
                     ↳ reads ~/hermes-cortex/.env
nginx proxy (:13004 / :14004)       ↳ calls remote Agent Bus via HTTP
 ↳ SSL + Basic Auth           ↳ exposes inbox_send/read/watch tools
 ↳ proxies → :8905
```

### What each agent needs

| Agent | Role | Runs API backend? | Runs MCP client? | Has `.env` config? |
|-------|------|-------------------|-------------------|------------------------|
| **Moses** | Primary orchestrator | ✅ YES — gateway :8905 + nginx :13004 | ✅ YES — inbox tools | ✅ `~/hermes-cortex/.env` |
| **Esther** | Backup orchestrator | ✅ YES — gateway :8905 + nginx :14004 | ✅ YES — inbox tools | ✅ Points to her own instance |
| **Gisu** | Remote server | ❌ No — client only | ❌ No — HTTP path (`contact-orchestrator.sh` / `lib.cortex_bus.bus_send`) | ✅ Points to Moses |
| **Joseph** | Remote server | ❌ No — client only | ❌ No — HTTP path (`contact-orchestrator.sh` / `lib.cortex_bus.bus_send`) | ✅ Points to Moses |
| **Kustos** | Remote server | ❌ No — client only | ❌ No — HTTP path (`contact-orchestrator.sh` / `lib.cortex_bus.bus_send`) | ✅ Points to Moses |
| **Titus** | macOS laptop | ❌ No — client only | ❌ No — HTTP path (`contact-orchestrator.sh` / `lib.cortex_bus.bus_send`) | ✅ Points to Moses |

### Critical: You need a poll cron to receive messages

The MCP client and config give you the **ability** to read messages, but nothing
actually checks the inbox automatically unless you have a **poll cron**. Without
it, messages sit unread until a human starts a session with you.

**Orchestrators (Moses, Esther)** need inbox-processing LLM cron(s) that use
the `inbox-watch` MCP tool. The recommended approach
is a **tiered weekday schedule** that matches work hours:

| Tier | Hours (KST, Mon-Fri) | Cadence | Cron Expression |
|------|---------------------|---------|-----------------|
| Workday | 9am–6pm | Every 10 min | `*/10 9-17 * * 1-5` |
| Evening | 6pm–12am | Every 30 min | `*/30 18-23 * * 1-5` |
| Overnight | 12am–6am | Every 2 hours | `0 0-5/2 * * 1-5` |

No polling during 6am–9am or on weekends.

Create three separate cron jobs to cover the full cycle:

```bash
# Workday — every 10 min, Mon-Fri 9am-6pm
hermes cron create --name process-inbox-workday \
 --model "deepseek-v4-flash" \
 --provider "deepseek" \
 --schedule "*/10 9-17 * * 1-5" \
 --prompt "Check the Agent Bus for new messages via inbox-watch MCP tool (mcp_agent_inbox_inbox_watch). If new messages are found, read (mcp_agent_inbox_inbox_read) and process using the Inbox Message Decision Framework: assess Priority/Actionability/Scope, then AUTO-ACT, DELEGATE, or ESCALATE. Report actionable items with evidence. If no messages, output exactly [SILENT]." \
 --deliver origin

# Evening — every 30 min, Mon-Fri 6pm-midnight
hermes cron create --name process-inbox-evening \
 --model "deepseek-v4-flash" \
 --provider "deepseek" \
 --schedule "*/30 18-23 * * 1-5" \
 --prompt "Check the Agent Bus for new messages via inbox-watch MCP tool (mcp_agent_inbox_inbox_watch). If new messages are found, read (mcp_agent_inbox_inbox_read) and process using the Inbox Message Decision Framework: assess Priority/Actionability/Scope, then AUTO-ACT, DELEGATE, or ESCALATE. Report actionable items with evidence. If no messages, output exactly [SILENT]." \
 --deliver origin

# Overnight — every 2 hours, Mon-Fri midnight-6am
hermes cron create --name process-inbox-overnight \
 --model "deepseek-v4-flash" \
 --provider "deepseek" \
 --schedule "0 0-5/2 * * 1-5" \
 --prompt "Check the Agent Bus for new messages via inbox-watch MCP tool (mcp_agent_inbox_inbox_watch). If new messages are found, read (mcp_agent_inbox_inbox_read) and process using the Inbox Message Decision Framework: assess Priority/Actionability/Scope, then AUTO-ACT, DELEGATE, or ESCALATE. Report actionable items with evidence. If no messages, output exactly [SILENT]." \
 --deliver origin
```

**Cost estimate:** ~$0.006/run → workday (54 runs/wk) + evening (12 runs/wk) + overnight (3 runs/wk) = ~$0.41/day ≈ $12/mo. The sensitive periods (workday) poll fastest; overnight and weekends run at reduced cadence to save tokens.

**Workers (Gisu, Joseph, Kustos, Titus):** you do NOT create these LLM crons —
they require the MCP `inbox-watch` tool, which you do not have. Your inbox is
polled by the `agent-message-handler` no_agent cron (every 5 min, installed by
default), which processes UPDATE_REQUEST etc. and replies via the HTTP client.

**Do NOT use the old `agent-inbox-check.sh` script** — it is deprecated and
no longer works (MCP-only now).

### What "install the Agent Bus" means

```
If you are Moses or Esther (orchestrator):
 └─ You already have the API backend (it's part of the Hermes gateway)
 └─ You already have the MCP client (it's in your config.yaml)
 └─ You just need the nginx proxy setup

If you are Gisu, Joseph, Kustos, or Titus (worker):
 └─ You DO NOT install the MCP client (cortex-bus-mcp.py). It is
    orchestrator-only — the doctor warns if you add it.
 └─ You DO have the HTTP client: ~/.hermes-cortex/cortex-bus.conf
    + contact-orchestrator.sh (or lib.cortex_bus). This is your ONLY bus access.
 └─ You DO NOT run a bus server, Postgres, or nginx proxy
```

> See the role matrix at the top of `docs/bus-architecture.md` — it is the
> canonical "who has what" reference. Every bus doc points to it.

### Setup checklist

**Orchestrators (Moses, Esther):**
```bash
# 1. Pull repo
cd ~/hermes-cortex && git pull

# 2. Ensure MCP client is in config.yaml
grep -A4 "agent-bus" ~/.hermes/config.yaml
# Should show: command: python3, args: [cortex-bus-mcp.py], enabled: true

# 3. Create credentials file — YOUR OWN credentials
nano ~/hermes-cortex/cortex-bus.conf
```
```ini
CORTEX_BUS_URL="https://your-domain.com:13004"
CORTEX_BASIC_AUTH="your_username:your_password"
AGENT_NAME="your_agent_name"
```
```bash
chmod 600 ~/hermes-cortex/cortex-bus.conf

# 4. Verify you can talk to the inbox
curl -s -u "your_username:your_password" \
 https://your-domain.com:13004/api/inbox?limit=3
```

**Workers (Gisu, Joseph, Kustos, Titus):** Do NOT add an `agent-bus` entry to
`config.yaml` — the MCP client is orchestrator-only. Your bus access is the
HTTP client (`~/.hermes-cortex/cortex-bus.conf` + `contact-orchestrator.sh`), which
the installer sets up. Verify it with:
```bash
bash ~/.hermes-cortex/scripts/contact-orchestrator.sh "TEST: connectivity" "ping"
```

**Moses and Esther only — additionally:**
```bash
# Ensure nginx proxy exists (Moses: :13004 → :8903, Esther: :14004 → :8903)
# Already set up by install.sh — verify:
curl -s -u "your_username:your_password" https://your-domain.com:13004/api/inbox?limit=1
# Should return 200
```

### Common confusion to avoid

Key rule: only Moses and Esther run the Agent Bus API backend and the MCP
client. Every other agent uses the HTTP client only (`contact-orchestrator.sh` +
`~/.hermes-cortex/cortex-bus.conf`). Do NOT share credentials — every agent
has their own htpasswd user.

---

## Offline Code — Local Snippet Search & Generation

518-snippet corpus across 32 categories. **Mandatory agent workflow:**
1. `offline_code search "<pattern>"` — check corpus first
2. **Found?** Use it. Zero API cost.
3. **Not found?** `web_search()` as last resort
4. **If web succeeded:** `offline_code learn "<title>" ...` to fill the gap

Commands: `offline_code search`, `offline_code gen`, `offline_code learn`, `offline_code stats`.

**tirith MCP server:** Use `tirith_*` tools instead of raw `curl` for sandboxed URL/command checks. Configure: `hermes mcp add tirith --command tirith --args mcp-server`

Load `skill_view(name="offline-code")` for full usage docs.

---

## Common Tasks

- **Troubleshooting:** Edit `docs/troubleshooting.md`
- **Templates:** Place in `docs/templates/`, update `install.sh`
- **Install changes:** Edit `install.sh` (26 steps, idempotent)
- **Docker config:** Edit `ops/install/deploy/docker-compose.langfuse.yml`
- **Scoring hooks:** `bash ~/.hermes-cortex/ops/scripts/install/install-score-hook.sh --all` (or `--list`)

## Rules

- **No PII in this repo.** No personal paths, hostnames, emails, API keys, or tokens. Use placeholders (`$HOME/`, `~/`, `<username>`). Every agent MUST grep for personal identifiers before committing.
- No secrets. `.env`, `*.pem`, `*.key` are gitignored.
|- Keep docs current when changing install behavior.

---

### Installation (one-time per agent)

```bash
cd ~/hermes-cortex && git pull --rebase origin main
bash ops/scripts/agent/install-worker.sh <YOUR_NAME>
```

The installer:
1. Copies `agent-worker.py` to `~/.hermes/scripts/`
2. Creates systemd `--user` service at `~/.config/systemd/user/hermes-agent-worker.service`
3. Auto-grants bus permissions if running on the bus machine
4. Starts the service via `systemctl --user start`
5. Verifies it's running

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-15T00:00:00+00:00

### Config

The worker reads from `~/.hermes-cortex/cortex-bus.conf`:
```ini
BUS_URL=http://bus-host:8905
CORTEX_BUS_AUTH=<your-basic-auth>
AGENT_NAME=<your-name>
```

Also accepts `CORTEX_BUS_FALLBACK_URL` and `CORTEX_BUS_AUTH` (primary names). Deprecated names `CORTEX_BUS_URL` and `CORTEX_INBOX_AUTH` still work as fallback.

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-17T00:00:00+00:00

> **⚠️ Conflict with agent-message-handler cron**
> The worker reads inbox messages with `vt=0` (peek — doesn't consume).
> Non-`workflow_step` messages stay visible for the `agent-message-handler` cron
> which runs every 5 minutes and processes `UPDATE_REQUEST`, `DIAGNOSTIC_REQUEST`,
> etc.
>
> If you upgrade the worker from an older version that used `vt=120`, you MUST
> pull the latest code and restart:
> ```bash
> cd ~/hermes-cortex && git pull && bash ops/scripts/cortex-update.sh
> systemctl --user restart hermes-agent-worker
>```
> Run `cortex-doctor` after to verify no warnings.

---

### In-session (MCP) — preferred when you have tools

```python

from hermes_tools import mcp__agent_inbox__inbox_send

mcp__agent_inbox__inbox_send(

  to="moses",

  subject="QUESTION: Bus seems slow today",

  body="I'm seeing 2s response times on port 8905",

  priority="normal"


)
```

Best for: human-readable questions, reports, help requests during your session.

Permanent: git-backed, survives restarts.

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-15T00:00:00+00:00

---

### Message format

| Field | Required | Description |
|-------|----------|-------------|
| `subject` | yes | Prefix with type: `QUESTION:`, `REPORT:`, `HELP:`, `ISSUE:`, `CRITICAL:` |
| `body` | yes | Full message content |
| `priority` | no | `normal` (default), `urgent`, `critical` |

| Situation | Subject prefix | Priority |
|-----------|---------------|----------|
| General question | `QUESTION:` | normal |
| Need help with config/tool | `HELP:` | normal |
| Reporting a result | `REPORT:` | normal |
| Something is broken | `ISSUE:` | urgent |
| System is down | `CRITICAL:` | critical |

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-15T00:00:00+00:00

### Headless (bus curl) — from workers, scripts, crons

```bash


bash ~/.hermes/scripts/contact-orchestrator.sh "QUESTION: Is the bus healthy?" "I see 503 errors" urgent


```

Or raw curl:

```bash


curl -s -u "$CORTEX_BASIC_AUTH" -X POST \


 -H "Content-Type: application/json" \


 -d '{"queue":"inbox_moses","message":{"from":"<YOUR_NAME>","to":"moses","subject":"QUESTION: <topic>","body":"<question>","priority":"normal"}}' \


 "${BUS_URL}/api/pgmq/send"


```

Best for: automated step results, no_agent cron outputs, worker data.

Ephemeral: Postgres PGMQ — archived after processing.

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-15T00:00:00+00:00
