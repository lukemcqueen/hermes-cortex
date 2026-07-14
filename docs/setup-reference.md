# Setup Reference (Luke's Deployment)

This document contains setup-specific guidance for deploying Hermes Cortex
agents across Luke's multi-machine fleet. It was relocated from `AGENTS.md`
to keep the root agent guidelines focused on general Hermes Cortex usage.

---

## Systemd Service Policy — User-Level Only

**All Hermes Cortex services MUST be installed as user-level systemd units only.**

| ✅ Correct | ❌ Wrong |
|-----------|---------|
| `~/.config/systemd/user/com.hermes.health-server.service` | `/etc/systemd/system/hermes-health.service` |
| `systemctl --user enable/start` | `sudo systemctl enable/start` |
| `WantedBy=default.target` | `WantedBy=multi-user.target` |

### Why

Running duplicate services at both system and user scope causes port conflicts,
auto-restart loops, and syslog noise. The Cortex installer (`install.sh`) and
all templates ship user-level units — system-level duplicates are **never**
created by the repo's own tooling.

### Deployment checklist

1. Service files live in `~/.config/systemd/user/` only
2. Enable/start with `systemctl --user enable <name>` (no `sudo`)
3. `WantedBy=default.target` in the `[Install]` section
4. Never `sudo cp` a user service into `/etc/systemd/system/`

### Cleanup (if duplicates exist)

```bash
# Disable system-level duplicates
sudo systemctl disable --now hermes-dashboard hermes-health \
  hermes-inbox hermes-gateway

# Remove the stale unit files
sudo rm /etc/systemd/system/hermes-*.service
sudo rm /etc/systemd/system/multi-user.target.wants/hermes-*.service
```

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

1. **Server agents** (`health_method: "http"`): Moses' `fleet-status-watchdog.py` cron (`*/5 * * * *`) fetches each agent's vector via HTTP.
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
   python3 ~/hermes-cortex/ops/scripts/health/health-vector.py --serve <PORT>
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
5. Moses' `fleet-status-watchdog.py` picks it up automatically once the `health_url` is set in `~/.hermes-cortex/state/agent-registry.json`.

### Deployment (Titus / macOS client-only)

Titus cannot be polled (no inbound). Instead he pushes to Moses' inbox:

1. **Pull hermes-cortex** and set up `~/hermes-cortex/.env` with his own credentials:
   ```ini
   CORTEX_INBOX_URL="https://your-domain.com:13004"
   CORTEX_INBOX_AUTH="titus:<password>"
   AGENT_NAME="titus"
   ```
2. Install the launchd agent:
   ```bash
   cp ~/hermes-cortex/docs/templates/com.hermes.health-push.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.hermes.health-push.plist
   ```
3. Test: `AGENT_NAME=titus bash ~/hermes-cortex/ops/scripts/health/health-vector-push.sh`

### Files

| Path | Purpose |
|------|---------|
| `ops/scripts/health/health-vector.py` | Health vector generator + HTTP server (cross-platform) |
| `ops/scripts/health/health-vector-push.sh` | Inbox push script for client-only agents |
| `ops/scripts/agent/fleet-status-watchdog.py` | Fleet health poller (no_agent cron) |
| `ops/scripts/agent/orch-health-report.py` | Health snapshot report — formatted for Telegram delivery |
| `src/agent-registry.template.json` | Agent registry template (fill during setup → `~/.hermes-cortex/state/agent-registry.json`) |
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
# 0. Set orchestrator flag in .env (required for orch crons installer)
echo 'IS_ORCHESTRATOR=true' >> ~/hermes-cortex/.env

# 1. Copy the script
cp ~/hermes-cortex/ops/scripts/agent/orch-health-report.py ~/.hermes/scripts/orch-health-report.py

# 2. Create the crons
hermes cron create --name orch-health-report-weekday \
  --no-agent --script orch-health-report.py \
  --schedule "0 9-18 * * 1-5"

hermes cron create --name orch-health-report-saturday \
  --no-agent --script orch-health-report.py \
  --schedule "0 11,17 * * 6"

# 3. Set up her own agent-registry.local.json (see Moses' version for reference)
```

---

## Ollama Model Tier

Hermes Cortex ships a **two-model stack** plus a unified env-var configuration system.

### Single Env File (`~/hermes-cortex/.env`)

All environment variables live in `~/hermes-cortex/.env` (hidden, gitignored).
This is the single source of truth for Cortex. ⚠ `~/.hermes/.env` is Hermes Agent's own config and is never touched by Cortex.

| Env var | Purpose | Default |
|---------|---------|---------|
| `IS_ORCHESTRATOR` | Gate orchestrator-only features (orch crons, team health, inbox remediation). Set `true` on Moses/Esther only. | `false` |
| `CORTEX_HEALTH_URL` | External health endpoint. Orchestrator pollers use this to verify agent reachability through nginx. Format: `https://yourdomain.com:xx007/health` | _(none)_ |
| `JUDGE_MODEL` | LLM-as-Judge scorer | `qwen2.5-coder:3b` |
| `EMBEDDING_MODEL` | Text embeddings (gbrain, session cache, loop scorer, offline_code) | `nomic-embed-text:v1.5` |
| `CODING_MODEL` | Code generation via offline_code | auto-detected by RAM |
| `CREATIVE_MODEL` | Reserved for future creative tasks | _(not yet wired)_ |

