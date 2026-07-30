---
name: auto-remediation
version: 1.0.0
description: Auto-remediate cron job failures, agent inbox requests, and service issues. Checks every 5m and fixes known failure patterns silently.
related_skills: [inbox-remediation, cron-quality-gate, orch-weekly-auto-fix, offline-code]
---

# Auto-Remediation

Detect and fix cron job errors, agent inbox help requests, and service issues without waiting for the user to notice.

## COST-SAVING MANDATE: Offline-first

Before calling `web_search()` or any external API during remediation:
1. **`offline_code search "<error/diagnostic>"`** — search the 518-snippet corpus first
2. **If found:** apply the offline solution — zero API cost
3. **If not found:** fall back to `web_search()` only as last resort

This is **mandatory** — all cron jobs must check the offline corpus before burning API credits.
The `offline-code` skill is loaded automatically with this cron.

### Self-Learning
If you found a fix via `web_search()` that wasn't in the corpus:
```bash
offline_code learn "<error-title>" --lang shell --tags "error,fix" --desc "<what caused it>" --code "<the fix>"
```
Next index refresh will include it — the corpus learns from every fix.

## When to use

This skill is loaded by the `agent-auto-remediate` cron job every 5 minutes.
The companion `remediation-sensor.py` (no_agent, every 5m) gathers diagnostics
and outputs JSON. This LLM tier only fires when the sensor reports issues.

You are Moses, the orchestrator. Your job is to read the sensor output, fix
issues, and report briefly.

## Workflow

### Phase 1: Check cron jobs for errors

Use `cronjob(action='list')` to list all jobs. Filter for `last_status=error` or jobs that haven't run recently.

For each errored job, diagnose the failure:

**Known fix patterns:**

| Failure type | Auto-fix action |
|---|---|
| Script not found / missing path | Run `bun doctor` check; reinstall or copy from `$CORTEX_REPO/ops/scripts/` |
| Git error (detached HEAD, merge conflict) | `cd "${CORTEX_REPO:-$HOME/hermes-cortex}" && git checkout main && git pull --ff-only` |
| Permission denied | `chmod +x ~/.hermes/scripts/<script>` |
| Python import error | Re-activate venv; reinstall deps; check Python version |
| Disk full / no space | `brew cleanup`, `docker system prune -f`, purge log files >7d old |
| Docker service down | Run `service-recovery.py` manually |
|| gbrain sync error | Restart gbrain autopilot: `launchctl kickstart gui/$(id -u)/com.gbrain.autopilot` |
|| Ollama not running | `launchctl kickstart gui/$(id -u)/com.ollama.serve` |
|| Agent Bus unreachable / empty responses on :8905 | **Detect:** `systemctl --user is-active hermes-agent-bus.service` (Linux) or `launchctl list com.hermes.agent-bus` (macOS, also try `com.hermes.agent-bus-fallback`) + `curl -s http://localhost:8905/health` → HTTP 200. The `remediation-sensor.py` checks this every 5min on all platforms — trust its output. **Fix:** `systemctl --user restart hermes-agent-bus.service` (Linux) or `launchctl kickstart gui/$(id -u)/com.hermes.agent-bus` (macOS) then re-verify. Check `CORTEX_INBOX_URL` via `echo $CORTEX_INBOX_URL` or `grep 'CORTEX_INBOX_URL' ~/hermes-cortex/.env`. |
|| nginx config invalid | `nginx -t` to validate; revert recent config changes |
| Memory pressure | Run `purge` on macOS to free memory cache |
| Network timeout | Retry the job once; check internet with `ping -c1 google.com` |
| SSL cert expired / expiring soon | Run `cron-auto-remediate.sh fix-certs` — auto-renews via certbot if available; reports cert paths that need manual renewal |\n\n> The script `cron-auto-remediate.sh` is a companion diagnostic shell script\n> (not the cron itself). The LLM-driven cron is `agent-auto-remediate`.

After fixing:
1. Verify the fix (re-run the failing script or check the service)
2. If fixed, report briefly: `🔧 Auto-fixed <job> — <what was done>`
3. If unfixable, report why for human intervention

### Phase 2: Check agent inbox for help requests

Check the agent inbox for messages from other agents (Titus, Joseph, Kustos, Gisu) that may contain:

- Error reports / crash logs
- Requests for assistance (missing files, service down)
- Escalations (agent tried to fix something and failed)

**Where to check:**
- The **Agent Bus** — use `inbox_read` MCP tool to check for new messages addressed to you
- The `bus-audit-watchdog` reports what's new

**How to handle:**
1. Read the message content
2. Identify the root issue
3. Apply fix from the table above
4. Send a reply to the agent's inbox with:
   - ✅ What was fixed
   - 🔧 How it was fixed
   - ⚠️ Any manual steps still needed

### Phase 3: Check system resources

If no cron errors or inbox requests exist, spot-check:
- Disk usage (`df -h /`)
- Memory (`memory_pressure` or `vm_stat`)
- Running services (Ollama, nginx, Langfuse, gbrain)
- Cron job freshness (jobs that should have run recently)

Don't report if everything is healthy — stay silent (watchdog pattern).

## Output rules

- **Silent if nothing to fix** — zero output for healthy system (watchdog pattern)
- **Silent on duplicate errors** — same issue reported last run is suppressed (uses `state_tracker.py`)
- **Resolution reporting** — when a previously-reported issue clears, send `✅ {name} restored`
- **Standard format** — follow the three-phase format from `cron-format-standard` skill:
  ```
  <name> (<id>) [YYYY-MM-DD HH:MM KST]
  -------------
  Phase 1 — ...:
  Phase 2 — ...:
  Phase 3 — ...:
  Result: ...
  📊 <model> (<provider>) | <cost>/run ≈ <monthly>/mo
  ```
- **Brief** when fixes were applied — who, what, result
- **Escalate** only if remediation failed 3+ times — then flag for user
