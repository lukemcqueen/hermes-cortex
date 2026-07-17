--- Full content (truncated) ---
---
name: agent-inbox-polling
description: "Set up Agent Inbox polling on any agent machine — config, watchdog script, cron jobs, verification."
version: 1.2.0
author: Joseph
platforms: [macos, linux]
---

# Agent Inbox Polling Setup

Set up a machine to poll the Agent Inbox for inter-agent messages (replaces the git-based inbox).

## Overview

Each agent needs two cron jobs:

1. **Watchdog** (every 1 min, no_agent = zero tokens) — runs `agent-inbox-check.sh` (DEPRECATED — see below), silent when nothing new
2. **Processor** (every 10 min, LLM agent) — fetches unread messages via MCP tools, reads them, takes action

### ⚠️ agent-inbox-check.sh Deprecated

Moses has deprecated the direct-cURL watchdog script. Use MCP tools (`inbox_read`, `inbox_send`, `inbox_watch`) instead of curl for all inbox operations. The watchdog script still works for local monitoring but the processor must use MCP tools.

**Note about the "external API removed" claim:** Some deployments still use `https://realg
... [truncated]
--- End skill ---