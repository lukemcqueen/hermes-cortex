--- Full content (truncated) ---
---
name: auto-remediation-fixes
description: Essential auto-remediation fixes for staging server guardian — timeout patterns, provider drift fixes, and operational hygiene for cron job errors and agent inbox remediation.
---

# Auto-Remediation Fixes — Orchestrator Patterns

## General Principles

### Conservative Editing of Monitoring Lists

When modifying a cron quality watchdog's `MONITORED_CRONS` list (or any monitoring inventory):

1. **Only remove entries that don't exist.** An existing cron, even if it's a `no_agent` script rather than an LLM-driven cron, still produces output worth monitoring. The watchdog checks apply to all output, not just LLM-generated text.
2. **Add new entries rather than shuffling.** If the list is missing crons that should be monitored, add them. Rearranging is cosmetic and risks accidentally removing a valid entry.
3. **Verify each entry exists.** Check `cronjob(action='list')` or `read_file('~/.hermes/cron/jobs.json')` for the exact cron name before 
... [truncated]
--- End skill ---