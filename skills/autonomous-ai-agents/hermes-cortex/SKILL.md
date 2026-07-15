---
name: hermes-cortex
description: Install, configure, and maintain Hermes Cortex — the observability and knowledge layer for Hermes Agent (Ollama, gbrain, Langfuse, Cortex Dashboard, nginx, launchd services, Hermes plugins, offline code assistant, offline content auto-update).
tags: [setup, installation, ollama, gbrain, langfuse, dashboard, nginx, launchd, macos, plugins, docker-compose, offline, code-assistant, rag, bible, hymns]
related_skills: [hermes-agent, docker-compose-common-issues]
---

# Hermes Cortex Setup

Hermes Cortex is the local AI infrastructure layer that provides:
- **Ollama** — Local LLM inference server
- **gbrain** — Postgres-native personal knowledge base with hybrid RAG search
- **Launchd services** — Persistent daemons for Ollama and gbrain sync
- **Hermes plugins** — `/brain` slash command for knowledge queries

## Installation

### Prerequisites

```bash
# Verify Bun is installed (required for gbrain)
bun --version

# Verify macOS (launchd required)
uname -s  # Should return "Darwin"
```

### Run the Installer

```bash
git clone https://github.com/fleet-operator/hermes-cortex.git ~/hermes-cortex
cd ~/hermes-cortex
bash install.sh
```

**Idempotent** — safe to re-run. Skips already-installed steps.

The installer runs **13 steps**:

| Step | Component | What it does |
|------|-----------|--------------|
| 1 | Ollama | Install via Homebrew, configure launchd service |
| 2 | Bun | JavaScript runtime for gbrain |
| 3 | gbrain | Knowledge brain CLI (from GitHub, NOT npm) |
| 4 | Brain directories | MECE-organized knowledge sources (`~/brain/`) |
| 5 | gbrain sources & sync | Auto-sync every 2 minutes via launchd |
| 6 | Langfuse | Docker Compose stack (6 containers: langfuse-web, langfuse-worker, postgres, redis, clickhouse, minio) with auto-generated secrets |
| 7 | Cortex Dashboard | Flask app + launchd service |
| 8 | nginx | Reverse proxy (SSL or local-only mode) |
| 9 | Hermes gbrain plugin | `/brain` slash command files |
| 10 | Hermes scripts | heartbeat.py, memory-to-brain-sync.py, etc. |
| 11 | Enable plugin | Add gbrain-command to Hermes config |
| 12-13 | Summary | Next steps prompt for cron job setup |

**What gets installed:**

| Component | Port | Purpose |
|-----------|------|---------|
| Ollama | 11434 | Local LLM serving |
| gbrain | — | Knowledge brain (Postgres + pgvector) |
| Langfuse | 3000 | LLM observability (Docker) |
| Cortex Dashboard | 8901 | System health + Langfuse companion |
| ClickHouse (Langfuse) | 8123/9000 | Analytics DB for Langfuse v3 |
| nginx | 11002, 11003 | Reverse proxy for external access |

### Script Deployment Architecture

Hermes Cortex uses a **two-directory deployment model**:

| Directory | Purpose | Managed by |
|-----------|---------|-----------|
| `~/.hermes-cortex/scripts/` | **Canonical runtime location** — all cortex scripts deployed here | `cortex-update.sh` register map |
| `~/.hermes/scripts/` | **Cron resolution** — Hermes Agent cron scheduler looks here | Symlinks → `~/.hermes-cortex/scripts/` |

**How scripts flow:** Repo source → `cortex-update.sh --force-all` → `~/.hermes-cortex/scripts/` → symlink → `~/.hermes/scripts/`. Do NOT manually copy scripts to `~/.hermes/scripts/` — always use `cortex-update.sh` to deploy, then create symlinks.

**To add a new cortex script:**
1. Add `register "ops/path/to/script" "${HERMES_HOME}/scripts/name"` to `cortex-update.sh`
2. Run `bash ~/.hermes-cortex/scripts/cortex-update.sh --force-all`
3. Create symlink: `ln -sf ~/.hermes-cortex/scripts/name ~/.hermes/scripts/name`
4. Register in `install-crons.sh` if it's a cron script

**Cleanup of stale duplicates:** If both `~/.hermes/scripts/` and `~/.hermes-cortex/scripts/` have a copy of the same file, replace the `~/.hermes/scripts/` copy with a symlink:
```bash
rm ~/.hermes/scripts/<file> && ln -sf ~/.hermes-cortex/scripts/<file> ~/.hermes/scripts/<file>
```
This was done for 42 files in June 2026. Any future cortex-update maintenance should follow the same pattern — never leave stale regular-file copies in `~/.hermes/scripts/`.

**Cron job script resolution:** The cron scheduler resolves scripts from `HERMES_HOME/scripts/` (`~/.hermes/scripts/`), resolving symlinks via `.resolve()`. The `install-crons.sh` function checks `SCRIPTS_DIR="${HOME}/.hermes-cortex/scripts"` when verifying script existence during cron creation.

**External access (via nginx):**
- Langfuse: `https://your-domain.com:11002` (TLS + basic auth, upstream `127.0.0.1:3000`)
- Cortex Dashboard: `https://your-domain.com:11003` (TLS + basic auth)

### Verify Installation

```bash
# Ollama health
curl -s http://127.0.0.1:11434/api/tags | jq .

# gbrain CLI
~/.bun/bin/gbrain --version

# gbrain health
~/.bun/bin/gbrain doctor --fast

# gbrain sources
~/.bun/bin/gbrain sources list

# Langfuse (Docker) — v3 health endpoint
docker ps | grep langfuse
curl http://localhost:3000/api/public/health

# Cortex Dashboard
curl http://localhost:8901/api/health
launchctl list | grep cortex-dashboard

# nginx
nginx -t
brew services list | grep nginx

# Launchd services
launchctl list | grep -E "(ollama|gbrain|cortex)"

# Hermes plugin
hermes plugins list | grep gbrain
ls -la ~/.hermes/plugins/gbrain-command/
```

### Post-Install Verification

After the basic health checks pass, run these deeper verifications to confirm gbrain is actually indexing content — not just registered:

```bash
# Run the brain bootstrap health check
bash scripts/bootstrap-brain.sh --check-only
# Look for: "X source(s) have indexed pages"
# If ALL show "0 pages indexed", brain directories are empty — add .md files

# Run the full heartbeat report
python3 scripts/heartbeat.py --report
# Expected: Overall OK or DEGRADED with actionable items

# Check memory budget
bash scripts/check-memory-budget.sh --report
# If >85%, run the pointer pattern to compress entries

# Verify gbrain has actual indexed pages per source
gbrain sources list | grep -v "0 pages"
# Should show at least one source with >0 pages
```

**Why this matters:** gbrain sources can be registered and "healthy" but have zero indexed pages. The `bootstrap-brain.sh --check-only` script detects this condition. If all sources show 0 pages, the `/brain` command returns nothing useful regardless of how much content exists in brain directories.

## Built-in Health Check

After install, the simplest readiness check is:

```bash
bash ~/.hermes/scripts/cortex-health.sh
```

This produces a single-pane report covering Ollama, Langfuse, gbrain sources,
gbrain sync daemon, memory sync freshness, Cortex Dashboard, and disk usage.
Exits with:
- **0** (HEALTHY) — all green
- **1** (DEGRADED) — non-critical issues like stale brain sources
- **2** (CRITICAL) — core services down

Also supports `--json` for programmatic consumption and `--watch`
(auto-recheck every 30s).

For deeper inspection, run the systematic audit below.

### 1. Cross-Reference Scripts

The installer embeds several utility scripts inside `install.sh` via heredocs. These
**diverged** from the standalone versions in the repo. Compare them:

```bash
# Check if heartbeat.py matches the repo version
diff <(sed -n '/^cat > "$HEARTBEAT_PATH" <<'"'"'HEARTBEAT'"'"'/,/^HEARTBEAT$/p' ~/hermes-cortex/install.sh | tail -n +2 | head -n -1) ~/.hermes/scripts/heartbeat.py

# Check if memory-to-brain-sync.py matches the repo version
diff <(sed -n '/^cat > "$M2B_PATH" <<'"'"'M2BPY'"'"'/,/^M2BPY$/p' ~/hermes-cortex/install.sh | tail -n +2 | head -n -1) ~/.hermes/scripts/memory-to-brain-sync.py
```

If either shows differences, the installed script is stale or the installer
has drifted. Copy the repo version over the installed one:
```bash
cp ~/hermes-cortex/scripts/heartbeat.py ~/.hermes/scripts/heartbeat.py
cp ~/hermes-cortex/scripts/memory-to-brain-sync.py ~/.hermes/scripts/memory-to-brain-sync.py
```

### 2. Verify the Sync Daemon / Autopilot Relationship

gbrain runs two launchd daemons — know which one matters:

- **`com.gbrain.autopilot`** — Self-maintaining brain daemon. Handles sync, extract, embed, lint, and backlinks in a 150s internal loop. This is the **primary** daemon.
- **`com.gbrain.sync-watch`** — Custom bash script polling `gbrain sync` every 120s. **Redundant** when autopilot runs.

**Why sync-watch fails:** autopilot holds the exclusive lock; sync-watch crashes every cycle because it can't connect while the autopilot is running.

**If autopilot is healthy, disable sync-watch:**
```bash
launchctl bootout gui/$(id -u)/com.gbrain.sync-watch 2>/dev/null || true
mv ~/Library/LaunchAgents/com.gbrain.sync-watch.plist{,.disabled}
mv ~/.gbrain/sync-watch.sh{,.bak}
```

The sync daemon now uses smart polling — it checks for registered sources
each cycle and only runs if non-default sources exist:

```bash
launchctl list | grep com.gbrain.sync-watch
# Should show PID (running), not "-" (stopped)

# Tail the log to see the polling pattern
tail -5 ~/.gbrain/sync-watch.log
# Expected: periodic sync cycles or "No non-default sources registered — skipping"
```

**Important:** `cortex-update.sh`'s `restart_gbrain_sync` must call `launchctl bootout` BEFORE
removing `sync-watch.sh`. Without bootout, launchd KeepAlive keeps the old process alive,
and `install-gbrain-sync.sh` sees "already running" and skips regenerating the script.
If the sync daemon's PID is unchanged after a cortex update, the old script is still in
memory and the update didn't actually take effect. See "Critical Pitfalls" below for the
full pattern.

No configuration fix needed — Moses patched this in the installer and cortex-update.sh. 

### 3. Verify cortex-update.sh covers all deployed files

The update script uses a `register()` function to map repo paths → installed paths.
Only registered files get auto-deployed when changed. See `references/cortex-update-deployment-map.md`
for the full current map (core scripts, self-remediation, offline tools, dashboard, agent inbox, templates, langfuse).

**New file additions:** When adding a new script to the repo, add a `register()` line to `cortex-update.sh`
(ops/scripts/cortex-update.sh) so it gets auto-deployed on next update. Files in `scripts/` (not `ops/scripts/`)
need `scripts/` prefix in the source path, e.g. `register "scripts/weekly-auto-fix.py"`.

See `references/cortex-update-deployment-map.md` for the complete map, update modes (delta/force/status),
the `restart_gbrain_sync` bootout pitfall, and the macOS sha256sum→shasum fallback.

