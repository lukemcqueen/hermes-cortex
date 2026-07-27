---
name: hermes-cortex-setup
description: Install and configure Hermes Cortex core components — Ollama, Bun, gbrain, health server, agent registry, hooks, cron jobs, and profile scaffolding on a target machine.
behavioral_principles:
 - Never install gbrain via pip3 or bare 'npm install -g gbrain' — the npm registry has a squatter package (old GPU JS library). Always use 'bun install -g github:garrytan/gbrain'.
 - When installing Bun, prefer download-inspect-execute over raw curl|bash when the security scanner flags it.
 - Always create a .env file in ~/hermes-cortex/ before running install-orch-crons.sh to avoid silent failure.
 - When sudo is unavailable, install Ollama from GitHub releases tarballs (not the official install.sh which requires root).
 - Before writing custom configs or inventing new approaches, check the repo's docs/ and ops/scripts/ first for existing documented solutions. Use the documented tools as primary; custom workarounds are a last resort.
 - When setting up services on a target machine, inspect running configs FIRST — check /etc/nginx/sites-enabled/, systemctl --user list-units, ss -tlnp, ps aux. The deployed nginx upstream blocks define the correct internal ports. Never invent port assignments before checking what's already deployed. Check in order: (1) running machine configs, (2) hermes-cortex repo docs/, (3) agent-registry.template.json.
 - For systemd user services that run bun/gbrain scripts, always set explicit PATH in Environment= — systemd does not inherit the user shell's PATH.
 - Verify each install step with a version check or doctor command before proceeding to the next.
 - After installing components, update PATH persistence in shell config (~/.bashrc) for Bun and ~/.local/bin.
 - The canonical SOUL.md path is ~/.hermes/SOUL.md — never write to /home/<other-user>/ paths without verifying they exist.
 - The brain directory structure needs git-init'd MECE subdirectories (19 dirs), not just flat kb/memories dirs.
 - The health-vector.py server binds to 127.0.0.1 by default; nginx proxies external traffic. No need to patch bind addresses — health-vector.py has zero pip dependencies and no EXTERNAL_HEALTH_URL requirement.
 - The gbrain CLI 'sources add' command can hang indefinitely on first run; use a timeout wrapper or configure the source path via the DB config directly.
 - When the user gives a cross-user path for SOUL.md (e.g. ~/...), redirect to ~/.hermes/SOUL.md and inform them — never create files in another user's home.
 - The user prefers the short /health endpoint path for external health URLs, not /api/v1/health. The former returns a compact vector, the latter returns full JSON. Always default to /health unless the user specifies otherwise.
 - The health server exposes two endpoints with different response formats: /health (compact 9-element vector, ideal for orchestrator polling) and /api/v1/health (full JSON, ideal for debugging). When configuring EXTERNAL_HEALTH_URL, use /health per user preference.
 - The gbrain sources add command can hang indefinitely on first run because it initializes the embedding model or does I/O. Workaround: use timeout wrapper or pipe EOF into stdin. The timeout causes a non-zero exit even on success, so check actual source status separately.
 - When setting up an agent on a target machine, always check the machine's existing deployed configs FIRST — especially /etc/nginx/sites-enabled/ and /etc/systemd/system/ and /etc/nginx/conf.d/. The actual upstream port definitions may differ from what the docs say. Check nginx configs for upstream blocks before choosing internal ports.
 - Before writing custom configs or inventing port schemes, check three sources in order: (1) the running config on the machine itself (nginx sites-enabled, systemd services), (2) the hermes-cortex repo docs/ directory, (3) the agent-registry.template.json. Only after exhausting these three should you write a custom approach.
 - Before importing markdown files into gbrain, stop the gbrain-sync.service daemon first — gbrain import fails with "Timed out waiting for PGLite lock" if the sync daemon holds the database lock. Restart sync after import completes.
 - fail2ban, nginx config deployment, and apt package installation require sudo. When these steps are needed and sudo is unavailable, prepare config files at `~/.hermes-cortex/nginx/` and scripts at `~/.hermes-cortex/scripts/` with full terminal commands printed for the user to copy-paste. Never assume sudo is available.
 - The health-vector.py service must run on port 8905 (127.0.0.1). This is what the deployed nginx `upstream health_backend` block expects. Do not change the port unless the nginx config explicitly defines a different upstream.
 - After the `src/` → `ops/` repo migration (July 2026), many deployed scripts retained stale `src/` paths. When fixing a script that references `src/scripts/` or `src/loop-governance/`, check if the file moved to `ops/scripts/` or `runtime/loop-governance/`. The old `src/` tree was completely removed. Grep for `src/` references in any script you patch as a matter of course.
 - Bus on 8903, health-vector on 8905. Never conflate them. The bus ExecStart must use the Hermes venv python (has uvicorn), not /usr/bin/python3.
 - Name the bus service file agent-bus.service, not hermes-agent-bus.service. The doctor checks for exactly agent-bus.service.
 - Verify bus setup at three layers: (1) systemctl is-active agent-bus.service, (2) curl :8903/health returns backend pgmq, (3) nginx upstream agent_bus_backend matches :8903. A running process on a port is not enough.
 - After cortex-update , check ~/.hermes/scripts/ for symlinks that point outside the scripts dir. Cron's no_agent runtime rejects symlinks. Replace with real `cp` copies.
 - no_agent cron scripts don't inherit Hermes env vars. If a script needs CORTEX_BUS_TOKEN or CORTEX_BUS_URL, ensure they're set via ~/.hermes-cortex/cortex-bus.conf, not just ~/hermes-cortex/.env.
 - After running install-orch-crons.sh, always check for stale old-name duplicate crons (bus-* vs orch-bus-*) and remove them. The installer doesn't auto-uninstall renamed crons.
 - When patching a no_agent cron script that uses `docker`, always wrap with `sg docker -c`. The cron runtime doesn't have docker group access even if the agent's shell does.
 - After cortex-update , verify deployed cron scripts in ~/.hermes/scripts/ are real file copies, not symlinks to the repo. Cron runtime rejects symlinks that resolve outside ~/.hermes/scripts/.
 - When running cortex-update.sh from its deployed location at ~/.hermes/scripts/, always export REPO_DIR=$HOME/hermes-cortex first. The script auto-detects REPO_DIR from $(dirname "${BASH_SOURCE[0]}") which resolves to ~/.hermes/scripts/ — not a git repo — and fails with "✗ Not a git repository".