Resolution priority (every script follows this):
1. **Runtime env var** — `JUDGE_MODEL=mannix/qwen:7b python3 script.py`
2. **`~/hermes-cortex/.env`** — persistent per-agent config, never overwritten
3. **Script's hardcoded default** — last resort fallback shipped with the repo

### Default Stack Values

| Tier | Model | Size | Role |
|------|-------|------|------|
| Embedding | `nomic-embed-text:v1.5` | 274 MB | Vector search (embeddings for search, RAG) |
| Unified gen/judge | `qwen2.5-coder:3b` | 1.9 GB | Code gen, classification, routing, quality gates |

> **⚠️ 64k context minimum required.** `qwen2.5-coder:3b` from the Ollama registry defaults to 32k — build it with 64k:
> ```bash
> ollama create qwen2.5-coder:3b -f <(echo -e "FROM qwen2.5-coder:3b\nPARAMETER num_ctx 65536")
> ```
> Larger variants (7b+) typically ship with 128k+ out of the box. The installer runs this check — see `install-ollama.sh build_qwen_model`.
>
> **Thermal note (CPU-only):** 65536 context on a CPU-only MacBook was previously blamed for 92°C throttling, but the real cause was unlimited Ollama threads + model kept loaded 24/7. With `OLLAMA_NUM_THREADS=2` and `OLLAMA_KEEP_ALIVE=0`, 65536 context runs at 58°C under load. See `install-ollama.sh` comments.

This replaces the previous three-model stack with a unified **qwen2.5-coder:3b** model for code generation, classification, and judging. Agents use it via `http://localhost:11434/api/generate` or `offline_code gen`.

### Scripts that respect `.env`

| Script | Env var read |
|--------|-------------|
| `llm-judge-scorer.py` | `JUDGE_MODEL` |
| `model-health-watchdog.py` | `JUDGE_MODEL` |
| `system-alert-watchdog.py` | `EMBEDDING_MODEL` |
| `loop_scorer.py` | `EMBEDDING_MODEL` |
| `session_cache.py` | `EMBEDDING_MODEL` |
| `loop-gov-mcp.py` | `EMBEDDING_MODEL` |
| `offline_code.py` | `EMBEDDING_MODEL`, `CODING_MODEL` |
| `lessons.py` | `EMBEDDING_MODEL` |
| `session_mine.py` | `EMBEDDING_MODEL` |
| `web_cache.py` | `EMBEDDING_MODEL` |
| `cleanup-ollama.sh` | `EMBEDDING_MODEL` |
| `install-ollama.sh` | `EMBEDDING_MODEL` |

### Cron Architecture — Three-Tier Model

Agent crons follow a three-tier architecture based on task requirements:

| Tier | Approach | When to use | Examples | Cost |
|------|----------|-------------|----------|------|
| **no_agent + API** | Python script + single deepseek API call | Deterministic orchestration + one creative generation | `agent-daily-bible-reading`, `agent-remediate-apply` | $0 / ~$0.01/run |
| **LLM-driven (deepseek)** | Full agent loop on deepseek-v4-flash | Needs Hermes tools (session_search, memory, patch) | `agent-daily-soul-refinement`, `memory-pruning`, `agent-fixer` | ~$0.01/run |
| **no_agent script** | Python/shell, no LLM | Deterministic checks, sensors, watchdogs | `remediation-sensor`, `model-health-watchdog`, `inbox-flag` | $0 |

**Migration from qwen2.5-coder:3b:** The 3B model is excellent for single-shot tasks but lacks the reasoning capacity for multi-step agentic workflows. Crons needing multi-tool chaining have been migrated to the first two tiers. Example: `agent-apply-fixes` was an LLM cron on qwen (every 10min, 9.6k token → 29min inference); converted to a no_agent script searching the offline code corpus instead — 4.5s per run, zero LLM cost.

**Key scripts:**
- `ops/scripts/agent-daily-bible-reading.py` — no_agent + deepseek API
- `ops/scripts/agent-remediate-apply.py` — no_agent: reads sensor output, applies fixes
- `ops/scripts/agent-apply-fixes.py` — no_agent: searches offline code corpus for fix patterns

Install: `bash ops/scripts/install-crons.sh`

### First-time bootstrap

After a fresh clone + setup, seed the loop-governance DB with scored cycles from git history:

```bash
cd ~/hermes-cortex && python3 ~/.hermes/scripts/populate-governance-db.py
```

This creates scored cycles from commits in the last 7 days so governance metrics (cycle counts, scoring activity, no_errored_crons) have baseline data from day one. **Only needed once per machine.**
