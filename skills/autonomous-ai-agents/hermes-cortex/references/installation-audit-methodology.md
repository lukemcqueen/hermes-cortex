# Installation Audit Methodology

Systematic approach to auditing a Hermes Cortex installation against
the documented state. Use after fresh install, after repo updates, or
when diagnosing "empty brain" or "nothing works" symptoms.

## Documented-vs-Actual Comparison

The core pattern: compare what the installer *claims* to have done against
what *actually* exists on disk and in running processes.

### Layer 1: Process Audit

1. List all Hermes Cortex launchd services
2. Check exit codes (non-zero = degraded even if running)
3. Cross-reference against what the installer should have created

### Layer 2: Container Audit

1. List running Docker containers — filter by stack name, don't rely on bare `docker ps`:
   ```bash
   docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep langfuse
   ```
   Bare `docker ps` truncates long container names (`langfuse-postgres-1` may not appear in the
   default tabular view unless you scroll right). Always grep by stack name.

2. Group by project/stack — count containers per stack:
   ```bash
   docker ps --format "{{.Names}}" | cut -d- -f1 | sort | uniq -c
   ```

3. Check for missing stacks (e.g., Langfuse should have 6 containers: web, worker, postgres,
   redis, clickhouse, minio — if fewer, the stack is degraded).

### Layer 3: File Audit

1. Compare repo's `scripts/` files against `~/.hermes/scripts/` copies
2. Check for drift between install.sh embedded heredocs and standalone files
3. Verify configs at expected locations

### Layer 4: Data Audit

1. Check every mycortex source has >0 indexed pages
2. Check git repos exist in every brain directory
3. Check mycortex migration state

### Layer 5: Workflow Audit

1. Run the heartbeat script with `--report` — does it detect everything?
2. Try `/brain hello` in a Hermes session — does it return anything?
3. Check cron jobs are registered and enabled

### Layer 6: Brain Content Audit

1. After seeding a new brain source (or running `--all`), verify pages made it in:
   ```bash
   mycortex sources list | grep -v "0 pages" | grep -v "^$\|SOURCES\|────"
   ```
2. After `mycortex sync --source <name>`, always follow with:
   ```bash
   mycortex extract --stale --source <name>
   ```
   Without `extract --stale`, new pages are synced but their cross-source edges
   aren't computed — the `/brain` slash command's multi-source search quality
   is degraded.
3. For large source seeds (50+ files), `sync` may timeout at the default 30s.
   Re-run with a longer window or verify pages appeared despite the timeout:
   ```bash
   mycortex sources list | grep <name> | awk '{print $3}'  # page count
   ```

## Remediation Pattern

For each gap found:
- **Missing service:** start it via launchd/systemd
- **Divergent script:** copy repo version over installed version
- **Empty brain dir:** seed content from project repo (see Existing Repo Setup)
- **Stale sync:** manually sync with explicit --source
- **Broken cron:** recreate with cronjob tool

## Recovery Checklist

```bash
# 1. Fix diverged scripts
cp ~/hermes-cortex/scripts/heartbeat.py ~/.hermes/scripts/heartbeat.py
cp ~/hermes-cortex/scripts/memory-to-brain-sync.py ~/.hermes/scripts/memory-to-brain-sync.py

# 2. Fix sync daemon (add --skip default)
sed -i '' 's/sync --all --no-pull/sync --all --no-pull --skip default/' ~/.legacy-brain/sync-watch.sh
launchctl unload ~/Library/LaunchAgents/com.legacy-brain.sync-watch.plist
launchctl load ~/Library/LaunchAgents/com.legacy-brain.sync-watch.plist

# 3. Seed all brain dirs from project repos
bash ~/.hermes/scripts/seed-project-brain.sh --all 2>/dev/null || \
  echo "No seed script yet — seed manually (see Existing Repo Setup in skill)"

# 4. Rebuild offline code index
offline_code index 2>/dev/null || python3 ~/.hermes-cortex/offline/offline_code.py index

# 5. Verify
mycortex sources list
python3 ~/.hermes/scripts/heartbeat.py --report
```
