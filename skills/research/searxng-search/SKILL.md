--- Full content (truncated) ---
---
name: searxng-search
description: Free meta-search via SearXNG — aggregates results from 70+ search engines. Self-hosted or use a public instance. No API key needed. Falls back automatically when the web search toolset is unavailable.
version: 1.0.0
author: hermes-agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [search, searxng, meta-search, self-hosted, free, fallback]
    related_skills: [duckduckgo-search, domain-intel]
    fallback_for_toolsets: [web]
---

# SearXNG Search

Free meta-search using [SearXNG](https://searxng.org/) — a privacy-respecting, self-hosted search aggregator that queries 70+ search engines simultaneously.

**No API key required** when using a public instance. Can also be self-hosted for full control. Automatically appears as a fallback when the main web search toolset (`FIRECRAWL_API_KEY`) is not configured.

## Configuration

SearXNG requires a `SEARXNG_URL` environment variable pointing to your SearXNG instance:

```bash
# Pub
... [truncated]
--- End skill ---