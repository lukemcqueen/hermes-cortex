---
name: auto-remediation-fixes
description: "Essential auto-remediation fixes for staging server guardian — timeout patterns, provider drift fixes, and operational hygiene for cron job errors and agent inbox remediation."
version: 1.0.0
category: devops
---

# Auto-Remediation Fixes — Orchestrator Patterns

## General Principles

### Conservative Editing of Monitoring Lists

When modifying a cron quality watchdog's `MONITORED_CRONS` list (or any monitoring inventory):

1. **Only remove entries that don't exist.** An existing cron, even if it's a `no_agent` script rather than an LLM-driven cron, still produces output worth monitoring. The watchdog checks apply to all output, not just LLM-generated text.
2. **Add new entries rather than shuffling.** If the list is missing crons that should be monitored, add them. Rearranging is cosmetic and risks accidentally removing a valid entry.
3. **Verify each entry exists.** Check `cronjob(action='list')` or `read_file('~/.hermes/cron/jobs.json')` before deciding an entry is stale.

## Timeout Patterns

### Cron Timeout Fires

When a cron times out ("timed out after Ns"):

1. Check the cron's actual runtime — `cronjob action='list'` shows `last_duration`.
2. If the script legitimately needs more time, raise the timeout — do not "optimize" a script that is correctly slow.
3. If the script hangs (waiting on network, lock, or stdin), fix the hang — raising the timeout just delays the failure.

### Provider Timeout Drift

When an API provider (OpenRouter, DeepSeek, Ollama) starts timing out:

1. Verify the provider's own status page (health-external-verification).
2. Check `OLLAMA_KEEP_ALIVE` — a 0 value unloads the model and the cold-load exceeds the `_embed()` timeout (see loop-governance lesson).
3. Add retry-with-backoff at the call site rather than raising timeouts globally.

## Provider Drift Fixes

### Model/Config Drift After Update

When an update cycle silently changes provider config:

1. **Diff the deployed config vs repo source** — `config-drift-diagnostics` compares 3 locations.
2. **Fix the repo source first**, then deploy — never patch the deployed copy directly (cortex-preflight rule).
3. **Verify the running service actually reloaded** — file-on-disk ≠ change-live (Principle 15).

### Cron Prompts Referencing Missing Skills

When a cron prompt references a skill that doesn't exist or was renamed:

1. Find the real skill name — `skills_list()`.
2. Update the cron's skill attachment — `cronjob action='update' skills=[...]`.
3. Update the installer source in `install-crons.sh` so the fix survives redeploys.

## Operational Hygiene

### Remediation Must Be Idempotent

Every fix applied by the guardian must be safe to re-run on an already-fixed system:

```bash
# ✅ Idempotent: check-then-act
if ! grep -q "setting" config; then
  echo "setting" >> config
fi

# ❌ Non-idempotent: appends every time
echo "setting" >> config
```

### Escalate After Repeated Failure

A remediation that fires 3+ times for the same root cause is a failed fix, not a healthy loop:

1. First occurrence: remediate, log outcome.
2. Second occurrence: remediate + check the fixer's own logic (wrong pattern?).
3. Third occurrence: **escalate** — stop auto-fixing, report to the orchestrator with the failure history.

### Unattended Destructive Actions Default to No-Op

In unattended/cron mode, destructive operations (prunes, deletions, resets) default to **inaction** when ambiguous. Disk pressure can be remediated; deleted data cannot.

## Related
- `auto-remediation-ecosystem` — full-pipeline deployment + monitoring
- `auto-remediation-setup` — setup and verification
- `cron-quality-gate` — the watchdog that monitors cron output
- `sensor-false-positive-remediation` — handling false sensor positives
- `fix-without-asking` — when to auto-fix vs escalate
