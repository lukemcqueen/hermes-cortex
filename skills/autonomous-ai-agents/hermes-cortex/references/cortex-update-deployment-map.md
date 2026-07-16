# cortex-update.sh Deployment Map

`cortex-update.sh` uses a `register()` function to map repo source paths → installed
destination paths. Only registered files are auto-deployed when changed.

## Full Map (as of commit f28552e)

Sources under `~/hermes-cortex/` → dest under `~/.hermes/` or `~/`.

### Core scripts
| Repo source | Installed dest | Notes |
|-------------|---------------|-------|
| `ops/scripts/cortex-update.sh` | `~/.hermes/scripts/cortex-update.sh` | Self-updating |
| `ops/scripts/health/heartbeat.py` | `~/.hermes/scripts/heartbeat.py` | |
| `ops/scripts/manage/memory-to-brain-sync.py` | `~/.hermes/scripts/memory-to-brain-sync.py` | |
| `ops/scripts/install/bootstrap-brain.sh` | `~/.hermes/scripts/bootstrap-brain.sh` | |
| `ops/scripts/health/check-memory-budget.sh` | `~/.hermes/scripts/check-memory-budget.sh` | |
| `ops/scripts/manage/cortex-health.sh` | `~/.hermes/scripts/cortex-health.sh` | |
| `ops/scripts/install/cortex-setup-langfuse.sh` | `~/.hermes/scripts/cortex-setup-langfuse.sh` | |
| `ops/scripts/install/install-gbrain-sync.sh` | `~/.hermes/scripts/install-gbrain-sync.sh` | `restart_gbrain_sync` |
| `ops/scripts/install/install-ollama.sh` | `~/.hermes/scripts/install-ollama.sh` | |
| `ops/scripts/install/install-nginx.sh` | `~/.hermes/scripts/install-nginx.sh` | |
| `ops/scripts/install/install-cortex-update-cron.sh` | `~/.hermes/scripts/install-cortex-update-cron.sh` | |
| `ops/scripts/health/prod-watchdog.sh` | `~/.hermes/scripts/prod-watchdog.sh` | |
| `ops/scripts/agent/agent-health-monitor.py` | `~/.hermes/scripts/agent-health-monitor.py` | |
| `ops/scripts/install/os-config.sh` | `~/.hermes/scripts/os-config.sh` | |
| `ops/scripts/install/service-writer.sh` | `~/.hermes/scripts/service-writer.sh` | |
| `ops/scripts/health/system-alert-watchdog.py` | `~/.hermes/scripts/system-alert-watchdog.py` | |
| `ops/scripts/health/service-recovery.py` | `~/.hermes/scripts/service-recovery.py` | |
| `ops/scripts/health/langfuse-health-watchdog.py` | `~/.hermes/scripts/langfuse-health-watchdog.py` | |
| `ops/scripts/manage/llm-judge-scorer.py` | `~/.hermes/scripts/llm-judge-scorer.py` | |
| `ops/scripts/health/cron-auto-remediate.sh` | `~/.hermes/scripts/cron-auto-remediate.sh` | |
| `ops/scripts/manage/daily-lesson-mine.sh` | `~/.hermes/scripts/daily-lesson-mine.sh` | |
| `ops/scripts/manage/lesson-compound-stats.py` | `~/.hermes/scripts/lesson-compound-stats.py` | |
| `ops/scripts/manage/lesson-hit.sh` | `~/.hermes/scripts/lesson-hit.sh` | |

### Lesson-aware scripts
| `ops/scripts/manage/daily-lesson-mine.sh` | `~/.hermes/scripts/daily-lesson-mine.sh` | |
| `ops/scripts/manage/lesson-compound-stats.py` | `~/.hermes/scripts/lesson-compound-stats.py` | |
| `ops/scripts/manage/lesson-hit.sh` | `~/.hermes/scripts/lesson-hit.sh` | |

### Offline tools
| `ops/offline/offline_knowledge.py` | `~/.hermes-cortex/offline/offline_knowledge.py` | |
| `ops/offline/offline_knowledge.sh` | `~/.hermes/bin/offline_knowledge` | Symlink in bin/ for PATH access |
| `ops/offline/offline_code.py` | `~/.hermes-cortex/offline/offline_code.py` | |
| `ops/offline/offline_code.sh` | `~/.hermes/bin/offline_code` | Symlink to bin/ for CLI access |
| `ops/offline/code-corpus/` | `~/.hermes-cortex/offline/code-corpus/` | 366 snippets, 25 languages |
| `ops/offline/kiwix-docker-compose.yml` | `~/.hermes-cortex/offline/kiwix-docker-compose.yml` | |
| `ops/offline/prep-offline.sh` | `~/.hermes-cortex/offline/prep-offline.sh` | |
| `ops/offline/session_mine.py` | `~/.hermes-cortex/offline/session_mine.py` | |
| `ops/offline/lessons.py` | `~/.hermes-cortex/offline/lessons.py` | |
| `ops/offline/migrate_fts_reasoning.sql` | `~/.hermes-cortex/offline/migrate_fts_reasoning.sql` | |
| `ops/offline/auto-update.sh` | `~/.hermes-cortex/offline/auto-update.sh` | |