### 4. Verify Langfuse Containers

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep langfuse
```

Expected: 6 containers (langfuse-web, langfuse-worker, postgres, redis, clickhouse, minio),
all healthy. If none exist, Langfuse was never deployed or Docker Desktop isn't running.

### 5. Check Every gbrain Source Has Indexed Pages

```bash
gbrain sources list | grep -v "0 pages" | grep -v "^$"
gbrain sources list | grep "0 pages"
```

Sources showing "0 pages, never synced" are registered but empty. They need content
before the sync daemon has anything to index. See "Existing Repo Setup" below.

### 5. Audit the Auto-Update Path

```bash
head -5 ~/.hermes-cortex/offline/auto-update.sh 2>/dev/null || head -5 ~/hermes-cortex/offline/auto-update.sh
grep "^HERMES_DIR\|^OFFLINE_DIR" ~/.hermes-cortex/offline/auto-update.sh 2>/dev/null
```

If the script references `$HOME/hermes-cortex/offline/` (hardcoded path), it breaks
when the repo is cloned somewhere other than `~/hermes-cortex`. The script should
derive its path from its own location or use `~/.hermes-cortex/offline/`.

### 6. Verify Offline Code Index

```bash
ls -la ~/offline/code-index.json 2>/dev/null || ls -la ~/hermes-cortex/offline/code-index.json 2>/dev/null || echo "MISSING — run: offline_code index"
```

If no index exists, the offline code assistant is non-functional. The installer
creates the corpus files but doesn't build the index automatically.

## Critical Pitfalls

### gbrain npm Package Collision

**PROBLEM:** `bun install -g gbrain` or `npm install -g gbrain` installs the WRONG package.

The npm registry has `gbrain@1.3.1` by stormcolor — a dead 2018 GPU JavaScript library with NO CLI binary. This is NOT the knowledge base tool.

**SOLUTION:** Install from GitHub:

```bash
bun install -g github:garrytan/gbrain
```

The real gbrain (garrytan/gbrain, 20.9k stars) is a Postgres-native personal knowledge base with hybrid RAG search, self-wiring knowledge graphs, and synthesis. It must be installed from GitHub, not npm.

**VERIFICATION:** After install, confirm:
```bash
gbrain --version  # Should return version like "gbrain 0.42.25.0"
which gbrain      # Should return ~/.bun/bin/gbrain
```

### gbrain Source Directory Requirements

**PROBLEM:** gbrain sync fails silently on source directories that aren't git-initialized.

**SOLUTION:** Every source directory must be a git repository before adding to gbrain:

```bash
cd ~/brain/default
git init
git add -A
git commit -m "initial brain state"
```

Then add the source:
```bash
gbrain sources add mybrain --path ~/brain/default --name "mybrain"
```

### Default Source is Special

**PROBLEM:** The `default` gbrain source is built-in (backs pre-v0.17 brain) and cannot have `--path` configured.

**SOLUTION:** Skip the `default` source when configuring. Use a separate source name like `mybrain`:

```bash
# WRONG - will fail silently
gbrain sources add default --path ~/brain/default

# RIGHT - use a different name
gbrain sources add mybrain --path ~/brain/default --name "mybrain"
```

### Sync Daemon (Patched — Smart Polling)

As of Moses' round-2 patches, the sync daemon no longer relies on
`--all --skip default`. Instead it:

1. Runs `gbrain sources list` each cycle to count registered non-default sources
2. If zero sources exist (fresh install), logs `"skipping — run seed-project-brain.sh"` and sleeps
3. Only runs `gbrain sync --all --skip default --no-pull` when sources exist

No more useless polling on an empty install, and no more silent failures
from the built-in `default` source.

**Redundancy with autopilot:** The autopilot (`gbrain autopilot`) is a
self-maintaining daemon that internally handles sync every ~150s alongside
extraction and embedding. When both daemons run, sync-watch fails every cycle
because autopilot holds the exclusive lock. If autopilot is running and healthy,
sync-watch should be disabled (see Section 2 of Built-in Health Check).

**New installs auto-detect:** As of commit 7f2205d, `install-gbrain-sync.sh`
now checks for `com.gbrain.autopilot` before setting up sync-watch and skips
it if autopilot is present. Existing installs with both daemons should disable
sync-watch manually (see Troubleshooting).

### cortex-update.sh restart_gbrain_sync — bootout before rm

**PROBLEM:** When `cortex-update.sh` detects a change to `install-gbrain-sync.sh`,
it calls the `restart_gbrain_sync` function. The original code did:

```bash
rm -f ~/.gbrain/sync-watch.sh
bash ~/.hermes/scripts/install-gbrain-sync.sh
```

This is wrong. launchd KeepAlive keeps the old process alive even after the
script file is deleted. `install-gbrain-sync.sh` checks `service_running()` and
sees PID 30588 (still alive) — so it prints "already running" and **skips
regenerating sync-watch.sh**. The result: the plist points to a deleted file.
If the process ever dies, launchd cannot restart it.

**FIX (applied in commit 893ddc4):** Always `bootout` the service before removing
the script:

```bash
launchctl bootout gui/$(id -u)/com.gbrain.sync-watch 2>/dev/null || true
sleep 1
rm -f ~/.gbrain/sync-watch.sh
bash ~/.hermes/scripts/install-gbrain-sync.sh
```

**Verification:** After a cortex update, check that sync-watch.sh exists and has a
new PID:

```bash
ls -la ~/.gbrain/sync-watch.sh       # must exist
launchctl list com.gbrain.sync-watch | grep PID  # should be different from before
grep "skip default" ~/.gbrain/sync-watch.sh  # confirm --skip default is present
```

### nginx zone-defs duplicate after --force-all

**PROBLEM:** Running `cortex-update.sh --force-all` deploys `hermes-zone-defs.conf`
(which defines `limit_req_zone`, `limit_conn_zone`, and `map` blocks). If the main
`nginx.conf` already defines the same zones from a previous setup, nginx fails with:
```
nginx: [emerg] limit_req_zone "general" is already bound to key "$binary_remote_addr"
```

**DIAGNOSE:**
```bash
nginx -t 2>&1 | grep "already bound"
grep limit_req_zone /opt/homebrew/etc/nginx/nginx.conf /opt/homebrew/etc/nginx/hermes-zone-defs.conf
```

**FIX:** Comment out the zone definitions in `nginx.conf` — `hermes-zone-defs.conf` is the
canonical source (included by `hermes-services.conf`):
```bash
sed -i '' 's/^    limit_req_zone /    #limit_req_zone /' /opt/homebrew/etc/nginx/nginx.conf
sed -i '' 's/^    limit_conn_zone /    #limit_conn_zone /' /opt/homebrew/etc/nginx/nginx.conf
nginx -t && nginx -s reload
```

**PREVENT:** After any `--force-all` update, always run `nginx -t`. If it fails with
"already bound", apply the fix above. The zone-defs file is the single source of truth.

### Loop-Governance Module — Setup Pitfalls

The loop-governance module (`core/governance/`) was added for TDD cycle scoring. First-time setup must account for these issues:

**1. macOS default bash (3.2) lacks `declare -A`**

The `setup.sh` script uses `declare -A` (associative arrays, bash 4+). macOS ships bash 3.2. This produces:
```
declare: -A: invalid option
```
The setup still completes because the error is non-fatal. Scripts are copied correctly despite this warning. If needed, install bash 5 via Homebrew: `brew install bash`.

**2. Symlink targets use underscores, not hyphens**

The repo files are named with underscores (`score_cycle.py`, `loop_feedback.py`, `loop_config.py`, `auto_apply.py`) but the `~/.local/bin/` wrappers are named with hyphens (`score-cycle`, `loop-feedback`, etc.). When creating symlinks, point to the underscore file:

```bash
# CORRECT
ln -sf ~/hermes-cortex/core/governance/score_cycle.py ~/.local/bin/score-cycle
ln -sf ~/hermes-cortex/core/governance/loop_feedback.py ~/.local/bin/loop-feedback
ln -sf ~/hermes-cortex/core/governance/auto_apply.py ~/.local/bin/auto-apply
ln -sf ~/hermes-cortex/core/governance/loop_config.py ~/.local/bin/loop-config

# WRONG — file doesn't exist
ln -sf ~/hermes-cortex/core/governance/score-cycle.py ~/.local/bin/score-cycle  # NO
```

If you symlink to a nonexistent target, bash will follow the dead symlink when using `cat >` and create a stub file at the target path. This corrupts the source file. Verify all targets exist:
```bash
for f in score-cycle loop-feedback auto-apply loop-config; do
  target=$(readlink ~/.local/bin/$f)
  [ -f "$target" ] && echo "✅ $f" || echo "❌ $f -> $target MISSING"
done
```

**3. Register the MCP server for agent access**

After running `setup.sh`, register the loop-governance MCP server so agents can use `cache_search`, `cycle_query`, `feedback_accept`, etc. as MCP tools instead of CLI:

```bash
hermes mcp add \
  --command $HOME/.hermes/mcp-venv/bin/python3 \
  --args ~/hermes-cortex/runtime/mcp-servers/loop-gov-mcp.py \
  loop-governance
```

The MCP server exposes 7 tools: `cache_search`, `config_show`, `config_set`, `cycle_query`, `cycle_stats`, `feedback_accept`, `feedback_override`. These are the primary interface for agents -- the CLI (`score-cycle`, `loop-feedback`) is the fallback for pre-commit hooks and scripts.

**Pitfall — config path:** The MCP server's `args` path in `~/.hermes/config.yaml` must point to the actual file. If hermes-cortex was cloned to a different path than `~/hermes-cortex/`, update the args. A stale path (pointing to a non-existent file) causes MCP tool failures with no visible error -- the process starts but runs old code.

**Verification:** After registering, run `hermes mcp list`. The loop-governance server should show `✓ enabled` with 7 tools. If MCP tools return "Error: no such column", kill stale `loop-gov-mcp.py` processes and let Hermes restart them.

**4. AGENTS.md rule #10 — Score every change (non-negotiable)**

After every change (code, config, script, or deployment), log it to the loop-governance DB. Two paths:

**Path A — MCP tools (for agents):**
- Before coding: `mcp_loop_governance_cache_search(query="task description")`
- After change: `mcp_loop_governance_cycle_query(task_id="<task>")`
- Provide feedback: `mcp_loop_governance_feedback_accept(cycle_id=N)` or `feedback_override(...)`

**Path B — CLI tools (for hooks/scripts):**
```bash
score-cycle --task <task-id> --cycle <N> --code-file <file> --prev-code-file <file> --pass-pct <pass-rate>
``` This applies to ALL changes — not just TDD cycles. For config/IT changes with no tests, pass `--pass-pct 100` if verification succeeded.

```bash
score-cycle --task <task-id> --cycle <N> --code-file <file> --prev-code-file <file> --pass-pct <pass-rate>
```

**Scoring guidelines by change type:**

| Change Type | `--test-file` | `--pass-pct` |
|---|---|---|
| Code change (TDD cycle) | Test file | Actual test pass rate |
| Config/IT change | N/A (omit) | 100 if verification passed, 0 if failed |
| Script edit | Any invocation that proves it works | 100 if ran without error |
| Deployment | Health check endpoint or proof of life | 100 if healthy |

If the system's decision was wrong, use `loop-feedback override <id> --note "..."`.

**Three-layer enforcement (see README.md for full docs):**

| Layer | What | How to install | Bypass |
|-------|------|---------------|--------|
| Pre-commit hook | Runs `score-cycle` on every `git commit` | `bash ~/.hermes-cortex/scripts/install-score-hook.sh --all` | `SKIP_SCORE=1` |
| SOUL.md directive | Rule in every Hermes session's system prompt | Edit `~/.hermes/SOUL.md` (add Mandatory Directives section) | Remove the directive |
| Cron auditor | Scans every 6h for unscored changes | Auto-created by `install-crons.sh` | N/A |

**Dogfood your own rules:** When you introduce a new rule or process that mandates scoring, immediately run `score-cycle` on your own changes to validate the tooling works end-to-end. This catches missing shebangs, Python version mismatches, scoring calibration gaps, and feedback CLI tooling issues before they hit production. The user will call you out if you mandate something and don't do it yourself — it erodes trust in the rule.

**Deployment convention:** New enforcement scripts must be registered in `cortex-update.sh` via `register()`. They deploy to `~/.hermes-cortex/scripts/` — the cron scheduler resolves scripts from there via `SCRIPTS_DIR="${HOME}/.hermes-cortex/scripts"`. Do NOT manually copy to `~/.hermes/scripts/`; use `cortex-update.sh --force-all` to deploy properly.

**Verification:** Run `bash ~/hermes-cortex/core/governance/verify.sh` — expects 14/14 passed, 0 warnings, 0 failures.

**Template for new projects:** Copy the standalone template from the hermes-cortex repo's `docs/templates/AGENTS-loop-governance.md` to add loop-governance rules to any project's AGENTS.md. See skill reference `agents-loop-governance-template.md`.

**4. score-cycle/loop-feedback shebangs — Python 3.12+ required (macOS default is 3.9)**

The `score-cycle` and `loop-feedback` entry points use `#!/usr/bin/env python3`. macOS ships Python 3.9 which doesn't support PEP 604 (`str | None` syntax). All Hermes projects now require 3.12+.

