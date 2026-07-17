--- Full content (truncated) ---
---
name: moses-inbox-remediation
description: "Auto-remediate hermes-cortex issues reported by peer agents via the agent inbox. Scans pending remediation markers every 10 minutes, reads the original message, applies the fix, and marks the request as done."
version: 1.0.0
author: Moses
license: MIT
metadata:
  hermes:
    tags: [cron, remediation, inbox, multi-agent, auto-fix]
    related_skills: [orch-weekly-auto-fix, agent-inbox, public-contribution]
---

# Moses Inbox Remediation

## When to Use

Load this skill when:
- Setting up the orch-process-agent-messages cron
- Other agents need to report hermes-cortex issues and have them auto-fixed
- You want a multi-agent auto-remediation pipeline

## Architecture

```
[Peer Agent] sends message to inbox topic → general/luke/all/<agentname>
    ↓
[orch-team-messages.sh] runs every 10m (no_agent)
    ↓  Detects keywords: error, failed, broken, crash, help, etc.
    ↓  Writes remediation marker to ~/.hermes/state/remediate/
    ↓
[orch-mose
... [truncated]
--- End skill ---