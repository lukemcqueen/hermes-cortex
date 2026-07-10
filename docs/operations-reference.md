# Operations Reference (Luke's Deployment)

This document contains operations-specific guidance for running Hermes Cortex
across Luke's multi-machine fleet. It was relocated from `AGENTS.md` to keep
the root agent guidelines focused on general Hermes Cortex usage.

---

## Agent Inbox Architecture

The agent inbox has two layers that are easy to confuse:

### Two layers, not one

| Layer | What it does | Who runs it |
|-------|-------------|-------------|
| **API backend** (gateway :8903 + nginx) | Stores messages, serves the HTTP API | **Only Moses and Esther** (the gateway does this automatically) |
| **MCP client** (`inbox-mcp.py` in Hermes config) | Provides `inbox_send`/`inbox_read`/`inbox_watch` tools to the agent | **Every agent** — including Moses and Esther |

The confusion is that "agent inbox" sounds like one thing. It's two:
1. The **server** that holds the messages → only Moses & Esther
2. The **client tool** that lets an agent send/read messages → every agent needs this

### Architecture diagram

```
MOSES / ESTHER (inbox servers)          EVERY AGENT (including Moses & Esther)
─────────────────────────────           ─────────────────────────────────────
Hermes gateway (:8903)                  ~/.hermes/config.yaml
  ↳ built-in inbox API                    ↳ mcp_servers.agent-inbox
  ↳ stores messages                       ↳ runs inbox-mcp.py as subprocess
                                          ↳ reads ~/hermes-cortex/.env (or legacy hermes-inbox.conf)
nginx proxy (:13004 / :14004)              ↳ calls remote inbox API via HTTP
  ↳ SSL + Basic Auth                      ↳ exposes inbox_send/read/watch tools
  ↳ proxies → :8903
```

### What each agent needs

| Agent | Role | Runs API backend? | Runs MCP client? | Has `.env` config? |
|-------|------|-------------------|-------------------|------------------------|
| **Moses** | Primary orchestrator | ✅ YES — gateway :8903 + nginx :13004 | ✅ YES — inbox tools | ✅ `~/hermes-cortex/.env` |
| **Esther** | Backup orchestrator | ✅ YES — gateway :8903 + nginx :14004 | ✅ YES — inbox tools | ✅ Points to her own instance |
| **Gisu** | Remote server | ❌ No — client only | ✅ YES — needs inbox-mcp.py in config | ✅ Points to Moses |
| **Joseph** | Remote server | ❌ No — client only | ✅ YES — needs inbox-mcp.py in config | ✅ Points to Moses |
| **Kustos** | Remote server | ❌ No — client only | ✅ YES — needs inbox-mcp.py in config | ✅ Points to Moses |
| **Titus** | macOS laptop | ❌ No — client only | ✅ YES — needs inbox-mcp.py in config | ✅ Points to Moses |

### Critical: You need a poll cron to receive messages

The MCP client and config give you the **ability** to read messages, but nothing
actually checks the inbox automatically unless you have a **poll cron**. Without
it, messages sit unread until a human starts a session with you.

Every client agent needs a `process-mcp-agent-inbox-messages` LLM cron:

```bash
hermes cron create --name process-mcp-agent-inbox-messages \
  --model "deepseek/deepseek-v4-flash" \
  --provider "openrouter" \
  --schedule "0 6-23 * * *" \
  --prompt "Check the agent inbox for new messages via inbox-watch MCP tool (mcp_agent_inbox_inbox_watch). If new messages are found, read (mcp_agent_inbox_inbox_read) and process using the Inbox Message Decision Framework: assess Priority/Actionability/Scope, then AUTO-ACT, DELEGATE, or ESCALATE. Report actionable items with evidence. Outside 6am-11pm daily, be silent if nothing urgent." \
  --deliver origin
```

This runs hourly 6am-11pm, costs ~$0.006/run in LLM tokens (~$0.11/day), and delivers
results to your origin chat (Telegram DM).

**Do NOT use the old `agent-inbox-check.sh` script** — it is deprecated and
no longer works (MCP-only now).

### What "install the inbox" means

```
If you are Moses or Esther:
  └─ You already have the API backend (it's part of the Hermes gateway)
  └─ You already have the MCP client (it's in your config.yaml)
  └─ You just need the nginx proxy setup

If you are Gisu, Joseph, Kustos, or Titus (client agents):
  └─ You need the MCP client in your Hermes config.yaml:
       mcp_servers:
         agent-inbox:
           command: python3
           args: [~/hermes-cortex/src/mcp-servers/inbox-mcp.py]
           enabled: true
  └─ You need ~/hermes-cortex/.env with YOUR credentials (or legacy `~/.hermes/hermes-inbox.conf`)
  └─ You DO NOT need to run an inbox server or nginx proxy
```

This configuration is set up automatically by `bash ~/hermes-cortex/install.sh` / `bash ~/hermes-cortex/ops/scripts/install-crons.sh`. If you ran the installer, your `config.yaml` already has the `agent-inbox` MCP server entry. If not, add it manually.

### Setup checklist

**Every agent (Moses, Esther, Gisu, Joseph, Kustos, Titus):**
```bash
# 1. Pull repo
cd ~/hermes-cortex && git pull

# 2. Ensure MCP client is in config.yaml
grep -A4 "agent-inbox" ~/.hermes/config.yaml
# Should show: command: python3, args: [inbox-mcp.py], enabled: true

# 3. Create credentials file — YOUR OWN credentials
# Primary: add to ~/hermes-cortex/.env (or use legacy ~/.hermes/hermes-inbox.conf)
nano ~/hermes-cortex/.env
```
```ini
CORTEX_INBOX_URL="https://your-domain.com:13004"
CORTEX_INBOX_AUTH="your_username:your_password"
AGENT_NAME="your_agent_name"
```
```bash
chmod 600 ~/hermes-cortex/.env

# 4. Verify you can talk to the inbox
curl -s -u "your_username:your_password" \
  https://your-domain.com:13004/api/inbox?limit=3

# 5. Create inbox-check cron (every 30 min):
#    hermes cron create ...
```

**Moses and Esther only — additionally:**
```bash
# Ensure nginx proxy exists (Moses: :13004 → :8903, Esther: :14004 → :8903)
# Already set up by install.sh — verify:
curl -s -u "your_username:your_password" https://your-domain.com:13004/api/inbox?limit=1
# Should return 200
```

### Common confusion to avoid

Key rule: only Moses and Esther run the inbox API backend. Every other agent just needs the MCP client (`inbox-mcp.py` in config.yaml) + credentials in `~/hermes-cortex/.env`. Do NOT share credentials — every agent has their own htpasswd user.

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
- **Docker config:** Edit `deploy/docker-compose.langfuse.yml`
- **Scoring hooks:** `bash ~/.hermes-cortex/ops/scripts/install/install-score-hook.sh --all` (or `--list`)

## Rules

- **No PII in this repo.** No personal paths, hostnames, emails, API keys, or tokens. Use placeholders (`$HOME/`, `~/`, `<username>`). Every agent MUST grep for personal identifiers before committing.
- No secrets. `.env`, `*.pem`, `*.key` are gitignored.
- Keep docs current when changing install behavior.


---

### Project Directory Convention


```
project-root/
├── .hermes-cortex/           # Agent infra (hidden, near code)
│   ├── sessions/current.md   # Active session state
│   ├── sessions/archive/     # Timestamped snapshots
│   ├── me

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-10T19:30:51.612984+00:00
