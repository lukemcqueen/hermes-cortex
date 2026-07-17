--- Full content (truncated) ---
---
title: Daily Bible Reading Cron
name: daily-bible-reading
description: >
  Daily cron job that reads one book of the Bible, extracts 3 lessons with
  practical application to server operations, and appends to SOUL.md.
  Runs autonomously at 1am — no user interaction, no notification.
triggers:
  - Cron job at 1am daily
  - Reading one book of the Bible per day through the full canon
  - SOUL.md maintenance and state file management
---

# Daily Bible Reading Cron

## Implementation Note

There are **two implementations** of the daily bible reading cron on this system:

| Aspect | Legacy (this skill) | Active (installed) |
|--------|-------------------|-------------------|
| Type | LLM-driven cron | `no_agent` Python script |
| Script | N/A (LLM prompts directly) | `~/hermes-cortex/src/scripts/agent-daily-bible-reading.py` |
| API | bible-api.com (WEB translation) | OpenCode Zen (deepseek-v4-flash) |
| State tracking | `~/.hermes/bible-reading-state.txt` | Parses SOUL.md for last bo
... [truncated]
--- End skill ---