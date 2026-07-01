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
hermes-cortex/src/offline/prep-offline.sh

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
hermes-cortex/src/offline/prep-offline.sh --mode=travel   # or build/education/all

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
| `offline_knowledge bible search "verse" --lang en` | Search Bible translations |
| `offline_knowledge bible list` | List available translations |
| `offline_knowledge hymns search "Amazing Grace"` | Search hymn lyrics across all hymns |
| `offline_knowledge hymns list` | List hymn resources (PDF, ABC, XML) |
| `./src/offline/prep-bible.sh --langs=all` | Download all Bible translations |
| `./src/offline/prep-hymns.sh` | Download public domain hymns from Open Hymnal Project |
| `python3 src/offline/offline-reader.py` | Launch local web UI for browsing Bible, hymns, and reference |
| `./src/offline/auto-update.sh` | Check for content updates (silent if offline) |
| `offline_knowledge stats` | Full system status |
| `offline_code search <query>` | Semantic + keyword search over 367 code snippets, 27 languages |
| `offline_code search "<query>" --lang go` | Search filtered by language |
| `offline_code gen "<prompt>"` | RAG code generation using Ollama (context from matching snippets) |
| `offline_code gen "<prompt>" --model qwen2.5-coder:7b` | Code gen with a larger model |
| `offline_code index --force` | Rebuild the embedding index (after adding snippets) |
| `offline_code stats` | Corpus statistics |

## Available ZIM Content

| ZIM File | Size | What it covers |
|---|---|---|
| `wikivoyage_en_all_nopic` | 232 MB | Travel guides, phrasebooks, safety info for 33,000+ destinations |
| `wikipedia_en_medicine_maxi` | 2.1 GB | Full medical encyclopedia — 70,000+ articles |
| `wikipedia_en_simple_all_maxi` | 3.4 GB | Plain English encyclopedia — all topics |
| `wikipedia_en_all_mini` | 12.4 GB | Full English Wikipedia (compressed, no images) |
| `wikibooks_en_all_maxi` | 1.5 GB | Free textbooks — math, science, programming |
| `wiktionary_en_all_maxi` | 2.2 GB | Dictionary, thesaurus, etymology |

### 📖 Bible Content

Bible translations can be downloaded alongside wiki content. Available in 55+ languages
including English (KJV, WEB, ASV, YLT), Spanish, French, German, Korean, Japanese, Chinese,
Arabic, Russian, and many more.

```bash
# Download major world language translations:
./src/offline/prep-bible.sh --langs=major

# Download all 55+ translations:
./src/offline/prep-bible.sh --langs=all

# Combine with offline prep:
./src/offline/prep-offline.sh --mode=travel --include-bible
```

Search Bible verses:
```bash
offline_knowledge bible search "John 3:16"
offline_knowledge bible search "faith" --lang en
offline_knowledge bible search "사랑" --lang ko
offline_knowledge bible list
```

Bible texts are small (4-10 MB per translation) and work without Docker.

### 🎵 Hymn Content

Public domain hymns from the [Open Hymnal Project](https://openhymnal.org). Includes:

- **Full hymnal PDF** with music scores (8 MB)
- **ABC notation files** — text-based music notation (2 MB)
- **MIDI audio files** — play hymns on any device (336 kB)
- **ThML XML** with structured lyrics and metadata (2 MB)
- **Seasonal editions** — Christmas, Easter, Visitation (bonus)

```bash
# Download the core hymnal:
./src/offline/prep-hymns.sh

# Download with seasonal editions:
./src/offline/prep-hymns.sh --editions=all

# Combine with offline prep:
./src/offline/prep-offline.sh --mode=travel --include-hymns
```

Search hymns:
```bash
offline_knowledge hymns search "Amazing Grace"
offline_knowledge hymns search "rock of ages"
offline_knowledge hymns list
```

Hymn content is ~35 MB total and works without Docker. View the PDF in any reader for printable scores.

### 📖 Offline Reader — Visual Browsing

For non-technical users, a local web UI provides point-and-click access to all offline content:

```bash
python3 src/offline/offline-reader.py
# Opens http://localhost:8081 in your browser
```

Features:
- **Bible reader** — select translation → pick book → read chapter by chapter
- **Hymn browser** — search by title/lyrics, view full text
- **Reference search** — queries kiwix-serve (Wikipedia, WikiMed, etc.)
- **Global search** — searches all sources at once from the home page
- Dark theme, zero dependencies, works completely offline

### 🔄 Auto-Update

A silent cron-friendly script that checks for content updates:

```bash
# Manual check:
./src/offline/auto-update.sh

# Dry run:
./src/offline/auto-update.sh --check

# As a weekly cron job (no_agent, zero token cost):
hermes cron create \
  --name "offline-content-update" \
  --schedule "0 9 * * 0" \
  --script "auto-update.sh" \
  --no-agent \
  --deliver "origin"
```

Behavior:
- **Offline aware** — exits silently if no internet (no spam)
- **Only changes when needed** — HEAD checks before downloading
- **Bible** — parses any unparsed `.txt` files to `.json`
- **Hymns** — checks Open Hymnal PDF/XML for size changes
|- **Silent** — only produces output when something actually changed

---

## 💻 Offline Code Assistant

A curated corpus of **367 code snippets** across **27 languages** with semantic search and RAG-powered code generation — all running locally via Ollama.

### What's Included

| Tier | Languages | Snippets |
|------|-----------|----------|
| **Tier 1** — Production core | Python (26), JavaScript (22), TypeScript (15), Go (22), Rust (21), Java (20), SQL (12), Shell (8) | 146 |
| **Tier 2** — Major ecosystems | C (18), C++ (22), C# (18), PHP (15), Ruby (15), Swift (15), Kotlin (15) | 118 |
| **Tier 3** — Growing/admired | Zig (12), Dart (15), Elixir (10), Lua (10), R (12) | 59 |
| **Tier 4** — Infra DSLs | Docker (5), Terraform (10), K8s (5), Nix (10), PowerShell (10) | 40 |

### Quick Start

```bash
# Index is pre-built; if needed, rebuild:
offline_code index --force

# Search for snippets
offline_code search "goroutine channel buffered"
offline_code search "spring boot rest api" --lang java

# Generate code from context
offline_code gen "worker pool pattern in go"

# See stats
offline_code stats
```

### How It Works

- **Corpus source:** `src/offline/code-corpus/snippets/*.py` — per-language Python modules export snippet definitions
- **Generator:** `python3 src/offline/code-corpus/generate.py` writes formatted `.md` files with YAML frontmatter
- **Embedding:** `offline_code index` batches snippets into groups of 10, embeds with Ollama `nomic-embed-text` (768-dim)
- **Search:** single-embed query → cosine similarity against stored embeddings + keyword boost
- **Generation:** top-3 matching snippets injected as context → `qwen2.5-coder:3b` (or your model)

### Adding Snippets

```bash
# 1. Create a new module or edit an existing one in:
#    src/offline/code-corpus/snippets/<language>_snippets.py
#
# Each module exports SNIPPETS — a list of 7-tuples:
#   (rel_path, language, tags, title, description, source, code)

# 2. Regenerate .md files
python3 src/offline/code-corpus/generate.py

# 3. Rebuild index
offline_code index --force
```

### Resource Usage

| Component | RAM | Notes |
|-----------|-----|-------|
| nomic-embed-text | ~300 MB | Shared with other offline tools |
| qwen2.5-coder:3b | ~1.9 GB | Optional — only loaded during `gen` |
| Corpus files | 3 MB disk | Text + 768-dim embeddings |

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
