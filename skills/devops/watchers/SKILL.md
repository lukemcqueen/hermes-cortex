--- Full content (truncated) ---
---
name: watchers
description: Poll RSS, JSON APIs, and GitHub with watermark dedup.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [cron, polling, rss, github, http, automation, monitoring]
    category: devops
    requires_toolsets: [terminal]
    related_skills: []
---

# Watchers

Poll external sources on an interval and react only to new items. Three ready-made scripts plus a shared watermark helper; wire them into a cron job (or run them ad-hoc from the terminal).

## When to Use

- User wants to watch an RSS/Atom feed and be notified of new entries
- User wants to watch a GitHub repo's issues / pulls / releases / commits
- User wants to poll an arbitrary JSON endpoint and get notified on new items
- User asks for "a watcher for X" or "notify me when X changes"

## Mental model

A watcher is just a script that:

1. Fetches data from the external source
2. Compares against a watermark file of previously-seen IDs
3. Writes 
... [truncated]
--- End skill ---