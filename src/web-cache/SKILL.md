---
name: web-cache
description: "Local semantic web cache for AI agents — cache web_search and web_extract results locally with embeddings, reducing API costs and enabling offline operation."
version: 1.0.0
author: Hermes Cortex
license: MIT
platforms: [linux, macos, windows]
---

# Web Cache — Local Semantic Cache for Agent Web Results

## Overview

`web_cache` is a transparent cache that sits between you and the web. It stores `web_search` and `web_extract` results in a local SQLite database with vector embeddings (via Ollama nomic-embed-text), so you can check the cache **before** making expensive web calls.

Over time, the cache becomes a rich "local internet" — you can answer most common queries from cached knowledge alone, even when offline.

## Installation

Installed automatically by `install.sh` step 10 into `~/.hermes/web-cache/`.

Requires: `sqlite-vec`, `requests` (installed in a venv at `~/.hermes/web-cache/.venv/`)

## Usage Protocol — How to Use This in Every Session

### 1. Before `web_search(query)` — Check Cache First

```python
# Step 1: Check cache
cache_result = terminal("""
    web_cache search "your search query here"
""")

# Step 2: Parse the result
import json
cache_data = json.loads(cache_result["output"])

if cache_data.get("cached"):
    hits = cache_data["hits"]
    # Use cached results — skip the web call entirely
    # Each hit has: query, summary, urls, similarity, source
else:
    # Cache miss — proceed with web_search as normal
    web_results = web_search("your search query here")
    
    # Then store the results for next time:
    terminal(f"""
        echo '{json.dumps(web_results)}' | web_cache store "your search query here" -
    """)
```

### 2. Before `web_extract(url)` — Check URL Cache First

```python
# Step 1: Check URL cache
cache_result = terminal(f"""
    web_cache extract {url}
""")

cache_data = json.loads(cache_result["output"])

if cache_data.get("cached"):
    # Use cached content — skip the web call
    content = cache_data["content"]
else:
    # Cache miss — proceed with web_extract as normal
    content = web_extract(url)
    
    # Then store for next time:
    terminal(f"""
        echo '{json.dumps(content)}' | web_cache store-extract {url} -
    """)
```

### 3. Automated Mode

For quick lookups, use `auto` and `auto-extract`:
```bash
# Returns cached results or empty miss
web_cache auto "query"
web_cache auto-extract "https://example.com"
```

These never make web calls — they only check the cache.

## Offline Operation

When you have no internet connection:
1. The cache is your only source of truth
2. Use `web_cache search <query>` — if the answer was cached before, you get it
3. Use `web_cache extract <url>` — if the page was cached before, you get it
4. No internet? No problem — the cache just returns misses for unknown queries

**Pro tip:** Before going offline, run a broad search session to populate the cache with content you'll need. Or import a cache export from another machine.

## Cache Sync (Multi-Machine)

To share cache between machines:
```bash
# On machine A: export
web_cache export ~/web-cache-export.tar.gz

# Transfer the file (AirDrop, USB, SSH, etc.)

# On machine B: import
web_cache import ~/web-cache-export.tar.gz
```

This merges — doesn't overwrite — so both machines accumulate knowledge.

## Maintenance

```bash
# View cache stats
web_cache stats

# Prune old entries when over 200MB limit
web_cache prune

# Manual backup
web_cache backup ~/backups/

# Export portable archive
web_cache export ~/backups/web-cache-YYYY-MM-DD.tar.gz
```

Cron jobs handle nightly pruning and backup automatically.

## Design

```
SQLite + sqlite-vec (vector search)
    ↓
Dual-mode lookup:
  - Semantic similarity for search queries (>0.82 threshold)
  - Exact URL match for page extracts
    ↓
Ollama nomic-embed-text for embeddings (768-dim, local, free)
    ↓
LRU eviction when >200MB (configurable)
    ↓
Portable export/import for multi-machine sync
```

## Commands Reference

| Command | Description |
|---------|-------------|
| `web_cache search <query>` | Semantic search cached queries |
| `web_cache store <query> [file]` | Store search results |
| `web_cache extract <url>` | Check URL cache |
| `web_cache store-extract <url> [file]` | Store extract results |
| `web_cache prune` | LRU eviction over limit |
| `web_cache stats` | Cache statistics |
| `web_cache backup [path]` | Backup DB to file |
| `web_cache export [path]` | Export portable tar.gz |
| `web_cache import <file>` | Import from export |
| `web_cache clear` | Wipe all cached data |
| `web_cache auto <query>` | Cache check only (no web call) |
| `web_cache auto-extract <url>` | URL check only (no web call) |
