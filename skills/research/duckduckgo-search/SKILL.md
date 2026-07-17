--- Full content (truncated) ---
---
name: duckduckgo-search
description: Free web search via DuckDuckGo — text, news, images, videos. No API key needed. Prefer the `ddgs` CLI when installed; use the Python DDGS library only after verifying that `ddgs` is available in the current runtime.
version: 1.3.0
author: gamedevCloudy
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [search, duckduckgo, web-search, free, fallback]
    related_skills: [arxiv]
    fallback_for_toolsets: [web]
---

# DuckDuckGo Search

Free web search using DuckDuckGo. **No API key required.**

Preferred when `web_search` is unavailable or unsuitable (for example when `FIRECRAWL_API_KEY` is not set). Can also be used as a standalone search path when DuckDuckGo results are specifically desired.

## Detection Flow

Check what is actually available before choosing an approach:

```bash
# Check CLI availability
command -v ddgs >/dev/null && echo "DDGS_CLI=installed" || echo "DDGS_CLI=missing"
```

Decision tree:
1. If `ddg
... [truncated]
--- End skill ---