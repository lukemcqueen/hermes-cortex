---
name: offline-knowledge
description: "Offline knowledge cascade — query local content (web-cache, kiwix ZIM, gbrain) without internet. Perfect for travel, remote areas, or saving API costs."
version: 1.0.0
author: Hermes Cortex
license: MIT
platforms: [linux, macos, windows]
---

# Offline Knowledge — Cascade Knowledge Lookup Without Internet

## Overview

The offline knowledge tool provides a transparent **cascade lookup** across four local sources, in order of speed/cost:

1. **web_cache** — semantic search (~50ms, zero cost, always checked first)
2. **kiwix-serve** (Docker) — Wikipedia, WikiMed, Wikivoyage, Wikibooks, Wiktionary via ZIM files
3. **gbrain** — personal knowledge brain via RAG
4. **LLM native knowledge** — always available, no lookup needed

**When online:** saves API calls on every cached query — cache hit → skip web_search entirely.
**When offline:** the cascade IS your internet — kiwix ZIM files are a local Wikipedia.

## Installation

```bash
# Step 1: Run the installer
hermes-cortex/install.sh    # steps 11 + 13 cover all offline tools

# Step 2: Download content (interactive menu)
hermes-cortex/offline/prep-offline.sh

# Step 3: Verify
offline_knowledge stats
```

## Usage Protocol — How to Use This in Every Session

### Before `web_search()` — Check Offline Knowledge First

```python
# Step 1: Check offline cascade (cache → kiwix → everything)
offline_result = terminal("""
    offline_knowledge query "your question here"
""")
import json
data = json.loads(offline_result["output"])

if data.get("cache", {}).get("status") == "hit":
    # Cache hit — use cached results directly (fastest, cheapest)
    hits = data["cache"]["hits"]
    # Each hit has: query, summary, urls, similarity
    
elif data.get("kiwix", {}).get("status") == "hit":
    # Kiwix hit — ZIM content has the answer
    results = data["kiwix"]["results"]
    # Each has: title, url (localhost:8080), relevance
    
elif data.get("summary", {}).get("source") == "none":
    # Nothing local — proceed with web_search as normal
    
    # Then STORE the result for next time:
    web_results = web_search("your question here")
    terminal(f"""
        echo '{json.dumps(web_results)}' | web_cache store "your question here" -
    """)
```

### Quick Status Check (First Message of Session)

```bash
offline_knowledge stats
```

If kiwix-serve isn't running, start it:
```bash
docker compose -f ~/.hermes/offline/kiwix-docker-compose.yml up -d
```

## Pre-Flight Checklist (Before Going Offline)

```bash
# 1. Download all content
hermes-cortex/offline/prep-offline.sh --mode=travel   # or build/education/all

# 2. Verify everything works
offline_knowledge stats
# Expected: web_cache ✅, kiwix-serve ✅, gbrain ✅
# Expected: ZIM files listing with correct sizes

# 3. Test a cascade query
offline_knowledge query "how to treat a snake bite in the jungle"
# Should return results from ZIM content (no internet needed)

# 4. Done. Unplug and go.
```

## Command Reference

| Command | Description |
|---------|-------------|
| `offline_knowledge query <question>` | Cascade: cache → kiwix → gbrain (recommended) |
| `offline_knowledge cascade-search <question>` | Detailed per-source results |
| `offline_knowledge kiwix-search <term>` | Direct ZIM full-text search |
| `offline_knowledge kiwix-status` | Check if kiwix-serve is running |
| `offline_knowledge kiwix-list` | List all loaded ZIM content |
| `offline_knowledge generate-library` | Regenerate library XML from ZIM files |
| `offline_knowledge stats` | Full system status |

## Available ZIM Content

| ZIM File | Size | What it covers |
|---|---|---|
| `wikivoyage_en_all_nopic` | 232 MB | Travel guides, phrasebooks, safety info for 33,000+ destinations |
| `wikipedia_en_medicine_maxi` | 2.1 GB | Full medical encyclopedia — 70,000+ articles |
| `wikipedia_en_simple_all_maxi` | 3.4 GB | Plain English encyclopedia — all topics |
| `wikipedia_en_all_mini` | 12.4 GB | Full English Wikipedia (compressed, no images) |
| `wikibooks_en_all_maxi` | 1.5 GB | Free textbooks — math, science, programming |
| `wiktionary_en_all_maxi` | 2.2 GB | Dictionary, thesaurus, etymology |

## Architecture

```
Agent question
    │
    ▼
┌─────────────────┐     hit? ──→ Return cached result
│  web_cache       │              (semantic, 768-dim vectors)
│  (SQLite+vectors)│
└────────┬─────────┘
         │ miss
         ▼
┌─────────────────┐     hit? ──→ Return ZIM article
│  kiwix-serve     │
│  (Docker, ZIM)   │
└────────┬─────────┘
         │ miss
         ▼
┌─────────────────┐     hit? ──→ Return brain knowledge
│  gbrain (RAG)    │
└────────┬─────────┘
         │ miss
         ▼
LLM native knowledge / web_search (online only)
```

## Design Principles

- **Transparent**: Same tool works online and offline
- **Cheapest first**: cache → local → network, in order of cost
- **Always useful**: even online, cache hits save API calls and time
- **Portable**: ZIM files + Docker compose = same setup on any machine
- **Private**: everything runs locally — no data leaves your machine