Ensure the shebang points to a 3.12+ interpreter:

```bash
# Use uv-managed 3.12 (default for Hermes projects)
ls ~/.local/bin/python3.12

# Or pyenv-managed 3.12+
ls ~/.pyenv/versions/ | grep '^3\\.1[2-9]'

# Update shebang:
sed -i '' '1s|#!/usr/bin/env python3|#!/Users/\$(whoami)/.local/bin/python3.12|' \\
  ~/hermes-cortex/core/governance/score_cycle.py \
  ~/hermes-cortex/core/governance/loop_feedback.py
```

When deploying to a new machine, verify `python3 --version` resolves to 3.12+. The `install.sh` probes `python3 python3.12` (plus any available 3.13/3.14) in order and selects the first 3.12+ with sqlite3 extension support.

**5. Cron prompt URLs must use external inbox address**

After a cortex update that adds or modifies cron jobs, verify the cron prompt doesn't contain the old internal URL (`127.0.0.1:8903`). The external URL is `https://your-domain.com:13004`. Check:

```bash
hermes cron list | grep "inbox-processor\\|inbox-watchdog"
# Verify prompt/preview doesn't say 127.0.0.1:8903
```

### cortex-update.sh offline_knowledge symlink blocks deploy

**PROBLEM:** `cortex-update.sh --force-all` maps `~/.hermes-cortex/bin/offline_knowledge` from the repo's `ops/offline/offline_knowledge.py`. If the `~/.hermes-cortex/bin/` directory does not exist, the symlink creation fails with:
```
ln: $HOME/.hermes-cortex/bin/offline_knowledge: No such file or directory
```
This is a **non-fatal error by itself**, but if `cortex-update.sh` runs with `set -e` (exit on error), the script stops immediately. Any `register()` lines AFTER the broken symlink — including newly added scripts — never get deployed.

**FIX:** Ensure the target directory exists before running cortex-update:
```bash
mkdir -p ~/.hermes-cortex/bin
bash ~/.hermes-cortex/scripts/cortex-update.sh --force-all
```

**PREVENT:** When registering a new file that creates a symlink in `cortex-update.sh`, add a `mkdir -p` for the target directory before the `ln -sf` command, or use `ln -sf ... 2>/dev/null || true` to prevent a failed symlink from blocking the rest of the update.

### Delta engine skips after manual git pull
before invoking `cortex-update.sh`, the delta engine sees `old_commit == new_commit`
and exits with "Already up to date". Files that actually changed in the repo don't
get deployed because the commit comparison passes through.

**FIX:** Use `--force-all` to bypass commit comparison and checksum every file:
```bash
bash ~/.hermes/scripts/cortex-update.sh --force-all
```

**PREVENT:** Either (a) let `cortex-update.sh` handle its own `git pull` instead of
pulling manually, or (b) always use `--force-all` after any manual pull.

### Launchd plist paths — shell/CORTEX_HOME variables NOT expanded

**PROBLEM:** `launchd` (via `launchctl load`) does NOT expand shell variables like
`$HOME` or `CORTEX_HOME` in plist files. Using them in `ProgramArguments`,
`WorkingDirectory`, `StandardOutPath`, or `StandardErrorPath` causes the job to
fail with **EX_CONFIG (exit code 78)** immediately on load.

This affects ALL cortex plists: `com.hermes.health-server.plist`,
`com.hermes.cortex-dashboard.plist`, `com.hermes.agent-inbox.plist`, and any
agent-created plists.

**DIAGNOSE:**
```bash
launchctl list com.hermes.health-server
# Look for: "LastExitStatus" = 78;  (EX_CONFIG)
# Or: paths showing as literal "$HOME/..." instead of "/home/<username>/..."
```

**FIX:** Use hardcoded absolute paths in ALL plist key values:

```xml
<!-- WRONG — launchd sees the literal string "$HOME" -->
<string>$HOME/.hermes/scripts/health-server.py</string>

<!-- RIGHT — hardcoded absolute path -->
<string>$HOME/.hermes/scripts/health-server.py</string>
```

**Affected files in the cortex repo (fixes applied in commit e1ff1c7):**
- `ops/scripts/com.hermes.health-server.plist` — paths used `$HOME`
- `ops/services/dashboard/com.hermes.cortex-dashboard.plist` — paths used `CORTEX_HOME`

**PREVENT:** Before creating or modifying any launchd plist, verify every path is
a hardcoded absolute path for the target user. The `~/` tilde prefix does work
(launchd expands it), but `$HOME` and any custom env var do NOT. When in doubt
use `/Users/<username>/` explicitly.

**VERIFICATION:** After fixing, confirm the job loads and shows expanded paths:
```bash
launchctl load ~/Library/LaunchAgents/com.hermes.health-server.plist
launchctl list com.hermes.health-server
# Expected: "Program" = "/home/<username>/.hermes/..."  (expanded, not literal "$HOME")
# Expected: "LastExitStatus" = 0
```

### Python 3.12 Default — Mandatory Pre-Merge Version Check

Python 3.12 is now the **explicit default** for all Hermes Cortex projects. All scripts,
cron jobs, and tooling assume 3.12+ with PEP 604 union syntax (`str | None`), PEP 695
type-parameter syntax, and `match`/case statements — all natively supported.

macOS ships Python 3.9 as the system default, so a **version check is mandatory** before
deploying any .py file to production (cron jobs, install scripts, MCP servers):

```bash
# Quick version check — must be 3.12+
python3 --version  # Expected: Python 3.12+
python3 -c "import sys; assert sys.version_info >= (3, 12), 'Need 3.12+'"
```

**The uv/pyenv-managed Python is the canonical interpreter.** Install or locate it:

```bash
# uv-managed 3.12 (preferred)
ls ~/.local/bin/python3.12

# pyenv-managed
pyenv install 3.12  # or 3.13
pyenv global 3.12

# Homebrew (fallback)
brew install python@3.12
```

**Verification checklist before deploying any new .py script:**
1. ✅ `python3 --version` resolves to 3.12+ (not macOS 3.9)
2. ✅ `python3 -c "compile(open('script.py').read(), 'script.py', 'exec')"` passes
3. ✅ `python3 -c "import script"` passes (no NameError, no missing imports)
4. ✅ `python3 script.py` exits 0 or produces expected output
5. ✅ All module-level function references resolve before their usage point
6. ✅ Script is registered in `cortex-update.sh` MAP if deployed via that path

**What about older scripts?** The repo no longer maintains 3.9 compatibility — scripts that
still use `Optional[str]` or `Union[int, str]` are legacy and should be updated to PEP 604
syntax when touched.

### Installer Script Divergence

**PROBLEM:** Several utility scripts are embedded inside `install.sh` as heredocs.
These are copies of the standalone versions in `scripts/` but can **drift apart**
when one is updated without updating the other.

Confirmed divergences as of v1.0.0:

| Script | Difference | Impact |
|--------|-----------|--------|
| `heartbeat.py` | Embedded version missing `check_memory_sync_freshness()` and `check_service()` | Memory sync staleness not detected; Linux systemd support absent |
| `memory-to-brain-sync.py` | Embedded version writes separate `hermes-memory.md` / `hermes-user.md` files; repo version writes `current.md` + monthly archive with YAML frontmatter | Different output format, different gbrain indexing behavior |

**SOLUTION:** After install, compare and sync:

```bash
# Check heartbeat
diff ~/hermes-cortex/scripts/heartbeat.py ~/.hermes/scripts/heartbeat.py
# If different: cp ~/hermes-cortex/scripts/heartbeat.py ~/.hermes/scripts/heartbeat.py

# Check memory-to-brain
diff ~/hermes-cortex/scripts/memory-to-brain-sync.py ~/.hermes/scripts/memory-to-brain-sync.py
# If different: cp ~/hermes-cortex/scripts/memory-to-brain-sync.py ~/.hermes/scripts/memory-to-brain-sync.py
```

**For repo maintainers:** Every time you update one of these scripts in `scripts/`,
you must also update the heredoc copy inside `install.sh`. The bash `diff` commands
above are the only way to detect drift — add them to CI or a pre-commit hook.

## Project Bootstrapping — seed-project.sh

Hermes Cortex provides `seed-project.sh` to deploy the development harness (AGENTS.md, `.hermes-cortex/` infrastructure, loop-governance scoring, pre-commit hooks, and project skills) to any project.

### Quick Start

```
# Default: merge mode, all components, backup created automatically
bash ~/.hermes-cortex/scripts/seed-project.sh --project=/path/to/project --name="Project Name"

# Preview what would change
bash ~/.hermes-cortex/scripts/seed-project.sh --project=/path/to/project --mode=diff

# Deploy specific components only
bash ~/.hermes-cortex/scripts/seed-project.sh --project=/path/to/project \
  --components=AGENTS.md,.hermes-cortex,pre-commit

# Custom skill set
bash ~/.hermes-cortex/scripts/seed-project.sh --project=/path/to/project \
  --skill-refs=change-test-loop,engineering-approach,save-lesson
```

### Modes

| Mode | Behavior | When to use |
|------|----------|-------------|
| merge (default) | Backup existing, write only changed files (checksum delta). | First seed, routine updates |
| overwrite | Backup existing, then overwrite everything. | Known-clean target |
| diff | Preview. No writes. No backup. | Safety check before running |

### Backup Architecture

Every seed creates a timestamped backup under `.hermes-cortex/.seed-backups/<ts>/`:

```
project/.hermes-cortex/.seed-backups/
├── 20260626_150000-12345/
│   ├── AGENTS.md              ← backed up BEFORE modify
│   ├── .hermes-cortex/         ← excludes .seed-backups/ (circular)
│   ├── .git/hooks/pre-commit
│   └── manifest.json
```

**Restore from latest:** `seed-project.sh --restore=/path/to/project`
**Restore from specific:** `seed-project.sh --restore=/path/to/project@<timestamp>`
**List backups:** `seed-project.sh --list-backups=/path/to/project`

### Components

