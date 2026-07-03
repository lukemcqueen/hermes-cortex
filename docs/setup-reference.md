# Setup Reference (Luke's Deployment)

This document contains setup-specific guidance for deploying Hermes Cortex
agents across Luke's multi-machine fleet. It was relocated from `AGENTS.md`
to keep the root agent guidelines focused on general Hermes Cortex usage.

---

## Health Monitoring Pipeline

The orchestrator polls all server agents every 10 minutes for a compact
**health vector** — a 9-element ternary status vector with no auth overhead,
no secrets, no JSON bloat.

### Service map (shared across all agents)

| Index | Service | Code | Description |
|-------|---------|------|-------------|
| 0 | resources | 1=ok, -1=stressed, 0=n/a | CPU load < 4× cores, memory > 5% free |
| 1 | services | 1=ok, -1=down, 0=n/a | At least one core daemon reachable |
| 2 | no_errored_crons | 1=ok, -1=error, 0=n/a | No cron jobs with recent failures |
| 3 | no_stale_crons | 1=ok, -1=stale, 0=n/a | No cron jobs gone stale (orchestrator) |
| 4 | nginx | 1=up, -1=down, 0=n/a | nginx process running |
| 5 | ollama | 1=up, -1=down, 0=n/a | Ollama process running |
| 6 | gbrain | 1=up, -1=down, 0=n/a | gbrain sync daemon running |
| 7 | disk_ok | 1=ok, -1=full, 0=n/a | Root partition < 90% used |
| 8 | gbrain_sources_ok | 1=ok, -1=missing, 0=n/a | ~/brain dirs exist and non-empty |

### Health endpoint (server agents)

Each server agent runs `health-vector.py --serve <port>` as a systemd user service. The endpoint returns a single JSON line:
```json
{"v":[1,1,1,1,1,1,1,1],"h":"hostname","t":1700000000}
```
No authentication. No TLS. Plain HTTP — the vector contains no secrets, just binary up/down/n/a flags.

### Agent endpoint URLs

> **Private config:** Actual domains are set locally (not committed to the public repo).
> See `src/agent-registry.json` — each agent's `health_url` must be configured on the
> orchestrator for the poller to reach it. Port hints are in the description field.

| Agent | Port | Method | Auth |
|-------|------|--------|------|
| Moses | `127.0.0.1:13007` | HTTP poll (internal) | none |
| Gisu | `:13007` | HTTP poll | none |
| Kustos | `:13007` | HTTP poll | none |
| Joseph | `:12007` | HTTP poll | none |
| Esther | `:14007` | HTTP poll | none |
| Titus | pushes to Moses inbox | Inbox push | each agent's own credentials |

### How it works

1. **Server agents** (`health_method: "http"`): Moses' `orch-team-health.py` cron (`*/10 * * * *`) fetches each agent's vector via HTTP.
2. **Client-only agents** (`health_method: "inbox"`): Titus runs `health-vector-push.sh` via launchd every 10 minutes, POSTing his vector to Moses' inbox API with his own Basic Auth credentials.
3. **Change detection**: The poller fingerprints each vector. No output = no change. Alerts fire only on state transitions:
   - `🔴 Titus ❌ ollama` (service went down)
   - `✅ Titus — all services restored` (back to healthy)

### Deployment (each server agent)

1. Open the firewall port:
   ```bash
   sudo ufw allow <PORT>/tcp
   ```
2. Run health-vector server (port varies per agent):
   ```bash
   python3 ~/hermes-cortex/src/scripts/health-vector.py --serve <PORT>
   ```
3. Install the systemd user service (Linux):
   ```bash
   systemctl --user enable health-vector.service
   systemctl --user start health-vector.service
   ```
4. Verify:
   ```bash
   curl -s http://127.0.0.1:<PORT>/
   # → {"v":[...], "h":"hostname", "t":...}
   ```
5. Moses' `orch-team-health.py` picks it up automatically once the `health_url` is set in `src/agent-registry.json`.

### Deployment (Titus / macOS client-only)

Titus cannot be polled (no inbound). Instead he pushes to Moses' inbox:

1. **Pull hermes-cortex** and set up `~/.hermes/moses-inbox.conf` with his own credentials:
   ```ini
   MOSES_INBOX_URL="https://your-domain.com:13004"
   MOSES_INBOX_AUTH="titus:<password>"
   AGENT_NAME="titus"
   ```
2. Install the launchd agent:
   ```bash
   cp ~/hermes-cortex/docs/templates/com.hermes.health-push.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.hermes.health-push.plist
   ```
3. Test: `AGENT_NAME=titus bash ~/hermes-cortex/src/scripts/health-vector-push.sh`

### Files

| Path | Purpose |
|------|---------|
| `src/scripts/health-vector.py` | Health vector generator + HTTP server (cross-platform) |
| `src/scripts/health-vector-push.sh` | Inbox push script for client-only agents |
| `src/scripts/orch-team-health.py` | Orchestrator poller (no_agent cron) |
| `src/scripts/orch-health-report.py` | Health snapshot report — formatted for Telegram delivery |
| `src/agent-registry.json` | Agent registry with `health_method`, `health_url` |
| `docs/templates/com.hermes.health-push.plist` | macOS launchd template for Titus |
| `docs/templates/health-vector.service` | systemd user service template for server agents |

### Health snapshot report

Moses sends a health snapshot to Luke on schedule via two no_agent crons:

| Cron | Schedule | What it does |
|------|----------|-------------|
| `orch-health-report-weekday` | `0 9-18 * * 1-5` | Every hour Mon-Fri 9AM–6PM KST |
| `orch-health-report-saturday` | `0 11,17 * * 6` | Sat 11AM + 5PM KST |

The script (`orch-health-report.py`) reads the agent registry with local overrides, polls every agent's health endpoint, and outputs compact markdown with emoji status bars — designed for mobile Telegram. No LLM tokens used (no_agent script cron).

**To deploy on Esther (backup orchestrator):**

```bash
# 1. Copy the script
cp ~/hermes-cortex/src/scripts/orch-health-report.py ~/.hermes/scripts/orch-health-report.py

# 2. Create the crons
hermes cron create --name orch-health-report-weekday \
  --no-agent --script orch-health-report.py \
  --schedule "0 9-18 * * 1-5"

hermes cron create --name orch-health-report-saturday \
  --no-agent --script orch-health-report.py \
  --schedule "0 11,17 * * 6"

# 3. Set up her own agent-registry.local.json (see Moses' version for reference)
```
