---
name: offline-code
version: 1.0.0
category: devops
description: "Offline code snippet search + generation using local Ollama models. Search a 518-snippet corpus across 32 categories with nomic-embed-text, generate code with auto-detected qwen2.5-coder (1.5b on 4-8GB, 7b on 8-24GB, 14b on 24GB+). No internet needed."
author: Titus
license: MIT
metadata:
  hermes:
    tags: [offline, code, rag, search, generation, nomic, qwen]
---

# Offline Code — Local Snippet Search & Generation

A two-tier local coding assistant: **search** a curated corpus of algorithms and patterns, then **generate** code using Ollama. All data stays on your machine.

```
                        offline_code
                       /            \
              search                   gen
                 │                       │
                 ▼                       ▼
      nomic-embed-text            qwen2.5-coder:1.5b
      (embeds query,              (RAG: top-3 snippets
       cosine similarity           + user prompt → code)
       → ranked snippets)
```

## Installation

```bash
# Step 1: Symlink the CLI wrapper
ln -sf ~/hermes-cortex/src/offline/offline_code.sh ~/.hermes/bin/offline_code

# Step 2: Verify CLI
offline_code stats

# Step 3: (Re)build the search index if needed
offline_code index --force

# Step 4: Ensure models are pulled
ollama pull nomic-embed-text        # already pulled by install.sh
ollama pull qwen2.5-coder:1.5b      # minimum (64K context, needed for gen)
```

## Usage

### Search for code patterns

```bash
offline_code search "flask rest api"
offline_code search "binary search tree rust"
offline_code search "retry pattern with backoff"
```

Returns top-matching snippets from the corpus, ranked by cosine similarity.

### Generate code using RAG

```bash
offline_code gen "binary search tree in rust"
offline_code gen "flask api with sqlalchemy"
offline_code gen "terraform aws vpc with subnets"
```

The generator: (1) finds top-3 matching snippets via search, (2) injects them as context, (3) sends everything to qwen2.5-coder:1.5b for generation. Result: small model + good context ≈ much larger model's quality.

### Index management

```bash
offline_code index            # incremental index (skips if current)
offline_code index --force    # full rebuild
offline_code stats            # corpus + index stats
```

## Agent Workflow — MANDATORY: Check Offline Before Web

This workflow is **mandatory** for all LLM cron jobs and coding sessions.
Before calling `web_search()`, you MUST follow this order:

```
1. offline_code search "<your pattern>"
     └── hit? → Use the snippet directly or adapt it. ZERO API COST.
     └── miss? → Go to step 2

2. offline_code gen "<your request>"
     └── Generates code using RAG + qwen2.5-coder
     └── Good for: algorithms, patterns, glue code

3. web_search (LAST RESORT — only if offline has nothing useful)

### Self-Learning: Fill Gaps
When `web_search()` finds something useful that the corpus missed:
1. **`offline_code learn "<title>" --lang <lang> --tags "<tags>" --desc "<desc>" --code "<code>"`**
2. This creates a new `.md` snippet in the correct language directory
3. **Next index refresh** (weekly cron or manual `offline_code index --force`) bakes it in
4. Future searches will find it — the corpus improves over time

Without explicit `--code`, you can pipe via stdin: `echo "code" | offline_code learn "Title"`
```

Skipping the offline check and going straight to `web_search()` is a
**quality gate failure** — it wastes API credits on questions the 518-snippet
corpus can answer for free.

This saves API costs, works offline, and is faster than web search.

## How It Works

| Component | Model | Size | Purpose |
|---|---|---|---|
| Search indexing | nomic-embed-text | 261 MB | Embed snippets into 768-dim vectors |
| Query embedding | nomic-embed-text | — | Embed your search query for cosine comparison |
| Code generation | Auto-detected qwen2.5-coder | varies | **1.5b** on 4-8GB RAM (default, 64K ctx) |
| | | | **7b** on 8-24GB RAM (better quality) |
| | | | **14b** on 24GB+ RAM (best quality) |

The model is auto-selected based on available RAM. You can override with `--model`:
```bash
offline_code gen "binary search tree" --model qwen2.5-coder:7b
offline_code gen "api endpoint" --model qwen2.5-coder:1.5b
```

The corpus lives at `~/hermes-cortex/src/offline/code-corpus/` with 366 snippets across 25 languages. Index stored at `~/offline/code-index.json`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `offline_code: command not found` | `ln -sf ~/hermes-cortex/src/offline/offline_code.sh ~/.hermes/bin/offline_code` |
| `nomic-embed-text not found` | `ollama pull nomic-embed-text` |
| `qwen2.5-coder not found` | `ollama pull qwen2.5-coder:1.5b` (minimum, auto-detects higher) |
| `Index is current` on `--force` | Use `--force` flag to rebuild |
| Corpus empty / no snippets | Run `offline_code index --force` to build from scratch |
| Slow search | First run indexes all snippets — subsequent runs use cached index |