### Dashboard
| `ops/services/dashboard/server.py` | `~/.hermes-cortex/dashboard/server.py` | `restart_dashboard` |
| `ops/services/dashboard/static/index.html` | `~/.hermes-cortex/dashboard/static/index.html` | |
| `ops/services/dashboard/com.hermes.cortex-dashboard.plist` | `~/Library/LaunchAgents/com.hermes.cortex-dashboard.plist` | |

### Agent inbox

| `ops/services/agent-inbox/server.py` | `~/.hermes-cortex/agent-inbox/server.py` | `restart_agent_inbox` |
| `ops/services/agent-inbox/com.hermes.agent-inbox.plist` | `~/Library/LaunchAgents/com.hermes.agent-inbox.plist` | |
| `ops/services/agent-inbox/agent-inbox-monitor.sh` | `~/.hermes/scripts/agent-inbox-monitor.sh` | |

> ⚠️ **server.py is deployed to all agents by cortex-update.sh (having the file on disk is harmless).**
> **But it should only be RUN on designated server machines** (Moses, Esther backup).
> Client agents (Titus, Gisu, Joseph, Kustos) must NOT start server.py. They connect remotely via MCP tools pointed at the server URL in `~/.hermes-cortex/cortex-bus.conf`.

### Templates (guarded — only if dest missing)
| `docs/templates/MEMORY.seed.md` | `~/.hermes/memories/MEMORY.md` | |
| `docs/templates/USER.seed.md` | `~/.hermes/memories/USER.md` | |
| `docs/templates/memory-readme.seed.md` | `~/.hermes/memory/README.md` | |

### Langfuse
| `deploy/docker-compose.langfuse.yml` | `~/langfuse/docker-compose.yml` | `restart_langfuse` |

## NOT Registered (must update manually)

| File | Why not registered |
|------|-------------------|
| `deploy/nginx/hermes-services.conf` | Not registered — nginx may not be installed (laptop profile). Apply manually or re-run install.sh. |
| `deploy/config/` files | Not registered — env-specific configs. |
| `ops/offline/prep-bible.sh`, `prep-hymns.sh` | Not registered — one-shot download scripts, not core services. |
| `ops/offline/offline_code.py` | Not registered — code corpus index is rebuilt by prep-code.sh during install. |

## Update Modes

**Delta mode (default):** Compares the last-updated commit (stored at `~/.hermes/state/update-commit`)
with the current repo HEAD via `git diff --name-only`. Only changed files are processed.

**Force mode (`--force-all`):** Checks every registered file via sha256sum comparison, regardless
of git history. Copies any file whose hash differs from the installed version.

**Status mode (`--status`):** Shows last update commit and current HEAD without making changes.

## macOS Compatibility — sha256sum Not Found

**PROBLEM:** `cortex-update.sh --force-all` uses `sha256sum` for checksum comparison, but macOS (even 14.x) does not ship `sha256sum`. The command returns "not found", causing `needs_update()` to see two empty hashes, which match — so **every existing file is skipped** during force-all updates. Only brand-new files (destination missing) get copied.

**FIX (applied in commit f28552e):** The `needs_update()` function now detects the available checksum tool:

```bash
if command -v sha256sum &>/dev/null; then
  src_hash=$(sha256sum "$src" 2>/dev/null | cut -d' ' -f1)
  dest_hash=$(sha256sum "$dest" 2>/dev/null | cut -d' ' -f1)
elif command -v shasum &>/dev/null; then
  src_hash=$(shasum -a 256 "$src" 2>/dev/null | cut -d' ' -f1)
  dest_hash=$(shasum -a 256 "$dest" 2>/dev/null | cut -d' ' -f1)
else
  [[ "$src" -nt "$dest" ]] && return 0 || return 1
fi
```

On macOS, `shasum -a 256` is the equivalent of `sha256sum` and is available natively (Perl-based).

**VERIFICATION:**
```bash
bash ~/.hermes/scripts/cortex-update.sh --force-all
diff ~/hermes-cortex/ops/scripts/health/system-alert-watchdog.py ~/.hermes/scripts/system-alert-watchdog.py
# Should be identical (no diff output)
```

## Restart Functions

When a registered file needs a service restart, the function is called after all
file copies complete:

| Function | Service | What it does |
|----------|---------|-------------|
| `restart_gbrain_sync` | `com.gbrain.sync-watch` | Unloads launchd, removes stale sync-watch.sh, re-runs install-gbrain-sync.sh to regenerate script + reload plist |
| `restart_langfuse` | Docker Compose stack | Runs `docker compose up -d` in `~/langfuse/` |
| `restart_dashboard` | `com.hermes.cortex-dashboard` | Unloads/reloads launchd plist |

### restart_gbrain_sync Pitfall

Must call `launchctl bootout` BEFORE removing `sync-watch.sh`. Without it, launchd
KeepAlive keeps the old process alive, and `install-gbrain-sync.sh` sees "already
running" and skips regeneration. The plist then points to a deleted file.

Fixed in commit 893ddc4. Verify after any cortex update:

```bash
ls -la ~/.gbrain/sync-watch.sh       # must exist
launchctl list com.gbrain.sync-watch | grep PID  # different from before
grep "skip default" ~/.gbrain/sync-watch.sh  # --skip default present
```