trigger: User asks to install, set up, deploy, or bootstrap Hermes Cortex, or mentions 'cortex setup', 'install cortex', 'hermes-cortex components'. The cron health report shows an agent as 🔴 unreachable — the fix is often missing health server + agent registry on that machine.
---

# Hermes Cortex Setup

Walkthrough for installing the core Hermes Cortex components on a Linux (or macOS) machine. Each step is verified before moving to the next.

## Prerequisites

- Linux or macOS host
- `curl`, `git`, `python3`, `unzip` available
- Hermes Agent installed (the cortex skill set layers on top)
- Target repo cloned: `git clone https://github.com/nousresearch/hermes-cortex.git ~/hermes-cortex`

## Installation Steps

### 0. Prerequisites Check

```bash
# Check what's available
echo "Python: $(python3 --version 2>/dev/null || echo 'MISSING')"
echo "Git: $(git --version 2>/dev/null || echo 'MISSING')"
echo "Docker: $(docker --version 2>/dev/null || echo 'MISSING')"
echo "Sudo: $(sudo -n echo 'yes' 2>/dev/null || echo 'no')"
echo "Python3.12: $(python3.12 --version 2>/dev/null || echo 'MISSING')"
```

**Pitfall — Hermes venv vs system Python:** pip packages are installed in `~/.hermes/hermes-agent/venv/`. The `python3` on PATH is usually this venv's python. Use `/usr/bin/python3` for system stuff and `~/.hermes/hermes-agent/venv/bin/python3` for agent-dependent services.

### 0.5. Clone the Repo (if not already cloned)

```bash
git clone --depth 1 https://github.com/fleet-operator/hermes-cortex.git ~/hermes-cortex
```

**Pitfall — Installer script path bug:** The `install.sh` script references scripts at `$(_scripts)/install-ollama.sh` but the actual file is at `$(_scripts)/install/install-ollama.sh` (inside an `install/` subdirectory). Running `install.sh` directly will fail on step 1 with a "No such file or directory" error. Fix: run the individual install scripts manually rather than the monolithic installer, or symlink the paths.

### 1. Install Ollama (Local LLM Server for Embeddings)

**No-sudo install (when sudo is unavailable):**

Ollama's official `install.sh` requires root to install to `/usr/local`. When sudo is unavailable, use the GitHub releases tarball:

```bash
# Detect the correct download URL (format changed to .tar.zst in v0.31+)
OLLAMA_VERSION="v0.31.2" # Latest stable as of Jul 2026
curl -fsSL --retry 3 --retry-delay 5 \
 -o /tmp/ollama-linux-amd64.tar.zst \
 "https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}/ollama-linux-amd64.tar.zst"

# Extract
mkdir -p /tmp/ollama-extract
tar --zstd -xf /tmp/ollama-linux-amd64.tar.zst -C /tmp/ollama-extract/

# Install binary
mkdir -p ~/.local/bin
cp /tmp/ollama-extract/bin/ollama ~/.local/bin/ollama
chmod +x ~/.local/bin/ollama

# Install libaries (needed by gbrain's llama-server companion)
mkdir -p ~/.local/lib/ollama
cp -r /tmp/ollama-extract/lib/ollama/* ~/.local/lib/ollama/
chmod +x ~/.local/lib/ollama/llama-server

# Verify
~/.local/bin/ollama --version
```

**Systemd user service:**

```bash
mkdir -p ~/.config/systemd/user/
cat > ~/.config/systemd/user/ollama.service << 'EOF'
[Unit]
Description=Ollama LLM Server
After=network-online.target

[Service]
ExecStart=%h/.local/bin/ollama serve
Environment=OLLAMA_HOST=127.0.0.1
Environment=OLLAMA_NUM_THREADS=2
Environment=OLLAMA_KEEP_ALIVE=0
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable ollama.service
systemctl --user start ollama.service
```

**Pull the embedding model:**

```bash
ollama pull nomic-embed-text:v1.5
```

**Pitfall — tarball format change (July 2026):** Ollama changed their Linux release tarball format from `.tgz` (gzip) to `.tar.zst` (zstd) around v0.31.0. The old URL `https://ollama.com/download/ollama-linux-amd64.tgz` returns a 404. Always use the GitHub releases page at `https://github.com/ollama/ollama/releases` and download the `.tar.zst` variant. The herd-installer scripts that still reference `.tgz` will fail — fix by downloading from releases.

**Pitfall — port binding on fresh install:** Ollama binds to 127.0.0.1 by default on a manual install. This is correct for single-machine setups. If deploying as a server that other agents poll, you'd set `OLLAMA_HOST=0.0.0.0` — but this also opens your LLM server to the LAN. Use nginx basic auth in front for production.

### 2. Install Bun (JavaScript runtime)

**Pitfall — security scanner blocking curl|bash:** The official Bun install (`curl -fsSL https://bun.sh/install | bash`) may be flagged by security scanners. Use the download-inspect-execute pattern:

```bash
# Download the install script for safety inspection
curl -fsSL https://bun.sh/install -o /tmp/bun-install.sh

# Inspect briefly (verify it's from oven-sh/bun, not malicious)
# Then run:
bash /tmp/bun-install.sh

# Verify
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
bun --version  # Should output v1.3.x or later
```

**Pitfall:** The security scanner may block `curl https://bun.sh/install | bash` style piping. The download→inspect→run pattern above avoids this.

### 3. Install gbrain (Knowledge Brain)

**CRITICAL PITFALL — npm squatter package:**
The npm registry has an unrelated squatter package at `gbrain@1.3.x` (an old GPU JavaScript library from 2018). If you run `pip3 install gbrain`, `npm install -g gbrain`, or `bun install -g gbrain`, you silently install the wrong binary. The canonical gbrain lives at `github:garrytan/gbrain`.

```bash
# Remove squatter if accidentally installed
bun remove -g gbrain 2>/dev/null
rm -f "$BUN_INSTALL/bin/gbrain" 2>/dev/null

# Install the real gbrain
bun install -g github:garrytan/gbrain

# Verify
gbrain --version  # Should output 0.42.x or later
```

### 4. Initialize gbrain

**🥇 RECOMMENDED: Postgres + pgvector via Docker (stable, concurrent, production).**

PGLite (WASM) is known to crash under Bun 1.3.x on several Linux configurations with `Aborted()`. Postgres + pgvector is the recommended engine for production. It supports concurrent connections (query while sync runs), survives disk corruption better, and doubles as a general-purpose RAG database for any agent with a pgvector client.

The gbrain Postgres is managed as part of the Langfuse Docker Compose stack (see Step 17):

```bash
# Add the env var to ~/langfuse/.env if not present
echo 'GBRAIN_PG_PASSWORD=your-password' >> ~/langfuse/.env

# Deploy the compose stack (includes gbrain-postgres service)
sg docker -c "docker compose -f ~/langfuse/docker-compose.yml up -d"

# Enable pgvector extension
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -c 'CREATE EXTENSION vector;'"

# Initialize gbrain with the Postgres URL
DATABASE_URL="postgresql://gbrain:your-password@127.0.0.1:15432/gbrain"
gbrain init --url "$DATABASE_URL" --embedding-model ollama:nomic-embed-text:v1.5 --yes

# Add your brain source
gbrain sources add hermes-cortex --path ~/hermes-cortex
gbrain sources default hermes-cortex

# Verify
gbrain doctor --json --fast
```

**⚠️ DEPRECATED: PGLite (WASM) — dev fallback only when Docker is unavailable.**

```bash
gbrain init --pglite --embedding-model ollama:nomic-embed-text:v1.5 --yes
```

Expected output: "Brain ready" plus recommended skills. Note: PGLite is single-connection — CLI commands hang while the sync daemon runs. See `references/pglite-wasm-postgres-migration.md` for the migration guide if WASM crashes.

### 5. Set Up Health Server (Agent Reachability)

**IMPORTANT — use the documented tool first:** The canonical approach per `setup-reference.md` uses `health-vector.py` (simple Python `http.server`, no dependencies). Avoid inventing custom solutions — the repo ships documented scripts for each purpose. The FastAPI `health-server.py` is a richer alternative for when you need detailed diagnostics, but always start with the documented approach unless you have a specific reason not to.

Each agent machine runs a health server so the orchestrator (Moses) can poll its status. Without this, the health report shows the agent as 🔴 unreachable.

#### Primary Approach: health-vector.py (Documented per setup-reference.md)

This is the canonical approach. It's a zero-dependency HTTP server that outputs a compact 9-element vector. Ports per agent from the docs:

| Agent | Port |
|-------|------|
| Moses/Gisu/Kustos | `:13007` |
| Joseph | `:12007` |
| Esther | `:14007` |
| Titus | inbox push (no HTTP) |

```bash
# Create systemd user service
cat > ~/.config/systemd/user/health-vector.service << 'EOF'
[Unit]
Description=Hermes Cortex Health Vector Server (<agent-name>)
After=network.target
Wants=ollama.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/<user>/hermes-cortex/ops/scripts/health/health-vector.py --serve <PORT>
Environment=HEALTH_HOSTNAME=<agent-hostname-prefix>
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable health-vector.service
systemctl --user start health-vector.service

# Verify
curl -s http://127.0.0.1:<PORT>/
# → {"v": [1, -1, 1, 1, -1, 0, 0, 1, -1], "h": "esther", "t": 1700000000}
```

**Key points:**
- No dependencies beyond stdlib (no pip install needed)
- Serves on `127.0.0.1` only by default — use nginx for external access (see step 14)
- Default `HEALTH_HOSTNAME` is `"t"` — set it to your agent's name so the orchestrator can identify the host
- `h` field shows the full hostname string (e.g. `"esther"`), not just the first letter
- The compact vector at `/` and `/health` is all the orchestrator needs
- **CRITICAL — add `Environment=PATH=` to the service unit.** `health-vector.py` uses `shutil.which()` to detect ollama and gbrain. Systemd does NOT inherit the user shell's PATH — if `~/.local/bin` and `~/.bun/bin` aren't in the service's PATH, both ollama and gbrain report as `0` (not installed), and `services` cascades to `-1` because not all key services are found. The vector goes from 7/9 → 5/7. Always include:
 ```
 Environment=PATH=/home/<user>/.local/bin:/home/<user>/.bun/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
 ```

**CRITICAL — do NOT assign the nginx external port as the health server's internal port.** The deployed nginx config defines `upstream health_backend { server 127.0.0.1:8905; }`. The internal port is always **8905** for health. Check `/etc/nginx/sites-enabled/*` for the actual upstream definition before choosing — never invent a +1 pattern.

