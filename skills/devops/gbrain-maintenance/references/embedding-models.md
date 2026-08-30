# Embedding Model Configuration & Verification

## Overview

gbrain uses a local Ollama embedding model to vectorize brain pages for semantic search.
The model is configured in two places:

| Location | Key | Example |
|----------|-----|---------|
| `~/.gbrain/config.json` | `embedding_model` | `ollama:nomic-embed-text:v1.5` |
| `~/.hermes/models.env` | `EMBEDDING_MODEL` | `nomic-embed-text:v1.5` |

## Model Selection Criteria

| Model | Size | Context | Dims | Notes |
|-------|------|---------|------|-------|
| `nomic-embed-text` (v1) | 274 MB | 2048 tokens | 768 | Default, but **overflows on pages >~500 words** — returns empty embeddings |
| **`nomic-embed-text:v1.5`** | **274 MB** | **8192 tokens** | **768** | ✅ **Drop-in replacement. Same size, same dims, native 8K context.** |
| `jina-embeddings-v2-small-en` | ~350 MB | 8192 tokens | 768 | Viable alternative, slightly larger |

### Why v1.5 won

- **Same size** (274 MB, ~137M params) → fits CPU + limited RAM
- **Same 768 dimensions** → no index rebuild needed
- **Native 8192 context** → handles any brain page without overflowing
- **Drop-in** — just change the model name, no config migration

## How to Swap Models

```bash
# 1. Pull the new model
ollama pull nomic-embed-text:v1.5

# 2. Update models.env
#    Change EMBEDDING_MODEL=nomic-embed-text → nomic-embed-text:v1.5

# 3. Update gbrain config
#    vim ~/.gbrain/config.json → change embedding_model to "ollama:nomic-embed-text:v1.5"
```bash
# 4. Restart autopilot (systemd)
systemctl --user restart gbrain-autopilot.service

# Verify
systemctl --user status gbrain-autopilot.service
```

### Environment Variables for Autopilot

The systemd service at `~/.config/systemd/user/gbrain-autopilot.service` should include:

```ini
Environment=GBRAIN_AI_EMBED_TIMEOUT_MS=300000
```

This prevents embedding timeouts on large pages (5 min per-call timeout).
After editing the service file: `systemctl --user daemon-reload && systemctl --user restart gbrain-autopilot.service`
# 5. Verify (see below)
```

## Verification

### Direct Ollama API test

Use Python to test the model returns valid embeddings for long content:

```python
import requests

# Short smoke test
resp = requests.post("http://localhost:11434/api/embed",
    json={"model": "nomic-embed-text:v1.5", "input": "Hello world."},
    timeout=120)
data = resp.json()
embeds = data.get("embeddings", [])
# Expected: 1 embedding, 768 dims, non-zero values

# Long content test (brain page that would overflow v1)
with open("/path/to/brain/page.md") as f:
    content = f.read()

resp = requests.post("http://localhost:11434/api/embed",
    json={"model": "nomic-embed-text:v1.5", "input": content},
    timeout=120)
data = resp.json()
embeds = data.get("embeddings", [])
# Check: len(embeds) == 1, len(embeds[0]) == 768
# Check for all non-zero: sum(1 for x in embeds[0] if abs(x) != 0)
```

**Key checks:**
- `len(embeds) == 1` — exactly one embedding vector returned
- `len(embeds[0]) == 768` — correct dimensionality
- Non-zero dims should be 766-768 (a few near-zero values are normal)
- Test with content >2048 tokens to confirm the model handles it

### Cold-start note

The first API call after pulling a model may **timeout** (30s default). The model needs to load into memory. Use `timeout=120` in your Python request, or warm the model first:

```bash
curl -s --max-time 60 http://localhost:11434/api/embed \
  -d '{"model":"nomic-embed-text:v1.5","input":"warmup"}' > /dev/null
```

After warmup, embedding calls are fast (~45ms per short text).

## Known Issues

### Symptom: gbrain returns empty embeddings for long pages

**Root cause:** `nomic-embed-text` (v1) has a 2048-token context limit.
Brain pages over ~500 words (~2000 chars) overflow the context window and
the model returns `"embeddings": []` — an empty array.

**Fix:** Swap to `nomic-embed-text:v1.5` (native 8192-token context).

### Symptom: `ollama/api/embed` returns empty embeddings for short text too

**Root cause (likely):** Shell escaping. When passing content through bash
string interpolation, newlines break the JSON payload. Use a Python script
with `json.dumps()` or write the payload to a file and use `@file`.

### Symptom: `nomic-embed-text:v1.5` not showing in `ollama ps`

Expected — `ollama ps` only shows **loaded** models. `nomic-embed-text:latest`
(v1) may be loaded because it was used recently. v1.5 gets loaded on first
use, then stays in memory for `keep_alive` duration (default 5 min).

Check available models:
```bash
ollama list | grep nomic
```
