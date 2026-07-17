--- Full content (truncated) ---
---
name: agent-inbox-automation
description: "Architecture for automated Agent Inbox monitoring and processing — detects unread messages within 1 minute, processes within 2 minutes."
version: 1.16.0
author: gisu
metadata:
  hermes:
    tags: [inbox, cron, automation, imap, api]
---

# Agent Inbox Automation

Two-tier architecture for reading and acting on Agent Inbox messages within 10 minutes.

## Architecture

\`\`\`
┌─────────────────┐     detects (every 5m)      ┌──────────────┐
│   Watchdog      │ ──────────────────────────► │   User/Tg    │
│ (no_agent=true) │     output unread details    │   (notify)   │
└────────┬────────┘                              └──────────────┘
         │
         │  watchdog output available for context_from
         ▼
┌─────────────────┐     reads + acts (every 10m) ┌──────────────┐
│   Processor     │ ──────────────────────────► │   APIs/Tools │
│ (LLM-driven)    │     mark read, send reply    │   (execute)  │
└─────────────────┘                     
... [truncated]
--- End skill ---