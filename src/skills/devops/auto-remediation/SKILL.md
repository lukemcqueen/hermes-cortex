---
name: auto-remediation
description: Auto-remediate cron job failures, agent inbox requests, and service issues. Checks every 5m and fixes known failure patterns silently.
---

# Auto-Remediation

Detect and fix cron job errors, agent inbox help requests, and service issues without waiting for the user to notice.

## When to use

This skill is loaded by the `cron-auto-remediate` cron job every 5 minutes.
You are Moses, the orchestrator. Your job is to check for problems and fix them.

## Workflow

### Phase 1: Check cron jobs for errors

Use `cronjob(action='list')` to list all jobs. Filter for `last_status=error` or jobs that haven't run recently.

For each errored job, diagnose the failure:

**Known fix patterns:**

| Failure type | Auto-fix action |
|---|---|
| Script not found / missing path | Run `~/.bun/bin/bun ~/.bun/bin/gbrain doctor` check; search for script in cortex repo; reinstall via `install.sh` or copy from `~/hermes-cortex/src/scripts/` |
| Git error (detached HEAD, merge conflict) | `cd ~/hermes-cortex && git checkout main && git pull --ff-only` |
| Permission denied | `chmod +x ~/.hermes/scripts/<script>` |
| Python import error | Re-activate venv; reinstall deps; check Python version |
| Disk full / no space | `brew cleanup`, `docker system prune -f`, purge log files >7d old |
| Docker service down | Run `service-recovery.py` manually |
| gbrain sync error | Restart gbrain autopilot: `launchctl kickstart gui/$(id -u)/com.gbrain.autopilot` |
| Ollama not running | `launchctl kickstart gui/$(id -u)/com.ollama.serve` |
| nginx config invalid | `nginx -t` to validate; revert recent config changes |
| Memory pressure | Run `purge` on macOS to free memory cache |
| Network timeout | Retry the job once; check internet with `ping -c1 google.com` |

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
- `~/hermes-cortex-private/messages/inbox/` — broadcast messages addressed to `all` or from an agent asking for help
- The `check-agent-messages.sh` output tells you what's new

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

- **Silent if nothing to fix** — zero output for healthy system
- **Brief** when fixes were applied — who, what, result
- **Escalate** only if remediation failed 3+ times — then flag for user