| Component | What it deploys | Source |
|-----------|----------------|--------|
| AGENTS.md | Templated agent guidelines with project name, date, commit. Includes contract rules 1-11 and loop-gov scoring section. | `docs/templates/AGENTS.seed.md` or custom `--template` |
| .hermes-cortex | Dir structure: sessions/archive/, memory/, skills/ + .gitignore (excludes memory, db, secrets). | Built-in |
| pre-commit | Loop-governance pre-commit hook via install-score-hook.sh | `ops/scripts/pre-commit-score` |
| loop-gov | score-cycle + loop-feedback wrappers in .hermes-cortex/loop-governance/ | Wrapper scripts |
| skills | Selected skills from ~/.hermes/skills/ into project's .hermes-cortex/skills/ | ~/.hermes/skills/ (via symlink) |

### Pitfalls (Discovered During Development)

1. **Functions must `return`, not `exit`.** `exit 0` inside a function kills the entire shell. Only `exit` from top-level main().
2. **`local var=$(cmd)` swallows exit codes.** With `set -e`, split into `local var; var=$(cmd) || true` to preserve error handling.
3. **Circular backup.** Backups live inside `.hermes-cortex/.seed-backups/`. Exclude `.seed-backups/` when copying `.hermes-cortex/` or it tries to copy itself.
4. **Restore must guard against missing data.** Never `rm -rf` the target before confirming the backup source exists. Move aside (never delete), then restore on failure.
5. **Timestamp collisions.** Two seeds in the same second collide. Append `-$RANDOM` to the timestamp.
6. **Template braces must match.** A missing `}` in `{{PLACEHOLDER}}` leaves the placeholder unexpanded.

### Design Principles

**Backup-first:** Every deployment operation (seed, update, restore) creates a backup of any file it modifies. `--no-backup` requires explicit opt-in. The rationale: "I can't tell you how many times I wish I had a backup but didn't."

**Idempotent by default:** SHA256 delta engine only writes changed files. Re-seeding is safe.

**Restore is a first-class operation:** Every deployment tool must have a `--restore` flag. Backups are worthless without a restore mechanism.

### References

- `references/seed-project-bootstrapping.md` — Full reference with usage details, component docs, restore guide
- `docs/templates/AGENTS.seed.md` — AGENTS.md template deployed by seed-project.sh

## Skills Architecture: Three-Layer Model

Hermes Cortex uses a three-layer skill model with different purposes per layer. Understanding this hierarchy is essential for any agent working on the repo.

### The Three Layers

| Layer | Location | Purpose | Managed by |
|-------|----------|---------|-----------|
| **Canonical source** | `~/hermes-cortex/skills/` | Public reusable skills distributed by the installer. These are the curated set — ~40 skills across devops, software-development, MCP, github, etc. | `git push` to repo |
| **Global installed** | `~/.hermes/skills/` | Hermes Agent's primary skill directory (~150 skills). Contains cortex skills + ecosystem skills (apple/, creative/, gaming/, mlops/, testing/, etc.) | `cortex-update.sh sync_skills()` + manual additions |
| **Project overrides** | `~/hermes-cortex/.hermes-cortex/skills/` | Project-specific skill overrides tracked in the repo. Hermes checks this FIRST when working in the hermes-cortex repo, falling back to `~/.hermes/skills/` for anything not found here. These are condensed versions (e.g. 72-line agent-contract vs 990-line global). | Tracked in repo (project-specific) |

### How Skills Flow

```
skills/ (canonical, ~40 skills)
    ↓  cortex-update.sh --force-all: sync_skills() checksums each SKILL.md
~/.hermes-cortex/skills/  →  (symlink)  →  ~/.hermes/skills/ (global, ~150 skills)
                                                    ↑
                                            ~110 ecosystem skills untouched by sync
```

**Key relationship:** `~/.hermes-cortex/skills/` is a symlink → `~/.hermes/skills/`. When `cortex-update.sh` calls `sync_skills()`, it copies from `skills/` to `~/.hermes-cortex/skills/`, the write resolves through the symlink to `~/.hermes/skills/`. Non-cortex skills (apple/, creative/, gaming/, etc.) are completely untouched — `sync_skills()` only overwrites files whose checksums differ from the source.

### Contrast with Script Deployment

Scripts and skills flow in opposite directions:

**Scripts:** `ops/scripts/` → `~/.hermes-cortex/scripts/` → (symlink) → `~/.hermes/scripts/`
**Skills:** `skills/` → `~/.hermes-cortex/skills/` → (symlink resolves to) `~/.hermes/skills/`

Scripts: `~/.hermes-cortex/scripts/` is primary, `~/.hermes/scripts/` is the cron-resolution symlink target.
Skills: `~/.hermes/skills/` is primary (Hermes Agent loads from here), `~/.hermes-cortex/skills/` is the symlink pointing back.

### cortex-update.sh sync_skills()

The `sync_skills()` function in `cortex-update.sh` (lines 442-479) uses a checksum-based delta engine:

```bash
# Called during every --force-all or delta update
# Compares SHA256 of skills/<file> vs installed destination
# Only copies when checksums differ — preserves non-cortex skills
sync_skills() {
  local skill_repo="${REPO_DIR}/skills"
  local skill_dest="${HERMES_HOME}/skills"  # resolves via symlink → ~/.hermes/skills/
  
  while IFS= read -r -d '' skill_file; do
    if needs_update "$skill_file" "$dest"; then
      copy_file "$skill_file" "$dest"
    fi
  done < <(find "$skill_repo" -name "SKILL.md" -type f -print0)
  
  # Also syncs reference files under each skill's references/ directory
  while IFS= read -r -d '' ref_file; do
    if needs_update "$ref_file" "$dest"; then
      copy_file "$ref_file" "$dest"
    fi
  done < <(find "$skill_repo" -path "*/references/*" -type f -print0)
}
```

The delta engine means:
- Only skills in `skills/` are ever touched — ~110 unique ecosystem skills (apple/, creative/, gaming/, mlops/, testing/) are completely safe
- New skills added to `skills/` get installed on next `cortex-update.sh --force-all`
- Updated skill files (checksum changed) get overwritten automatically
- No manual copying needed — reverse direction (repo ← ~/.hermes/skills/) is for when you create a skill in the agent and want to commit it to the repo

### Setup (Applied June 2026)

The symlink was created once:

```bash
# 1. Migrate any unique skills from old .hermes-cortex/skills/ that didn't exist in ~/.hermes/skills/
#    Checked: only mcp-server-building and repo-organization were unique → copied manually

# 2. Remove old directory, create symlink
rm -rf ~/.hermes-cortex/skills
ln -s ~/.hermes/skills ~/.hermes-cortex/skills

# 3. Verify with cortex-update
bash ~/.hermes-cortex/ops/scripts/cortex-update.sh --force-all
# Expected output: "Skills: N updated, M unchanged"
```

### What This Means for Agent Sessions

When an agent works inside the hermes-cortex repo:
1. Hermes checks `.hermes-cortex/skills/` (in the repo) first — these are project-specific overrides
2. Falls back to `~/.hermes/skills/` (global, via symlink) for anything not in the overrides
3. The overrides are intentionally condensed versions — e.g. the 72-line `agent-contract` used when working on hermes-cortex vs the 990-line public version

For agents on other projects (not working in the hermes-cortex repo):
- Only `~/.hermes/skills/` is used (no `.hermes-cortex/skills/` project override exists)
- `cortex-update.sh` keeps these current automatically

## Launchd Services

### Ollama Service

```bash
# Status
launchctl list | grep com.ollama.serve

# Start
launchctl start com.ollama.serve

# Stop
launchctl stop com.ollama.serve

# Logs
tail -f ~/Library/Logs/com.ollama.serve.out
```

### Gbrain Sync Daemon

```bash
# Status
launchctl list | grep com.gbrain.sync-watch

# Start
launchctl start com.gbrain.sync-watch

# Stop
launchctl stop com.gbrain.sync-watch

# Logs
tail -f ~/.gbrain/sync-watch.log
```

## Hermes Plugin

The `/brain` slash command is installed at `~/.hermes/plugins/gbrain-command/`.

**CRITICAL: Enable the plugin after install**

The installer creates the plugin files but does NOT enable it. You must enable it manually:

```bash
hermes plugins enable gbrain-command
```

This takes effect on the next Hermes session. Verify with:
```bash
hermes plugins list | grep gbrain
# Should show "enabled" status
```

**Usage:**
```
/brain <query>
```

**Files:**
- `__init__.py` — Plugin implementation with gbrain query integration
- `plugin.yaml` — Hermes plugin configuration

**Troubleshooting:**
If `/brain` command doesn't work:
1. Check plugin status: `hermes plugins list`
2. If "not enabled": `hermes plugins enable gbrain-command`
3. Start a new Hermes session (`/reset` or restart CLI)

## Hermes Langfuse Tracing Plugin

Hermes Agent ships a built-in Langfuse observability plugin (`observability/langfuse`) that auto-traces every LLM call, tool invocation, and conversation turn. After setting up Langfuse as a Docker server (step 6 of install.sh), you must explicitly enable and configure this plugin — it is NOT auto-activated by the installer.

### Setup

```bash
# Install the Langfuse Python SDK
pip install langfuse
```

### Create an API Key

Option A — Via Langfuse UI: Settings → API Keys (requires catching the ~2s serving window).

Option B — Direct DB insert (recommended when web container cycles):

1. Generate key pair with Python (run from terminal where `bcrypt` is available):
```python
import bcrypt, hashlib, secrets
rand = secrets.token_hex(16)
sk = f"sk-lf-titus-{rand}a1b2"
pk = f"pk-lf-titus-{secrets.token_hex(16)}"
bc = bcrypt.hashpw(sk.encode(), bcrypt.gensalt(rounds=11)).decode().replace("$2b$", "$2a$")
```

2. Write the SQL and execute via `docker cp` (avoids shell `$` expansion):
```bash
docker cp /tmp/insert-key.sql langfuse-postgres-1:/tmp/
docker exec langfuse-postgres-1 psql -U postgres -f /tmp/insert-key.sql
```

### Set Environment Variables

Write to `~/.hermes/.env` via Python (avoids shell `$` expansion in the secret key):

```python
lines = [
    f"HERMES_LANGFUSE_PUBLIC_KEY={pk}",
    f"HERMES_LANGFUSE_SECRET_KEY={sk}",
    "HERMES_LANGFUSE_BASE_URL=http://localhost:3000",
    "HERMES_LANGFUSE_ENV=local",
]
with open(os.path.expanduser("~/.hermes/.env"), "a") as f:
    for line in lines:
        f.write(line + "\n")
```

### Enable the Plugin

```bash
hermes plugins enable observability/langfuse
# Takes effect on next Hermes session
```

### Verification

