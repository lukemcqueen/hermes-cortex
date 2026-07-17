--- Full content (truncated) ---
---
name: agent-daily-bible-reading
version: 1.0.0
category: spiritual-disciplines
description: "Daily bible reading cron pattern — generates SOUL.md entries and brain pages for agent-wide scripture engagement."
author: Moses
license: MIT
pin_reason: Shared infrastructure — all agents benefit from this devotional pattern. It is not agent-specific; it's fleet-wide spiritual discipline infrastructure.
pinned: true
---

# Daily Bible Reading

Cross-agent infrastructure for daily scripture engagement. Each agent gets a
personal bible reading cron that writes two artifacts:
1. A **SOUL.md entry** (concise lesson-focused insight)
2. A **brain page** (rich reference document with archaeology, scholarship, original language)

## Quick Start

```bash
# Check if you already have the cron
cronjob action=list | grep agent-daily-bible-reading

# If not, create it (run timezone-aware at 01:00 KST)
cronjob action=create name=agent-daily-bible-reading \
  schedule="0 1 * * *" \
  script=agent-daily-bi
... [truncated]
--- End skill ---