**Verification pitfall — don't trust `systemctl is-active` alone.** After restarting or installing the health-vector service, the unit may report `active` even when configured on the wrong port. Always verify at THREE layers:
1. `systemctl --user is-active health-vector.service` → `active`
2. `curl -s http://127.0.0.1:<PORT>/` → valid JSON vector (not empty, not connection refused)
3. `curl -sk https://<domain>:<NGINX_PORT>/` → same vector (nginx proxy works)

A mismatch between the systemd unit's `ExecStart` port (e.g. `--serve 8906`) and the nginx `upstream` port (e.g. `server 127.0.0.1:8905`) produces `systemctl active` + `504 Gateway Timeout` or `502 Bad Gateway` via nginx, and `connection refused` on the expected port locally. If local curl works on a different port, grep the service file:

```bash
grep --serve ~/.config/systemd/user/health-vector.service
```

Fix: `patch` the `--serve <correct_port>` value in the service file, then `systemctl --user daemon-reload && systemctl --user restart health-vector.service`.

See `references/health-vector-troubleshooting.md` for the full three-layer verification walkthrough and port-mismatch reproduction steps.

**Golden rule — Check existing deployments before inventing configs.** Check three sources in order:
1. **Running configs on the machine** — `/etc/nginx/sites-enabled/*`, `systemctl --user list-units`, `ss -tlnp`, `ps aux`
2. **Hermes Cortex docs** — `docs/setup-reference.md`, `docs/operations-reference.md`, `docs/fleet-reference.md`
3. **Agent registry template** — `ops/install/deploy/agent-registry.template.json` in the repo (old `src/agent-registry.template.json` path no longer valid)

The biggest class of error is inventing port assignments (e.g. 12007, 14008, 14070, 14076) when the answer is already in the deployed nginx config. Always check first.

**Note on stale paths:** The `deploy/` root symlink (→ `ops/install/deploy/`) has been **removed**. Paths like `deploy/nginx/hermes-services.conf` are now fully broken — always use the canonical `ops/install/deploy/nginx/...` form.

**FastAPI health-server.py REMOVED.** The richer FastAPI-based `health-server.py` has been removed from the repo. Use `health-vector.py` only — it's zero-dependency and covers all agent health monitoring needs.

### 6. Set Up Agent Registry

The agent registry tells the orchestrator (Moses) how to find each agent. Each machine needs its own registry file:

```bash
mkdir -p ~/.hermes-cortex/state

cat > ~/.hermes-cortex/state/agent-registry.json << 'EOF'
{
 "version": 3,
 "health_vector_map": [
  "resources","services","no_errored_crons","no_stale_crons",
  "nginx","ollama","gbrain","disk_ok","gbrain_sources_ok"
 ],
 "agents": {
  "<agent-name>": {
   "name": "<Agent Name>",
   "role": "<role>",
   "hostname": "<hostname>",
   "is_server": true,
   "accessible": true,
   "platform": "linux",
   "health_method": "http",
   "health_url": "http://127.0.0.1:8905/api/v1/health",
   "description": "<Agent Name> — <description>",
   "inbox_user": "<agent-name>",
   "inbox_watch_schedule": "every 10m",
   "inbox_deliver": "local"
  }
 }
}
EOF
```

The agent names from the template:

| Key | Role | Description |
|-----|------|-------------|
| `moses` | orchestrator | Fleet health, cron management, infrastructure |
| `esther` | orchestrator-backup | Backup orchestrator during Moses downtime |
| `titus` | devops | Service health, ClickHouse ops, recovery |
| `kustos` | security | Threat detection, blocklist management |
| `gisu` | communications | Inbox routing, message triage |
| `joseph` | web-infrastructure | Web/infra server |

**Pitfall — localhost vs domain URL:** For local dev, use `http://127.0.0.1:8905/api/v1/health`. For production, Moses would update this to the public URL with nginx + basic auth.

### 7. Set Up gbrain Sync Daemon

The knowledge brain needs a sync daemon to watch for file changes:

```bash
cat > ~/.config/systemd/user/gbrain-sync.service << 'EOF'
[Unit]
Description=gbrain sync daemon
After=network-online.target
Wants=ollama.service

[Service]
ExecStart=/home/<user>/.bun/bin/bun run /home/<user>/.bun/bin/gbrain sync --watch
Environment=HOME=/home/<user>
Environment=PATH=/home/<user>/.bun/bin:/home/<user>/.local/bin:/usr/local/bin:/usr/bin:/bin
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable gbrain-sync.service
systemctl --user start gbrain-sync.service
```

**Pitfall — correct command is `sync --watch`, not `sync-daemon`:** The gbrain CLI does NOT have a `sync-daemon` subcommand. The continuous sync mode is `gbrain sync --watch` (or `gbrain sync --watch --interval N`). Running `gbrain sync-daemon` produces "Unknown command: sync-daemon".

**Pitfall — gbrain binary is a bun script, not a native binary:** `~/.bun/bin/gbrain` is a symlink to a TypeScript source file. Running it directly requires `bun` on PATH. Systemd user services do NOT inherit the user shell's PATH, so you must either:
- Use `ExecStart=/home/<user>/.bun/bin/bun run /home/<user>/.bun/bin/gbrain sync --watch` (recommended)
- Or set `Environment=PATH=...` in the service with the full bun path

**Pitfall — `Source "default" has no local_path` crash loop:** After starting gbrain sync, the logs may show: "Sync error (1/5): Source 'default' has no local_path." This triggers a crash loop: 5 consecutive failures → gbrain-sync exits → systemd restarts after 10s → repeat indefinitely (restart counter can reach 300+). The default source is **protected** (pre-v0.17 brain) and cannot have its `local_path` set via CLI. Fix by adding a new source and redirecting the brain's default:

```bash
# 1. Stop sync to free DB locks
systemctl --user stop gbrain-sync

# 2. Add a source with a real path
gbrain sources add hermes-cortex --path ~/hermes-cortex

# 3. Change the brain's default source
gbrain sources default hermes-cortex

# 4. Restart sync
systemctl --user start gbrain-sync

# 5. Verify — check journal for import, not errors
journalctl --user -u gbrain-sync --since \"30 seconds ago\" --no-pager -n 5
# Expected: \"Running full import of /home/.../hermes-cortex...\"
# NOT: \"Sync error (1/5): Source 'default' has no local_path\"
```

After fixing, the old `default` source is silently skipped because it's no longer the default. The daemon imports the new source (e.g. 800 files) and runs cleanly.

**Pitfall — gbrain service name mismatch in health-vector.py.** The `health-vector.py` script checks for specific systemd service names. The `check_services()` function uses `key_services = ["nginx", "ollama", "gbrain-sync"]` and `check_gbrain()` uses `_systemd_active("gbrain-sync.service")`. If you named the service differently (e.g. `gbrain-autopilot.service` or `com.gbrain.autopilot`), both checks fail — gbrain reports `0` and `services` reports `-1` (cascading: since gbrain isn't "running", `all_running` is `False`). Verify the service name with `systemctl --user list-units --type=service --state=active,running | grep gbrain` and update health-vector.py if yours differs.

After fixing, the health vector goes from `[1, -1, -1, 1, 1, 1, 0, 1, 1]` → `[1, 1, -1, 1, 1, 1, 1, 1, 1]` (services and gbrain turn green). The remaining `-1` (`no_errored_crons`) is a separate issue — errored cron jobs.

**Pitfall — gbrain sync blocked by files without YAML frontmatter.** Markdown files that lack YAML frontmatter (e.g. `# Title` instead of `---\ntitle: ...\n---`) cause gbrain to fail with "1 file(s) failed to parse: UNKNOWN: 1". This blocks the entire sync run — no new files are indexed. Symptoms: the sync watchdog says "Sync blocked" and the commit pointer never advances. Fix:

```bash
# Option A: Add --skip-failed to the systemd service ExecStart
# Original: ExecStart=... gbrain sync --watch
# Fixed:  ExecStart=... gbrain sync --watch --skip-failed
systemctl --user daemon-reload
systemctl --user restart gbrain-sync

# Option B: One-time acknowledge without modifying the service
systemctl --user stop gbrain-sync
gbrain sync --skip-failed
systemctl --user start gbrain-sync
```

With `--skip-failed`, the daemon acknowledges parse failures and advances past them. The file is still not indexed, but the sync makes progress. After 3 consecutive syncs with the same failure, gbrain auto-skips it permanently.

**Pitfall — gbrain sync fails with `git pull failed` when local branch diverged from remote.** gbrain's sync daemon runs `git pull` internally. If the local branch and remote diverged (e.g. after `git pull --rebase` or `git reset`), `git pull` fails with "your branch and 'origin/main' have diverged". This causes a crash loop: sync exits → systemd restarts → git pull fails again → repeat.

```bash
# Stop sync, fix the repo, restart
systemctl --user stop gbrain-sync
cd ~/hermes-cortex
git pull --rebase origin main
# If conflicts: resolve, git add <files>, git rebase --continue
git push origin main
systemctl --user start gbrain-sync
```

After restart, gbrain detects "last_commit not an ancestor of HEAD (history rewritten)" and does a tree-to-tree diff to re-sync. It reports "12 file(s) already done; draining" and re-indexes files whose content changed during the rewrite.

### 8. Create ~/.hermes-cortex Infrastructure Directory

```bash
mkdir -p ~/.hermes-cortex/state
mkdir -p ~/.hermes-cortex/hooks
mkdir -p ~/.hermes-cortex/sessions
mkdir -p ~/.hermes-cortex/scripts
mkdir -p ~/.hermes-cortex/skills
```

### 9. Create Brain Directory Structure (MECE Tree)

The gbrain brain source needs a full directory tree, not just a flat kb directory:

```bash
MECE_DIRS="archive civic companies concepts conversations deals \
 hiring household ideas inbox media meetings org people personal \
 programs projects prompts sources writing"

for source in default; do
 source_dir="${HOME}/.gbrain/sources/${source}"
 mkdir -p "$source_dir"
 for dir in $MECE_DIRS; do
  mkdir -p "${source_dir}/${dir}"
 done
 # Create index.md with schema docs
 cat > "${source_dir}/index.md" << 'INDEXEOF'
# Brain Source: default
...
INDEXEOF
 # Init git — gbrain requires git per source
 git -C "${source_dir}" init
 git -C "${source_dir}" add -A
 git -C "${source_dir}" commit -m "init: default brain source"
done
mkdir -p "${HOME}/.gbrain/sources/lessons"
```

### 10. Copy Skills, Hooks, and Loop Governance Tools

```bash
# Skills
cp -r ~/hermes-cortex/.hermes-cortex/skills ~/.hermes-cortex/

# Hooks
cp ~/hermes-cortex/.hermes-cortex/hooks/pre-commit ~/.hermes-cortex/hooks/pre-commit
cp ~/hermes-cortex/.hermes-cortex/hooks/post-commit ~/.hermes-cortex/hooks/post-commit
chmod +x ~/.hermes-cortex/hooks/pre-commit ~/.hermes-cortex/hooks/post-commit

# Governance DB bootstrap (one-time per machine)
python3 ~/.hermes/scripts/populate-governance-db.py
```

After setup, initialize the governance DB and session cache — see the loop-governance skill's `references/first-time-bootstrap.md` for the full first-run sequence (seed from git history, build cache, set hooksPath).

# Profile skills
# Personal skills no longer in repo — use ~/.hermes/skills/ directly

# AGENTS.md metadata
cp ~/hermes-cortex/AGENTS.md ~/.hermes/AGENTS.md

# SOUL.md — the agent's identity
# Agent profiles removed from repo — use template directly
cp ~/hermes-cortex/docs/templates/SOUL.md ~/.hermes/SOUL.md
```

**Pitfall — SOUL.md path:** The canonical location is `~/.hermes/SOUL.md`, NOT `~/...` or any other user's home. Always verify the target directory exists before writing. If the user gives you a cross-user path, create it under the current user's `~/.hermes/` instead and inform them.

### 11. Persist PATH in Shell Config

Add `~/.local/bin` and `~/.bun/bin` to the user's PATH:

```bash
grep -q '\.local/bin\|\.bun/bin' ~/.bashrc || {
 cat >> ~/.bashrc << 'EOF'

# Hermes Cortex paths
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"
EOF
}
```

### 12. Configure Git Identity

```bash
cd ~/hermes-cortex
git config user.name "<Agent Name>"
git config user.email "<agent-name>@hermes-cortex"
```

### 13. Install Universal Cron Jobs (Every Agent)

The `install-crons.sh` script in the repo installs the universal crons listed in AGENTS.md (health monitors, inbox sensors, governance auditors, etc.). These are no_agent scripts that run on every agent machine.

**Pitfall — script search path is `~/.hermes-cortex/scripts/`:** The `install-crons.sh` script (line 34) looks for scripts in `SCRIPTS_DIR="${HOME}/.hermes-cortex/scripts"`, NOT `~/.hermes/scripts/`. If scripts aren't found at that path, it silently skips those crons. Deploy scripts there first:

```bash
# Copy critical monitor scripts to both locations
mkdir -p ~/.hermes-cortex/scripts
mkdir -p ~/.hermes/scripts

for script in system-alert-watchdog.py service-recovery.py model-health-watchdog.py \
 remediation-sensor.py governance-auditor.py memory-to-brain-sync.py \
 agent-apply-fixes.py nginx-threat-pipeline.sh \
 agent-ip-submission.sh; do
 repo_path=$(find ~/hermes-cortex/ops/scripts -name "$script" 2>/dev/null | head -1)
 if [ -n "$repo_path" ]; then
  cp "$repo_path" ~/.hermes/scripts/"$script"
  cp "$repo_path" ~/.hermes-cortex/scripts/"$script"
 fi
done
```

**Pitfall — cron security rejects absolute paths AND symlinks:** The `hermes cron create` tool has two validations:

1. **Absolute path rejection** — pass just the filename, not the full path:
  ```
  Script path must be relative to ~/.hermes/scripts/. Got absolute or home-relative path: '...'
  ```
2. **Symlink traversal rejection** — symlinks resolving outside the scripts dir are blocked:
  ```
  Failed to create job: Script path escapes the scripts directory via traversal: 'foo.py'
  ```

Always use `cp` (real file copy) and pass just the filename (e.g. `remediation-sensor.py`), never `~/hermes-cortex/...` or a symlink.

**Pitfall — cron scripts import helper modules from the same directory.** Several cron scripts import utility modules as peer imports (`from hermes_tz import ...`, `from platform_utils import ...`, `from state_tracker import ...`, `from hermes_models import ...`). When you copy scripts to `~/.hermes-cortex/scripts/` or `~/.hermes/scripts/`, these helper modules must be copied alongside:

```bash
# Helper modules needed by Hermes Cortex cron scripts
for helper in platform_utils.py hermes_tz.py state_tracker.py hermes_models.py; do
 find ~/hermes-cortex/ops/scripts -name "$helper" -exec cp {} ~/.hermes/scripts/ \; 2>/dev/null
 find ~/hermes-cortex/ops/scripts -name "$helper" -exec cp {} ~/.hermes-cortex/scripts/ \; 2>/dev/null
done
```

Without these, cron scripts fail silently at runtime with `ModuleNotFoundError`:

```
File "system-alert-watchdog.py", line 32, in <module>
  from hermes_tz import format_timestamp
ModuleNotFoundError: No module named 'hermes_tz'
```

**Pitfall — scripts called as sibling subprocesses by cron-run handlers are NOT auto-deployed.** `cortex-update.sh ` registers script paths in its internal map and deploys them to `CORTEX_DEPLOY_HOME` (`~/.hermes-cortex/scripts/`), but some handler scripts run from the cron path (`~/.hermes/scripts/`) and resolve sibling scripts at runtime via `Path(__file__).resolve().parent / "<sibling>.py"`. For example, `agent-message-handler.py` (every 2 min cron) calls `agent-diagnostic.py` as a subprocess using this sibling-path pattern. If `agent-diagnostic.py` only exists in `~/.hermes-cortex/scripts/` but not in `~/.hermes/scripts/`, the handler silently fails at runtime.

After `cortex-update `, check for this pattern and sync siblings:

```bash
# Find handlers that reference sibling subprocess calls via resolve().parent
grep -rl "resolve().parent" ~/.hermes/scripts/ 2>/dev/null | while read handler; do
 handler_dir=$(dirname "$handler")
 # Extract script names referenced as siblings
 grep -oP 'parent\s*/\s*"\K[^"]+' "$handler" 2>/dev/null | while read sibling; do
  src="$HOME/.hermes-cortex/scripts/$sibling"
  dst="$handler_dir/$sibling"
  if [ -f "$src" ] && [ ! -f "$dst" ]; then
   cp "$src" "$dst"
   echo "Synced sibling: $sibling → $handler_dir/"
  fi
 done
 # Also sync lib/ directory if handler has peer imports from lib.
 if grep -q "from lib\." "$handler" 2>/dev/null; then
  mkdir -p "$handler_dir/lib"
  cp "$HOME/.hermes-cortex/scripts/lib/"*.py "$handler_dir/lib/" 2>/dev/null
 fi
done
```

Without this, subprocess handlers fail at runtime with:
```
FileNotFoundError: [Errno 2] No such file or directory: '.../agent-diagnostic.py'
```
(Shows no stderr and no ModuleNotFoundError — just an empty result, which is harder to debug.)

**Pitfall — `install-crons.sh` reports "✓ Created" for jobs that actually failed.** The script prints "✓ Created cron: X" during processing but the underlying `hermes cron create` command may have failed with a validation error (e.g. symlink traversal, missing dependencies). Always verify with `hermes cron list` after install to confirm the cron was actually registered. The script's final summary line ("✓ Created: N new cron job(s)") is accurate; the per-job "✓ Created" lines are optimistic.

See `references/cron-dependency-map.md` for the full dependency table and debugging guide.

**Pitfall — `hermes cron create` validates script paths and rejects both absolute paths and symlinks.** Two separate checks:
1. Pass just the filename, not the full path (error: `"Script path must be relative to ~/.hermes/scripts/"`)
2. Symlinks resolving outside `~/.hermes/scripts/` are rejected (error: `"Script path escapes the scripts directory via traversal"`)
Use `cp` (real file copies), not `ln -sf`.

Then run the installer:

```bash
bash ~/hermes-cortex/ops/scripts/install-crons.sh
```

Expected output: "✓ Created: N new cron job(s)" where N is the number of scripts found (up to 28+).

Main categories of universal crons:
- **Health monitoring**: `system-alert-watchdog` (every 30m), `service-recovery` (every 5m), `model-health-watchdog` (daily)
- **Governance**: `governance-auditor` (every 6h), `agent-weekly-loop-eval` (weekly)
- **Inbox**: `inbox-flag` (every 10m), `agent-inbox` (every 2h)
- **Remediation**: `remediation-sensor` (every 5m), `agent-fixer` (every 2h)
- **Security**: `threat-pipeline` (daily), `agent-ip-submission` (every 30m)
- **Maintenance**: `memory-pruning` (weekly), `memory-to-brain-sync` (every 6h)
- **Content**: `agent-daily-bible-reading` (daily), `agent-daily-soul-refinement` (daily)

Verify with: `hermes cron list`

### 13b. Install Orchestrator Crons (Moses Only)

Crons are installed via the orchestrator (Moses) using the inbox request protocol per AGENTS.md. For initial setup on the orchestrator machine:

```bash
cat > ~/hermes-cortex/.env << 'EOF'
IS_ORCHESTRATOR=true
LLM_CRON_MODEL=<model-name>
LLM_CRON_PROVIDER=<provider-name>
EMBEDDING_MODEL=nomic-embed-text:v1.5
EOF

bash ~/hermes-cortex/ops/scripts/install/install-orch-crons.sh
```

**Pitfall:** `install-orch-crons.sh` exits with error if `LLM_CRON_MODEL` and `LLM_CRON_PROVIDER` are not set in `.env`. On worker agents (non-orchestrator), it exits gracefully with a message saying orchestrator crons aren't needed.

## Verification

After all steps, run the full verification:

```bash
# 1. Systemd services
systemctl --user list-units --type=service --state=active,running 2>/dev/null | \
 grep -E 'ollama|health-vector|gbrain'

# 2. Health endpoint (compact vector)
curl -s http://127.0.0.1:8905/

# 3. Ollama
curl -s http://127.0.0.1:11434/api/tags
# Should show nomic-embed-text:v1.5

# 4. gbrain
gbrain doctor --json --fast

# 5. Bun
bun --version

# 6. gbrain sync daemon
journalctl --user -u gbrain-sync.service --no-pager -n 10

# 7. Agent profiles
# Agent profiles removed from repo — SOUL.md lives at ~/.hermes/SOUL.md
ls ~/.hermes/SOUL.md
cat ~/.hermes/SOUL.md | head -5

# 8. Agent registry
cat ~/.hermes-cortex/state/agent-registry.json | python3 -m json.tool | head -10

# 9. PATH
echo "$PATH" | tr ':' '\n' | grep -E "local|bun"

# 10. Brain structure
ls ~/.gbrain/sources/default/
```

Expected health vector output:
```json
{"v": [1, 1, 1, 1, 1, 1, 1, 1, 1], "h": "hostname", "t": 1700000000}
```

### 14. Set Up Nginx Reverse Proxy (SSL Termination)

The health server binds to `127.0.0.1:INTERNAL_PORT` (localhost only) and nginx handles the external interface with SSL. Without this separation, nginx and the health server conflict on the same port.

See `references/nginx-proxy-patterns.md` for:
- Port convention table (prefix per agent: 14=Esther, 13=Moses/generic, 12=Joseph)
- SSL cert setup with Let's Encrypt
- Full nginx config template
- The port conflict pattern and fix

Quick deploy (run with sudo):
```bash
sudo cp ~<user>/.hermes-cortex/nginx/hermes-<agent>.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/hermes-<agent>.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo nginx -s reload
```

### 15. Import Brain Files into gbrain

After extracting brain files into the MECE brain directory structure, they need to be imported into gbrain to become searchable. The sync daemon holds a database lock, so it must be stopped first:

```bash
# Stop sync to release DB lock
systemctl --user stop gbrain-sync.service

# Import markdown files
cd ~/.gbrain/sources/default
gbrain import . --yes

# Restart sync
systemctl --user start gbrain-sync.service

# Verify
gbrain query "test"  # Should return imported pages
```

**Pitfall — gbrain import requires the DB lock to be free.** If the sync daemon is running, gbrain import fails with "Timed out waiting for PGLite lock". Always stop the sync daemon before running import or any other write operation. Restart it afterward.

See `references/health-endpoint-formats.md`

**Pitfall — PGLite WASM runtime crash (July 2026).** On some Linux systems, gbrain's PGLite engine fails to initialize its WASM runtime with `Aborted()`. The daemon enters a crash loop (600+ restart attempts). Fix: switch gbrain from PGLite to Postgres + pgvector via Docker. See `references/pglite-wasm-postgres-migration.md` for the full workaround.

## Related

- Setting up individual project profiles: `cortex-profile.sh <project-name> [path]`
- gbrain reference: `docs/gbrain-v2-taxonomy.md` in the repo
- Loop governance: `references/first-time-bootstrap.md` (first-run DB seed, cache build, hooksPath config)
- Nginx proxy patterns: `references/nginx-proxy-patterns.md` (port convention, SSL, port conflict fix)
- Health endpoint formats: `references/health-endpoint-formats.md` (compact vector vs full JSON)
- Health vector troubleshooting: `references/health-vector-troubleshooting.md` (systematic debug — PATH, service names, cron errors)
- Agent Bus troubleshooting: `references/agent-bus-troubleshooting.md` (token verification, missing X-Forwarded-User header, runtime path mismatch, queue verification, systemd service template)
- Stale paths audit guide: `references/stale-paths-audit-guide.md` (systematic methodology for auditing docs after repo restructures)
- Docker without sudo patterns: `references/docker-no-sudo.md` (sg docker -c, group management)

### 16. Set Up Cortex Dashboard

The Cortex Dashboard is a Flask app at `ops/services/dashboard/server.py`. It shows system health, cron status, and agent info. No Docker needed.

```bash
# Install Flask (in Hermes venv)
~/.hermes/hermes-agent/venv/bin/pip3 install flask

# Create systemd user service
cat > ~/.config/systemd/user/cortex-dashboard.service << 'EOF'
[Unit]
Description=Hermes Cortex Dashboard
After=network.target

[Service]
Type=simple
ExecStart=/home/<user>/.hermes/hermes-agent/venv/bin/python3 \\
 /home/<user>/hermes-cortex/ops/services/dashboard/server.py
Environment=HOME=/home/<user>
Environment=CORTEX_DASHBOARD_PORT=8901
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable cortex-dashboard.service
systemctl --user start cortex-dashboard.service

# Verify
curl -s http://127.0.0.1:8901/ | head -5
# → <!DOCTYPE html><html lang="en">...
```

Nginx proxies this at `:14001` (or the agent's prefix + 001).

### 17. Deploy Langfuse (LLM Observability)

Langfuse runs as a Docker Compose stack with ClickHouse, Postgres, Redis, and MinIO. Requires Docker.

```bash
# Generate secrets
mkdir -p ~/langfuse
cat > ~/langfuse/.env << EOF
LANGFUSE_CLICKHOUSE_PASSWORD=$(openssl rand -hex 16)
LANGFUSE_POSTGRES_PASSWORD=$(openssl rand -hex 16)
LANGFUSE_REDIS_AUTH=$(openssl rand -hex 16)
LANGFUSE_MINIO_ACCESS_KEY=$(openssl rand -hex 16)
LANGFUSE_MINIO_SECRET_KEY=$(openssl rand -hex 32)
LANGFUSE_SALT=$(openssl rand -hex 16)
LANGFUSE_SECRET_KEY=$(openssl rand -hex 32)
LANGFUSE_NEXTAUTH_SECRET=$(openssl rand -hex 32)
LANGFUSE_ENCRYPTION_KEY=$(openssl rand -hex 32)
LANGFUSE_DOMAIN=localhost
EOF

# Copy compose file and start
cp ~/hermes-cortex/ops/install/deploy/docker-compose.langfuse.yml ~/langfuse/docker-compose.yml
cd ~/langfuse
docker compose up -d

# Verify (6 containers)
docker ps --format 'table {{.Names}}\t{{.Status}}'
```

Expected containers: `langfuse-web`, `langfuse-worker`, `postgres`, `clickhouse`, `redis`, `minio`.

Nginx proxies this at `:14002` (prefix + 002).

### 18. Set Up fail2ban (Security)

```bash
# Install
sudo apt-get install -y fail2ban

# Copy Hermes Cortex badbots filter
sudo cp ~/hermes-cortex/ops/install/deploy/nginx/nginx-badbots.conf \\
 /etc/fail2ban/filter.d/nginx-badbots.conf

# Create jail
sudo tee /etc/fail2ban/jail.d/nginx-badbots.local << 'JAIL'
[nginx-badbots]
enabled = true
port   = http,https
filter  = nginx-badbots
logpath = /var/log/nginx/access.log
maxretry = 1
bantime = 86400
findtime = 86400
JAIL

# Start
sudo systemctl enable --now fail2ban
sudo fail2ban-client status
```

This bans IPs scanning for archive files (zip, tar.gz, etc.) on first hit, 24-hour ban.

## Docker Without sudo Patterns

When the user is not in the docker group (permission denied on /var/run/docker.sock), use `sg docker -c` as a temporary workaround:

```bash
sg docker -c "docker compose up -d"
sg docker -c "docker ps"
```

This runs the command with the docker group's supplementary group credentials without requiring a new login shell. For permanent access, add the user to the docker group:

```bash
sudo usermod -aG docker <username>
```

Then log out and back in (or `newgrp docker` in the user's terminal). The `newgrp docker` session change does NOT propagate to the Hermes agent's shell — it only affects the user's own interactive shell.

**Pre-existing concern:** The security scanner flags `usermod -aG docker` as a security concern. This is an intentional architecture decision — the user should be informed that Docker group access is equivalent to root access on the machine (it allows container escape).`