- `hermes plugins list | grep langfuse` should show "enabled"
- After a few conversation turns, traces appear in Langfuse UI (http://localhost:3000)

The langfuse SDK queues traces and retries on failure. The web container's restart cycle doesn't lose data — the SDK flushes during brief UP windows.

## Post-Update Verification

Hermes Agent ships a built-in Langfuse observability plugin (`observability/langfuse`) that auto-traces every LLM call, tool invocation, and conversation turn. After setting up Langfuse as a Docker server (step 6 of install.sh), you must explicitly enable and configure this plugin — it is NOT auto-activated by the installer.

### Setup

```bash
# 1. Install the Langfuse Python SDK
pip install langfuse

# 2. Create a Langfuse API key
#    Option A: Via Langfuse UI at Settings → API Keys (requires catching the ~2s window)
#    Option B: Via direct DB insert (when web container cycles restart)
```

**Option B — Direct DB insert (recommended):**

```bash
# Generate key pair
python3 -c "
import bcrypt, hashlib, secrets
rand = secrets.token_hex(16)
sk = 'sk-lf-titus-' + rand
pk = 'pk-lf-titus-' + secrets.token_hex(16)
bc = bcrypt.hashpw(sk.encode(), bcrypt.gensalt(rounds=11)).decode().replace('\$2b\$', '\$2a\$')
key_id = 'cmqkey-' + secrets.token_hex(8)
print(f'PK: {pk}')
print(f'SK: {sk}')
print(f'KEY_ID: {key_id}')
print(f'BCRYPT: {bc}')
" > /tmp/key-data.txt

# Insert into DB
eval "$(cat /tmp/key-data.txt | sed 's/ //g')"
docker exec langfuse-postgres-1 psql -U postgres -c "
  INSERT INTO api_keys (id, created_at, note, public_key, hashed_secret_key, 
    display_secret_key, project_id, organization_id, scope, is_in_app_agent_key)
  VALUES (
    'KEY_ID_PLACEHOLDER', now(), 'Hermes Agent Tracing', 
    'PK_PLACEHOLDER', 'BCRYPT_PLACEHOLDER', 
    'sk-lf-titus-...LAST4', 'default-project', 
    (SELECT id FROM organizations LIMIT 1), 'PROJECT', false
  );
"
```

**NOTE:** The `$` in bcrypt hashes get mangled by shell expansion. Always use `docker cp` with a `.sql` file to insert the API key, not inline `docker exec -c`. See Troubleshooting → bcrypt Password Hash via docker cp for the safe pattern.

### 3. Set Environment Variables

```bash
# Add to ~/.hermes/.env (via Python to avoid shell $ expansion)
python3 -c "
import os, base64
lines = [
    'HERMES_LANGFUSE_PUBLIC_KEY=pk-lf-titus-YOUR_PUBLIC_KEY',
    'HERMES_LANGFUSE_SECRET_KEY=sk-lf-titus-YOUR_SECRET_KEY',
    'HERMES_LANGFUSE_BASE_URL=http://localhost:3000',
    'HERMES_LANGFUSE_ENV=local',
    'HERMES_LANGFUSE_RELEASE=1.0.0',
]
with open(os.path.expanduser('~/.hermes/.env'), 'a') as f:
    for line in lines:
        f.write(line + chr(10))
"
```

### 4. Enable the Plugin

```bash
hermes plugins enable observability/langfuse
# Takes effect on next Hermes session
```

### Verification

The plugin takes effect on the **next Hermes session**. To verify it's working:

```bash
# Check plugin status
hermes plugins list | grep langfuse
# Should show "enabled"

# After a few conversation turns, check Langfuse for new traces
# Data appears at http://localhost:3000 (during the ~2s serving window)
```

### Important Notes

- The plugin sends traces for every LLM call via the langfuse Python SDK. The SDK queues traces and retries on failure, so brief server downtime doesn't lose data.
- The `BASE_URL` must point to `http://localhost:3000` for local setups. For remote access via nginx, use the external URL (e.g., `https://your-domain.com:11002`).
- The plugin is bundled with Hermes in `plugins/observability/langfuse/`. It requires the `langfuse` pip package at runtime (installed in step 1).

## Post-Update Verification

After pulling latest cortex code and running `cortex-update.sh`, verify the update actually took effect:

### 1. Check Deployment Map Completeness

New files in `scripts/` (repo root) are NOT auto-registered unless they have a `register()` line in `cortex-update.sh`. Files in `ops/scripts/` are only registered if explicitly listed. Run:

```bash
cd ~/hermes-cortex
git diff --name-only HEAD~1..HEAD | grep "^scripts/\|^ops/"
```

Then cross-reference against the register map in `cortex-update.sh`:

```bash
grep "^register " ~/.hermes/scripts/cortex-update.sh | grep -o '"[^"]*"' | head -80
```

git diff --name-only HEAD~1..HEAD | grep "^scripts/\|^ops/"

**Common misses:** scripts at `scripts/` root level (e.g. `scripts/moses-inbox-remediate.sh`), new skill directories under `skills/` (these ARE auto-synced by `sync_skills()` — no register line needed).

### 2. Test Companion Scripts

New pipeline components often include companion scripts. Verify they run on the
canonical 3.12+ interpreter before deploying:

```bash
# Quick syntax and import check
python3 -c "compile(open('<new-script>.py').read(), '<new-script>.py', 'exec')"
python3 -c "import sys; sys.path.insert(0, '.'); import $(basename <new-script> .py)"

# Run the new script — expected: silent exit or [] (no pending items)
bash ~/.hermes/scripts/<new-script>.sh

# For .py scripts: verify import works and exit code matches watchdog pattern
python3 -c "import sys; sys.path.insert(0, '$HOME/.hermes/scripts'); import <script_basename>"
python3 ~/.hermes/scripts/<script>.py
echo "Exit: $?"  # Should be 0
```

### 3. Verify New Cron Jobs Were Created

New pipelines often need new cron jobs that aren't auto-created by cortex-update.sh:

```bash
hermes cron list | grep <pipeline-name>
```

If missing, create them per the new skill's setup instructions. Common patterns:
- **no_agent watchdog** — `--schedule "every 10m" --script "<name>.sh" --no-agent --deliver origin`
- **LLM-driven processor** — `--schedule "every 10m" --skills "<skill-name>" --enabled-toolsets terminal,file,web --deliver origin`

### 4. Check for Stale System-Alert / Service-Recovery Scripts

The most common drift: installed watchdog scripts lag behind the repo. The `--force-all` flag catches these, but verify:

```bash
diff ~/hermes-cortex/ops/scripts/health/system-alert-watchdog.py ~/.hermes/scripts/system-alert-watchdog.py
diff ~/hermes-cortex/ops/scripts/health/service-recovery.py ~/.hermes/scripts/service-recovery.py
```

Zero output = in sync. Any diff means the installed version is stale.

### 5. Report Improvements to Moses

If the update revealed missing registrations, compatibility issues, or bugs, report them to Moses via the git-based inbox immediately (see "Reporting Issues" below).

## Reporting Issues to Moses

**Standing directive:** After every cortex update or install, report any bugs, missing registrations, compatibility issues, or improvement suggestions to Moses. This is not optional — it's how the repo stays healthy.

### Where to Send

Use the git-based agent inbox in the private repo:

```bash
cat > ~/hermes-cortex-private/messages/inbox/$(date -u +%Y%m%d%H%M%S)-titus-to-moses.md << 'EOF'
---
from: titus
subject: <descriptive subject line>
topic: moses
---

<details of issue: what was found, what was fixed locally, any upstream changes needed>
EOF

cd ~/hermes-cortex-private
git add messages/
git commit -m "titus: <summary of report>"
git pull --rebase origin main
git push
```

### What to Report

| Signal | Action |
|--------|--------|
| New file missing from deployment map | Report the filename, what it does, and the register line added |
| macOS/Linux compatibility gap | Report the affected script, the fix applied, and the platform |
| Python 3.12+ requirement issue | Report the script and ensure the interpreter resolves to 3.12+ |
| Hardcoded paths or UIDs | Report the hardcoded value and the dynamic alternative |
| Missing imports | Report the script and the missing import |
| New cron jobs that needed manual creation | Report which crons were created and their schedule |

### Verification

After sending, verify the message landed:

```bash
ls -la ~/hermes-cortex-private/messages/inbox/*titus-to-moses*
```

The `orch-team-messages.sh` cron (every 10m) will pick it up and Moses (or the inbox processor) will process it.

## Maintenance

### Update gbrain

```bash
# Prefer update over reinstall — preserves installed state
bun update -g gbrain

# Verify new version
gbrain --version
```

If `bun update` doesn't find the latest GitHub commit (uncommon — bun resolves correctly from `~/.bun/install/global/package.json`), fall back to force reinstall:

```bash
bun install -g github:garrytan/gbrain --force
```

### Apply migrations

Migrations run **automatically** during `gbrain sync` — you usually don't need to call them separately. After updating gbrain, just sync:

```bash
gbrain sync
```

If sync output shows migration errors, retry explicitly:

```bash
gbrain apply-migrations --yes
```

**If migrations fail:** run `gbrain doctor` to check for wedged migrations, then see "gbrain Migration Failures" in Troubleshooting below.

### Keep cortex-associated skills up to date

```bash
hermes skills check          # Check all installed skills for updates
hermes skills update <name>  # Update a specific skill
```

The `hermes-cortex` repo ships some local skills — these are updated via `git pull` in the repo, not via `hermes skills update`. Only hub/official skills are updated by `hermes skills update`.

### Rebuild Knowledge Index

```bash
gbrain sync --source mybrain --no-pull
gbrain extract --stale
```

### gbrain Source Migration: Merge Sources via Clean Reimport

When you need to move pages from one gbrain source into another (e.g. moving orphaned `default` source pages into a named source with a filesystem path), use the export→wipe→reimport pattern. This is the canonical way to consolidate sources.

**When to use:**
- The `default` source has pages but no `local_path` (and can't be removed)
- You want all pages under a single source backed by disk
- You need to change a source's physical path or source_id

**Workflow:**

```bash
# PGLite upgrade path removed. This system uses Postgres (pgvector).
# See docs/gbrain-postgres-migration.md for migration steps.
echo "PGLite engine upgrade no longer supported — migrated to Postgres"
```
gbrain extract --stale

# 7. Restart daemons
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gbrain.autopilot.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gbrain.sync-watch.plist
```

**Pitfalls:**
- The `default` source is protected — it appears after init but will have 0 pages. It cannot be removed or cleaned up.
- The export script reads `compiled_truth`, not `content` — check the pages table schema first if gbrain version has changed (`SELECT column_name FROM information_schema.columns WHERE table_name = 'pages'`)
- Slugs in the database use underscores (e.g. `sources_docs_testing`). The script converts them to slashes for filesystem paths (e.g. `sources/docs/testing.md`)
- After wipe+reinit, ALL gbrain daemons must be reloaded — they were using the old DB handle

**Verify:**
```bash
gbrain stats                # Should match original page count
gbrain sources list         # mybrain has pages, default is empty
gbrain search "test" --limit 1  # Returns results
```

### gbrain PGLite Recovery

> ~~Removed — this system uses Postgres (pgvector).~~
> PGLite recovery no longer applicable. See [`docs/gbrain-postgres-migration.md`](docs/gbrain-postgres-migration.md).

**Embedding model verification:**
```bash
curl -s http://localhost:11434/api/embeddings \
  -d '{"model":"nomic-embed-text:v1.5","prompt":"test"}' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d[\"embedding\"])}d')"
# Expected: "768d"
```

### Health Check

```bash
# Run the heartbeat script
python3 ~/.hermes/scripts/heartbeat.py

# Check all components
gbrain doctor --fast
curl -s http://127.0.0.1:11434/api/tags

# Verify gbrain sources have indexed pages
bash ~/.hermes/scripts/bootstrap-brain.sh --check-only

# Check memory budget
bash ~/.hermes/scripts/check-memory-budget.sh --report
```

### gbrain Source Management Quick Reference

Useful commands for managing sources day-to-day:

```bash
# List all sources with page counts
gbrain sources list

# Check which source is the active default
gbrain sources current
# Returns something like "source: mybrain  tier: brain_default"

# Set the brain-wide default source (for federated queries)
gbrain sources default mybrain

# Check source status (last sync, embedding coverage)
gbrain sources status

# Detach from stale .gbrain-source in current directory
gbrain sources detach
```

**Source hierarchy (check via `sources current`):**
1. `--source` flag on the command (highest priority)
2. `$GBRAIN_SOURCE` env var
3. `.gbrain-source` dotfile in CWD
4. Brain-level default (set via `sources default`)
5. Seed default (`default` source, lowest priority)

**Cron integration:** The `hermes-cortex-sync` cron job runs these checks automatically every 4 hours on weekdays and reports to Telegram.

## Security Posture

After installation, run a quick security audit to lock down file permissions and verify network exposure.

### File Permission Lockdown

Hermes stores API keys, conversation history, and project data in `~/.hermes/`. Several of these files default to world-readable (0644) and should be restricted to owner-only:

```bash
chmod 600 ~/.hermes/config.yaml
chmod 600 ~/.hermes/.hermes_history
chmod 600 ~/.hermes/kanban.db
chmod 600 ~/.hermes/SOUL.md
chmod 600 ~/.hermes/interrupt_debug.log
chmod 600 ~/.hermes/gateway.lock ~/.hermes/gateway.pid
for f in ~/.hermes/config.yaml.bak.*; do chmod 600 "$f" 2>/dev/null; done
```

Verify everything is 0600 except logs and cache dirs:
```bash
cd ~/.hermes && stat -f "%Lp %N" config.yaml .hermes_history kanban.db SOUL.md auth.json .env
```

### Bind Address Audit

Verify no services are exposed beyond localhost:
```bash
lsof -iTCP -sTCP:LISTEN -P -n 2>/dev/null | grep -v "127.0.0.1\|::1"
```
Expected output: only macOS system processes (ControlCenter, Docker Desktop internal ports, rapportd). No user services should appear.

If a service binds to `0.0.0.0`, fix it in its config (e.g. `app.run(host="127.0.0.1")` for Flask, `--host 127.0.0.1` for Ollama).

### nginx — Local-Only Unload

nginx is only needed for external/public access (TLS reverse proxy). For local-only setups, it's dead weight that can sit in error state with log-permission issues. Unload it:

```bash
launchctl unload ~/Library/LaunchAgents/homebrew.mxcl.nginx.plist
brew services stop nginx
```

If you later want external access, fix the log-permission issue first:
```bash
sudo chown "$(whoami):staff" /opt/homebrew/var/log/nginx/*.log
# then start nginx
brew services start nginx
```

### Restart Resilience Check

All services should survive reboot via launchd `RunAtLoad` or Docker's `restart:always` policy:

```bash
# Verify launchd services
launchctl list | grep -E "(ollama|gbrain|cortex|hermes|docker)"

# Verify Docker container restart policies
for c in $(docker ps -a -q); do
  docker inspect "$c" --format '{{.Name}} {{.HostConfig.RestartPolicy.Name}}'
done
```

Expected: all Hermes Cortex services (`ollama.serve`, `gbrain.sync-watch`, `cortex-dashboard`, `ai.hermes.gateway`) present with `RunAtLoad`. Langfuse containers show `always`, other project containers show `always` or `unless-stopped`.

### Security Checklist (Post-Install)

| Check | Command | Pass |
|-------|---------|------|
| Files locked 0600 | `ls -la ~/.hermes/.env ~/.hermes/config.yaml` | Owner-only |
| No public bindings | `lsof -iTCP -sTCP:LISTEN` | 127.0.0.1 only |
| Firewall enabled | `/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate` | State = 1 |
| Docker restart:always | `docker inspect $(docker ps -qa) --format '{{.Name}} {{.HostConfig.RestartPolicy.Name}}'` | always/unless-stopped |
| SSH remote login off | `sudo systemsetup -getremotelogin` (ask) | Off |
| SSH private key perms | `ls -la ~/.ssh/` | Private keys 0600 |

## Troubleshooting

### gbrain Command Not Found

```bash
# Check if installed
~/.bun/bin/gbrain --version

# Reinstall if needed (NOT from npm!)
bun install -g github:garrytan/gbrain

# Ensure PATH includes ~/.bun/bin
export PATH="$HOME/.bun/bin:$PATH"
echo 'export PATH="$HOME/.bun/bin:$PATH"' >> ~/.zshrc
```

### offline_knowledge Command Not Found

```bash
# Check if installed
ls -la ~/.hermes/bin/offline_knowledge

# ~/.hermes/bin is NOT in PATH by default — add it:
export PATH="$HOME/.hermes/bin:$PATH"
echo 'export PATH="$HOME/.hermes/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# Or use full path:
~/.hermes/bin/offline_knowledge stats
```

### Langfuse Containers Not Starting (v3)

The one-command setup script `cortex-setup-langfuse.sh` generates
all required secrets and deploys the stack:

```bash
bash ~/.hermes/scripts/cortex-setup-langfuse.sh --start
```

This creates `~/langfuse/.env` with 11 auto-generated secrets, copies
the docker-compose file, and runs `docker compose up -d`. No more
staring at `:?` expansion errors because someone forgot to create `.env`.

**Common causes (if manual setup was used):**
  - Missing `LANGFUSE_ENCRYPTION_KEY` (32-byte hex) — required at startup
  - Missing `CLICKHOUSE_MIGRATION_URL` — must use `clickhouse://clickhouse:9000` (Go driver TCP), NOT `http://localhost:8123`
  - `CLICKHOUSE_CLUSTER_ENABLED` must be `false` without Zookeeper
  - Missing `LANGFUSE_S3_EVENT_UPLOAD_BUCKET` — Zod schema rejects missing required S3 vars

```bash
cd ~/langfuse
docker compose logs langfuse-web  # Check for ZodError
docker compose logs langfuse-worker
docker compose up -d

# Force recreate containers if env vars changed
docker compose down
docker compose up -d

# Check health after 30s
curl http://localhost:3000/api/public/health
```

**Full env reference:** See `references/langfuse-v3-migration.md` for all required vars and typical values.

### Langfuse Web Fails with P1000 Auth Error

**Symptom:** `Error: P1000: Authentication failed against database server` in `docker logs langfuse-langfuse-web-1`. The web container starts, runs Prisma migrations, then crashes repeatedly.

**Root cause:** The `DATABASE_URL` in `docker-compose.yml` was written as a literal placeholder (`***`) instead of a variable reference (`**`). When `.env` is regenerated (e.g., after gbrain migration or Langfuse reinstall), Postgres gets the new password from `.env` via `**`, but the web container's `DATABASE_URL` retains the old/hardcoded value.

**Diagnose:**

```bash
# 1. Check for the error
docker logs langfuse-langfuse-web-1 --tail 10 2>&1 | grep P1000

# 2. Verify the compose file has variable reference, not literal placeholder
sed -n '/DATABASE_URL/p' ~/langfuse/docker-compose.yml | xxd
# $  = 0x24  → variable reference (correct)
# *  = 0x2a  → literal asterisk (wrong — hardcoded placeholder)
```

**Fix:**

```bash
# Update docker-compose.yml to use variable reference
sed -i '' 's/postgresql:\\/\\/postgres:\\*\\*\\*@postgres/postgresql:\\/\\/postgres:***@postgres/' ~/langfuse/docker-compose.yml
# Force-recreate BOTH web and worker
docker compose -f ~/langfuse/docker-compose.yml up -d --force-recreate langfuse-web langfuse-worker
```

**Also fix the repo source:**
```bash
sed -i '' 's/postgresql:\\/\\/postgres:\\*\\*\\*@postgres/postgresql:\\/\\/postgres:***@postgres/' ~/hermes-cortex/ops/install/deploy/docker-compose.langfuse.yml
```

### Langfuse Web Container Cycles After Init

After fixing the auth error, the web container may still cycle. Next.js exits with code 0 after init scripts complete (creating default org/user/project). Docker `restart: always` triggers a new cycle. The container serves HTTP for only ~1-4s between MCP registration and exit.

**Detection:**
```bash
docker inspect langfuse-langfuse-web-1 --format '{{.RestartCount}}'
# Shows 6+ restarts
```

**Catching the brief window (browsing works but browser starts too slow):**
```bash
for i in $(seq 1 60); do
  r=$(curl -sS --max-time 2 http://localhost:3000/ 2>/dev/null)
  [ -n "$r" ] && echo "$r" | head -5 && break
  sleep 2
done
```

### Langfuse Stale Users Cause Init Hang

After multiple restart cycles, Next.js init scripts (which create default org/project/user) may hang permanently if user records already exist. Container stays up 5+ minutes without reaching MCP registration. Fix:

```sql
DELETE FROM users WHERE email IN ('user@example.com', 'hermes2@example.com');
```
CASCADE handles related records. Next container restart recreates them cleanly.

### bcrypt Password Hash via docker cp

When `.env` password doesn't match the DB hash, update via SQL file to avoid shell `$` expansion mangling the hash:

```bash
python3 -c "
import bcrypt
pw = 'plaintext_password'
salt = bcrypt.gensalt(rounds=12).decode().replace('\$2b\$', '\$2a\$')
h = bcrypt.hashpw(pw.encode(), salt.encode()).decode().replace('\$2b\$', '\$2a\$')
print(h)
" > /tmp/hash.txt
echo "UPDATE users SET password = '$(cat /tmp/hash.txt)' WHERE email = 'user@example.com';" > /tmp/fix.sql
docker cp /tmp/fix.sql langfuse-postgres-1:/tmp/
docker exec langfuse-postgres-1 psql -U postgres -f /tmp/fix.sql
```

Langfuse uses `$2a$` bcrypt prefix (not Python's default `$2b$`) — replace after generation.

### Cortex Dashboard Not Loading

```bash
# Check launchd service
launchctl list | grep cortex-dashboard

# Check logs
tail -50 ~/.hermes/logs/cortex-dashboard.log

# Restart
launchctl unload ~/Library/LaunchAgents/com.hermes.cortex-dashboard.plist
launchctl load ~/Library/LaunchAgents/com.hermes.cortex-dashboard.plist
```

### nginx 502 Bad Gateway

```bash
# Check backend services are running
curl http://localhost:3000  # Langfuse v3 (health endpoint)
curl http://localhost:8901  # Dashboard

# Check nginx config
nginx -t
# Apple Silicon: /opt/homebrew/var/log/nginx/*.log
# Intel Mac:    /usr/local/var/log/nginx/*.log
tail -50 /opt/homebrew/var/log/nginx/*.log 2>/dev/null || tail -50 /usr/local/var/log/nginx/*.log

# Restart nginx
brew services restart nginx
```

### Plugin Not Working

```bash
# Verify enabled
hermes plugins list

# If "not enabled":
hermes plugins enable gbrain-command

# Start a new Hermes session (/reset or restart CLI)
```

### Autopilot Shows synced=0 — No Sources Registered

**Symptom:** Autopilot cycles every ~150s but every cycle shows `synced=0 extracted=0 embedded=0` and `orphans=N`. Brain directories under `~/brain/` have content but gbrain doesn't index anything.

**Root cause:** The installer creates brain directories with git repos and content, but does NOT register them as gbrain sources. Only the built-in `default` source exists — and it's a federated source with no filesystem path, so it can never sync from disk.

**Diagnostic sequence:**

```
# 1. Check autopilot is running
launchctl list | grep gbrain

# 2. Check autopilot cycles — look for synced=0
tail -20 ~/.gbrain/autopilot.log

# 3. Verify brain directories have content
ls ~/brain/

# 4. (Postgres engine — autopilot no longer blocks CLI access)
#    Skip straight to CLI commands

# 5. Check what sources are registered
gbrain sources list
# If only "default" appears, no named sources exist

# 6. Check DB stats
gbrain stats

# 7. Compare registered sources vs brain directories
# For each dir in ~/brain/ that has a git repo, register it
for d in ~/brain/*/; do
  name=$(basename "$d")
  if [ -d "$d/.git" ]; then
    echo "Need to register: $name"
  fi
done

# 8. Register each project as a gbrain source
gbrain sources add <name> --path ~/brain/<name> --name "<Name>"

# 9. Do initial sync
gbrain sync --all --no-pull
gbrain extract --stale

# 10. Autopilot runs independently — no manual restart needed
#     CLI commands work concurrently with autopilot on Postgres
```

**Pitfalls:**
- `gbrain sources list` and `gbrain stats` work concurrently with autopilot on Postgres (pgvector). No need to stop autopilot.
- Every brain directory must be a **git repo** — `git rev-parse --is-inside-work-tree` confirms. If not, `git init && git add -A && git commit -m "initial"`.
- The `default` source is built-in and cannot be removed or configured with `--path`. Skip it.
- After registration, wait for ~2 autopilot cycles before the `/brain` slash command returns results.

### gbrain Sync Fails

> ~~PGLite engine removed. This system uses Postgres (pgvector).~~
> No longer applicable — gbrain migrated to Postgres.
> See [`docs/gbrain-postgres-migration.md`](docs/gbrain-postgres-migration.md) for troubleshooting with Postgres.

### gbrain Embedding Times Out on Large Documents

**Symptoms:**
```
Error embedding <slug>: [embed(ollama:nomic-embed-text:v1.5)] The operation timed out.
```
Some pages embed successfully (showing progress) but others fail partway through. Large daily memory files and long reference docs fail consistently.

**Root cause:** The default gbrain embed timeout (`AI_EMBED_TIMEOUT_MS`) is 60 seconds. Ollama's `nomic-embed-text:v1.5` takes longer than 60s to generate 768-dim embeddings for large documents.

**Fix:** Set the environment variable in ALL gbrain scripts:
```bash
export GBRAIN_AI_EMBED_TIMEOUT_MS=300000
gbrain embed --stale
```

**Files that need this env var:**
- `~/.gbrain/autopilot-run.sh` — before the `exec` line
- `~/.hermes/scripts/gbrain-nightly-dream.sh` — after PATH export
- `~/.hermes/scripts/gbrain-update-sync.sh` — same

**Verification:**
```bash
# Before: check current embedded count
gbrain stats | grep "Embedded"

# After retry
export GBRAIN_AI_EMBED_TIMEOUT_MS=300000
gbrain embed --all 2>&1 | tail -5
# Expected: "Embedded X chunks across Y pages" with 0 errors

gbrain stats | grep "Embedded"
# Expected: Embedded = Chunks
```

### gbrain Migration Failures

Migrations can stall or fail for several reasons. Follow this diagnostic chain:

**1. Check what failed**

```bash
cat ~/.gbrain/migrations/completed.jsonl | grep -E '(fail|partial|retry)' | tail -5
```

Look for the last `"status":"partial"` or `"status":"failed"` entry — it specifies which phase
and why (e.g. `"source \"mybrain\" has uncommitted changes"`).

**2. Clean the brain repo if dirty**

The v0.32.2 migration (facts fence) refuses to write if the brain directory has uncommitted
changes. Fix:

```bash
cd ~/brain/default
git status --short   # check for dirty files
git add -A && git commit -m "clean state before migration"
```

Then re-run `gbrain apply-migrations --yes`.

**3. Unstick a wedged migration**

If `gbrain apply-migrations --yes` reports a migration is "WEDGED (3+ consecutive partials)":

```bash
gbrain apply-migrations --force-retry <version> --yes  # e.g. 0.32.2
gbrain apply-migrations --yes
```

**4. Autopilot lock times out all gbrain CLI commands**

**Symptoms:** Every gbrain CLI command hangs or times out — `gbrain stats`, `gbrain sources list`, `gbrain search`, all of them.

> **Postgres engine:** With Postgres (pgvector), CLI commands can run concurrently with the autopilot — no lock contention. If commands still hang, the issue is something else (see other troubleshooting steps or [`docs/gbrain-postgres-migration.md`](docs/gbrain-postgres-migration.md)).
>
> For legacy PGLite, the autopilot held the exclusive database lock. This is no longer the case with Postgres.

**Diagnose:** Check if gbrain processes are running:
```bash
ps aux | grep gbrain | grep -v grep
```

**Fix:**
```bash
# Release the lock by stopping both gbrain services
launchctl bootout gui/$(id -u)/com.gbrain.autopilot 2>/dev/null || true
launchctl bootout gui/$(id -u)/com.gbrain.sync-watch 2>/dev/null || true
sleep 2

# Now CLI commands will respond
gbrain <command>

# Reload services
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gbrain.autopilot.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gbrain.sync-watch.plist
```

`bootout` stops the process cleanly — no lock files to remove. After the CLI work, `bootstrap` (not `load`) reloads both services. Verify they're running:
```bash
launchctl list | grep gbrain
# Should show PID (running), exit code 0
```

### Ollama Not Responding

```bash
# Check service status
launchctl list | grep com.ollama.serve

# Restart service
launchctl stop com.ollama.serve
launchctl start com.ollama.serve

# Wait for startup (can take 5-10 seconds)
sleep 5
curl http://127.0.0.1:11434/api/tags
```

### Sync Daemon Not Running

```bash
# Check if loaded
launchctl list | grep com.gbrain.sync-watch

# Reload if needed
launchctl unload ~/Library/LaunchAgents/com.gbrain.sync-watch.plist
launchctl load ~/Library/LaunchAgents/com.gbrain.sync-watch.plist
```

## Public vs Private Repo Split

Hermes Cortex uses a two-repo architecture:

| Repo | Visibility | Contents |
|------|-----------|----------|
| **`hermes-cortex`** (public) | Public | `install.sh`, `docker-compose.langfuse.yml`, `dashboard/`, `nginx/`, skeleton config, architecture docs, bump-version script |
| **`hermes-cortex-private`** (private) | Private | Full `config.yaml` with personal settings, brain content on `brain-*` branches, custom scripts, SSL certs |

**Domain Privacy Rule:** Use `example.com` as placeholder in public repo files. Put your real domain in private repo only. See `references/public-repo-privacy.md` for the full pattern including git history rewriting.

**What the public installer NOW includes (as of commit a51c3a0):**
- ✅ Ollama + launchd service
- ✅ gbrain CLI (from GitHub)
- ✅ Brain directory structure
- ✅ gbrain sync daemon
- ✅ `/brain` Hermes plugin
- ✅ **Langfuse** (Docker Compose, auto-generated secrets)
- ✅ **Cortex Dashboard** (Flask app + launchd)
- ✅ **nginx** reverse proxy (SSL or local-only mode)
- ✅ Utility scripts (heartbeat.py, memory-to-brain-sync.py, etc.)

**What still lives in private repo:**
- Full personal `config.yaml` with custom settings
- Brain content (on `brain-*` branches, not `main`)
- Custom utility scripts beyond the core set
- SSL certificates for nginx

**To apply personal config after public install:**
```bash
git clone git@github.com:fleet-operator/hermes-cortex-private.git ~/hermes-cortex-private
cp ~/hermes-cortex-private/config/config.yaml ~/.hermes/config.yaml
```

**Architecture:**
- Public repo: full installer + observability stack (safe to share)
- Private repo: secrets + personal config + brain content

## Offline Code Assistant

A local RAG-powered coding assistant using Ollama embeddings + a curated snippet corpus spanning 27 languages with 367 examples. Two-tier system: small model + RAG ≈ productivity of a 7B model. All data stays on your machine.

### Setup

The code corpus lives in the repo at `offline/code-corpus/`. Build the index:

```bash
cd ~/hermes-cortex
bash offline/prep-code.sh
```

This generates code snippet files across 20+ languages, builds embeddings with `nomic-embed-text:v1.5`, and writes the index to `~/offline/code-index.json`.

**Ollama models needed:**
- `nomic-embed-text:v1.5` — embeddings (pulled by install.sh)
- `qwen2.5-coder:3b` — code generation (~1.7 GB, must pull manually: `ollama pull qwen2.5-coder:3b`)

### Usage

```bash
# From the repo root
python3 offline/offline_code.py search "flask rest api"    # Find relevant snippets
python3 offline/offline_code.py gen "binary search tree"   # Generate code via Ollama
python3 offline/offline_code.py index                      # Rebuild the search index
python3 offline/offline_code.py stats                      # Corpus statistics
```

**search** — Returns snippets ranked by cosine similarity (nomic-embed-text:v1.5), with language, tags, and score. Top matches include full code blocks.

**gen** — Finds the most relevant snippets via RAG, injects them as context, then generates code with qwen2.5-coder:3b. Falls back gracefully if the model isn't pulled.

**Corpus languages:** Python, JavaScript, TypeScript, Go, Rust, C, C++, C#, Java, Kotlin, Swift, Dart, Elixir, PHP, Ruby, Lua, R, Shell, SQL, Terraform, Docker, Nix, Zig, PowerShell, Kubernetes (27 languages, 367 snippet files).

**Top tags:** pattern, api, web, algorithm, cli, io, net, util, async, testing, security, config, data.

### Pitfalls

- **Model not found on `gen`** — Run `ollama pull qwen2.5-coder:3b` first. The 1.7 GB download takes 2-3 minutes on broadband.
- **Outdated index** — Rebuild with `offline_code.py index --force` after adding new snippet files.
|- **Python version** — The corpus generation needs Python 3.12+ (3.9's sqlite3 can't `enable_load_extension`). Use `python3.12` which is the Hermes default.

## Offline Content

The repo bundles several offline content tools for low-connectivity environments:

| Tool | Description | Script |
|------|-------------|--------|
| **Bible downloader** | Downloads public domain Bible translations (KJV, WEB, ASV, etc.) | `offline/prep-bible.sh` |
| **Hymn collection** | Downloads Open Hymnal Project content (PDFs, ABC, MIDI) | `offline/prep-hymns.sh` |
| **Offline reader** | Local web UI for Bible and hymns | `offline/offline-reader.py` |
| **Auto-update** | Weekly cron job that checks for content updates silently | `offline/auto-update.sh` |
| **Knowledge cascade** | gbrain + kiwix ZIM + web_cache fallback chain | `offline/offline_knowledge.py` |

**Known gap — no `lesson` subcommand:** The `offline_knowledge` tool has `bible` and `hymns` subcommands but NOT `lesson` — `offline_knowledge lesson index` and `offline_knowledge lesson search` do not exist. Lessons live as markdown files in `~/brain/*/lessons/` indexed by gbrain, not as a separate offline knowledge corpus. See `references/offline-knowledge-subcommands.md` for the subcommand architecture pattern and how lessons would be added.

### Known Issues — Bible Prep

`prep-bible.sh` has an unbound variable bug (`$tmp_txt` never assigned) that crashes the download. `bible-parse.py` has 4 pattern-matching issues with KJV headers (colons, "Saint" vs "St.", "General" prefix) and cannot parse WEB's "Book NN Name" format at all. See `references/bible-prep-issues.md` for the full reproduction details and fixes — send this to the repo owner.

### Auto-Update

The `auto-update.sh` script is designed for weekly cron scheduling:
- Checks internet before doing anything (silent exit if offline)
- Only produces output when something actually changed
- Logs to `~/offline/auto-update.log`

```bash
# Check & update everything
./offline/auto-update.sh
# Check only, no downloads
./offline/auto-update.sh --check
# Verbose mode
./offline/auto-update.sh --verbose
```

## Architecture: Uber-Agent + gbrain Knowledge Separation

**Current approach (as of June 2026):** One single Hermes agent (default profile) with knowledge isolation via gbrain sources, not Hermes profiles. This replaced the earlier profile-per-project model.

### Rationale

Profile-per-project was tried (~20 profiles, each with isolated skills/memories/sessions) but provided minimal practical value:

- All profiles inherited the same root `config.yaml` and `.env` — no true config isolation
- Only difference was separate session history and memory files
- Added complexity: shell function, project registration file, auth.json sync, profile creation scripts
- gbrain already handles knowledge separation more cleanly via per-project brain sources

**Decision:** Continue with the **uber-agent** — a single Hermes instance (default profile) with knowledge separation delegated to gbrain sources.

### How Knowledge Isolation Works

Each project gets its own gbrain source directory (e.g., `~/brain/ione/`, `~/brain/acme-royalty/`) that syncs to gbrain as a named source:

```bash
gbrain sources add ione --path ~/brain/ione --name "IONE Website"
gbrain sources add acme-royalty --path ~/brain/acme-royalty --name "ACME Royalty"
```

When querying knowledge in-session:

```
/brain ione site deployment notes
```

The `/brain` command searches across all gbrain sources — no profile switching needed.

### Cleanup Steps (applied June 2026)

When migrating away from profile-per-project:

```bash
# 1. Remove all profile directories
rm -rf ~/.hermes/profiles/*/

# 2. Remove the zshrc shell function that auto-injected --profile
#    Find and delete the entire hermes() function block from ~/.zshrc

# 3. Remove project registration file
rm ~/.cortex-projects.json

# 4. Source the updated .zshrc or open new terminal
source ~/.zshrc
```

### Legacy: Profile-per-Project (Deprecated)

This section documents the approach that was used before mid-2026. Kept for reference if it's ever reconsidered.

The old approach used Hermes profiles for per-project isolation (separate MEMORY.md, USER.md, skills, sessions) with tooling to auto-detect the right profile based on working directory.

**Key files that were removed:**
- `~/.zshrc` shell function intercepting `hermes` calls to inject `--profile`
- `~/.cortex-projects.json` — project-to-profile mapping
- `scripts/cortex-profile.sh` — profile creation helper
- Individual profile dirs under `~/.hermes/profiles/`

**Problems that motivated the change:**
- Profiles without their own `config.yaml` inherit root config — no real isolation
- `auth.json` auto-creation in profiles blocks root credential fallback, requiring manual sync scripts
- Shell function adds startup latency and parse-error risk from alias caching
- gbrain already provides better knowledge separation without the profile overhead

### Memory Architecture (Six-Layer Model)

*See `references/memory-architecture.md` for the full six-layer model, memory scoring rubric, and detailed patterns.*

Agent knowledge in Hermes Cortex spans six layers from fastest/least durable to slowest/most durable:

| Layer | Location | Durability |
|-------|----------|-----------|
| 1 — Agent Prompt | `MEMORY.md` / `USER.md` | Hot cache, lost on restart |
| 2 — Session State | `.hermes-cortex/sessions/current.md` | This session only |
| 3 — Hermes Profile | `~/.hermes/profiles/` | Legacy isolation layer |
| 4 — Brain Source | `~/brain/<source>/` | Cross-project deep knowledge (GBrain) |
| 5 — Repo Memory | `.hermes-cortex/memory/` | Per-project durable conventions |
| 6 — Repo Docs | `docs/` | Version controlled, team-visible |

**Pointer Pattern:** Keep MEMORY.md under 2,200 chars by storing compact pointers (~120 chars) that point to brain directories for detail. Instead of `"ACME Works uses Python 3.13.13, Meilisearch v1.14 on port 13213..."`, write `+ /brain default acme-works (setup, search config)`.

**Memory Scoring Rubric:** Each entry in `memory/` is scored on 4 dimensions (0–3 each). Minimum total: **7/12**. Dimensions: Durability (0–3), Reuse (0–3), Non-obviousness (0–3), Risk if forgotten (0–3). This prevents memory bloat — only durable, reusable, non-obvious, high-impact knowledge gets saved.

**Brain Source vs Repo Memory:** These are independent axes — use both. Brain sources share knowledge by topic across projects; repo memory holds per-project truth. Gbrain sources require git-init and `gbrain sync` to index; repo memory is read from the working directory.

See `references/memory-architecture.md` for the full rubric, entry format, and patterns for cross-project knowledge flow.

## Existing Repo Setup — Seeding Brain Content

After install, each project has an empty brain directory (e.g. `~/brain/my-project/`).
gbrain sources are registered (from the installer or bootstrap script) but show
**"0 pages, never synced"** because there's no content to index.

This is the single most common post-install problem. Without content, the `/brain`
command returns nothing.

### Seed One Project

```bash
# 1. Copy documentation from the repo to the brain dir
mkdir -p ~/brain/my-project/sources
cp ~/path/to/my-project/README.md ~/brain/my-project/sources/
cp ~/path/to/my-project/ARCHITECTURE.md ~/brain/my-project/sources/
cp ~/path/to/my-project/docs/*.md ~/brain/my-project/sources/

# 2. Git init (gbrain requires git repos)
cd ~/brain/my-project
git init
git add -A
git commit -m "seed: my-project documentation"

# 3. Register gbrain source (if not already done)
gbrain sources add my-project --path ~/brain/my-project --name "My Project"

# 4. Sync
gbrain sync --source my-project --no-pull

# 5. Verify
gbrain sources list | grep my-project
# Should show >0 pages
```

### Seed All Projects (Automated)

If `scripts/seed-project-brain.sh` exists (added in a later patched version of the repo):

```bash
# See what's empty and what repos can be auto-detected
bash ~/.hermes/scripts/seed-project-brain.sh --list

# Seed all detected projects
bash ~/.hermes/scripts/seed-project-brain.sh --all

# Seed a single project with auto-detected repo
bash ~/.hermes/scripts/seed-project-brain.sh --project=my-project --auto
```

The script copies README.md, ARCHITECTURE.md, CONTRIBUTING.md, and `docs/`\nfiles into the brain dir, then registers and syncs with gbrain.\n\n**After seeding:** always run `gbrain extract --stale` to complete the index:\n\n```bash\ngbrain extract --stale --source my-project\n```\n\nWithout extraction, cross-source edges aren't built and multi-source search\nquality via `/brain` is degraded.\n\n**Large projects (50+ files):** the initial sync may timeout after 30 seconds.\nThis doesn't mean it failed — check pages actually made it in:\n\n```bash\ngbrain sources list | grep my-project | awk '{print $3}'\n```\nIf pages registered, the sync succeeded despite the timeout message. The\ntimeout only affects the CLI response, not the sync operation.

### What to Seed

Good candidates for brain content:

| File | Why |
|------|-----|
| `README.md` | Project purpose, setup, key links |
| `ARCHITECTURE.md` | System design, component relationships |
| `docs/decisions/*.md` (or ADRs) | Design rationale, rejected alternatives |
| `docs/architecture/*.md` | Detailed architecture docs |
| `docs/specs/*.md` | API specifications, data models |
| `docs/design/*.md` | Design documents |
| `CONTRIBUTING.md` | Workflow conventions |

The `/brain` slash command queries all gbrain sources simultaneously, so seedy docs make every project's knowledge available from any Hermes session.

## Cleaning Up Agent Artifacts from Project Roots

Hermes Agent creates `project-root/.hermes/` directories when working inside
project repos. These contain plans, sessions, scripts, and research docs that
are developer-local scratch files, not project source code.

Over time they accumulate across repos and can pollute `git status` or get
accidentally committed if `.gitignore` lacks `.hermes/`.

### Detection

```bash
find ~/Developer -maxdepth 3 -type d -name '.hermes' -not -path "$HOME/.hermes" -not -path "$HOME/.hermes/*"
```

### Assessment

| Content | Value | Action |
|---------|-------|--------|
| `plans/*.md`, `*.md` at root | Medium — plans, UX reviews, analysis | Archive to `~/brain/<project>/agents/`, then delete |
| `sessions/current.md` | Low — ephemeral session state | Delete directly |
| `scripts/*.sh` | Low — usually hardcoded paths | Review; delete or archive if reusable |

### Cleanup Workflow

1. **Archive** valuable content to `~/brain/<project>/agents/` and git-commit
2. **Add `.hermes/`** to the project's `.gitignore` if missing
3. **Remove** the directory — **one at a time** (sequential `rm -rf`, each reviewed independently)
4. **Sync** the brain source so archived content is searchable

See `references/hermes-dot-dir-cleanup.md` for the full pattern including
archive commands, verification steps, and bulk-detection for prevention.

Remember: `.hermes/` in project roots is the old pattern. The preferred
approach is `.hermes-cortex/` (project-anchored) + `~/.hermes/` (home-dir)
+ `~/brain/<project>/agents/` for indexed agent artifacts.

## References

- `references/script-deployment-architecture.md` — Two-directory deployment model, symlink convention, adding new scripts, pitfalls
- `references/langfuse-data-population.md` — Direct SQL insertion of sample traces, generations, and scores when the API is unavailable due to the web container restart cycle

- `references/memory-architecture.md` — Six-layer memory model, pointer pattern, memory scoring rubric (≥7/12), cross-project knowledge flow, brain source vs repo memory
- `references/multi-project-memory-layers.md` — Memory survivability across restarts, model swaps, profile switches, reinstalls
- `references/session-state-pattern.md` — Session state layer: what stores what, when to save, when to discard
- `references/naming-conventions.md` — Hermes Cortex skill naming (`hc-` prefix) and versioning conventions
- `references/auto-profile-detection.md` — Legacy auto-profile detection pattern (working-directory-based profile selection, deprecated)
- `references/installation-audit-methodology.md` — Systematic install audit: documented-vs-actual pattern, divergence detection, recovery checklist
- `references/hermes-dot-dir-cleanup.md` — Full `.hermes/` directory cleanup pattern: assessment, archive, removal, gitignore, prevention
- `references/gbrain-npm-collision.md` — Detailed documentation of the npm package collision issue
- `references/gbrain-cron-maintenance.md` — gbrain cron maintenance reference, update workflows, and source migration notes
- `references/plugin-enablement.md` — Plugin enablement pitfall and post-install checklist
- `references/install-update-650fc94.md` — Langfuse, Cortex Dashboard, nginx installation (commit 650fc94)
- `references/public-repo-privacy.md` — Domain privacy pattern (example.com placeholder, git history rewriting with git-filter-repo)
- `references/langfuse-v3-migration.md` — Full Langfuse v3 env var reference and migration steps
- `references/security-hardening.md` — File permission lockdown, bind address audit, nginx unload, restart resilience check, full audit one-liner
- `references/bible-prep-issues.md` — Known upstream bugs in prep-bible.sh and bible-parse.py (to report to Moses)
- `references/cortex-update-deployment-map.md` — Full file map, restart functions, and the launchd bootout-before-rm pitfall
- `references/offline-knowledge-subcommands.md` — Subcommand architecture pattern for offline_knowledge.py, the `lesson` tooling gap, and PATH setup
- `references/gbrain-source-migration-export.md` — gbrain data export, cross-engine migration, and Postgres setup notes
- `github.com/garrytan/gbrain` — Official gbrain repository (install via `bun install -g github:garrytan/gbrain`)
- `github.com/fleet-operator/hermes-cortex-private` — Private repo with personal config, brain content
