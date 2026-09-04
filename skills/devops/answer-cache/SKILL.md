---
name: answer-cache
version: 1.0.0
category: devops
description: >-
  Agent protocol for mycortex answer cache — inserts a cache-check step
  between RAG miss and model call. Saves tokens by caching LLM answers
  with quality gating, semantic dedup, and RLS isolation per profile.
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
---

# Answer Cache — Agent Protocol

## Purpose

When mycortex (`search`) misses and the model answers from training data, that
answer is ephemeral. Next session pays the same token cost. This skill inserts
a cache-check step between RAG miss and model call, so repeated queries hit
the local answer cache for 0 tokens.

## Core Flow

```
Query -> mycortex search (hit? use it, 0 tokens)
       -> miss? mycortex answer search (hit? use it, 0 tokens)
       -> miss? model answers (costs tokens)
       -> quality gate passes? mycortex answer store -> future hits local
```

## CLI Commands

All via the `mycortex` CLI (`~/.hermes-cortex/scripts/mycortex`):

### Store an answer

```bash
mycortex answer store "<query>" "<answer>" \
  --confidence high|medium|low \
  --model deepseek/deepseek-v4-flash \
  --tokens 512 \
  --source-scope federated|source_name
```

- Quality gates auto-skip: time-sensitive queries, refusals, PII
- Use `--force` to bypass quality gates
- Use `--update` to overwrite an existing entry for the same query
- Semantic dedup checks before insert (trigram similarity > 0.6)

### Search cached answers

```bash
mycortex answer search "<query>" [--limit 10] [--min-score 0.0] [--json]
```

- Returns exact matches first, then trigram similarity matches
- `--min-score 0.5` filters low-confidence semantic matches
- `--json` for machine-readable output

### View statistics

```bash
mycortex answer stats [--json]
```

### Prune stale entries

```bash
mycortex answer prune [--days 90] [--min-access 0] [--dry-run]
```

## Agent Protocol

### Step 1: Search mycortex (existing RAG)
```python
result = terminal("mycortex search '<query>' --limit 5 --json")
```

### Step 2: On miss, check the answer cache
```python
result = terminal("mycortex answer search '<query>' --limit 3 --min-score 0.5 --json")
```

### Step 3: Model fallback + auto-store
```python
# Only if both searches yield nothing useful
# After getting the model's answer:
terminal("mycortex answer store '<query>' '<answer>' --confidence medium --tokens <N>")
```

### Step 4: Verify the cached answer is used on repeat
```python
result = terminal("mycortex answer search '<query>' --json")
# -> returns the stored answer with 0 token cost
```

## Quality Gate Rules

| Gate | What it prevents | Bypass |
|------|-----------------|--------|
| Time-sensitive | "current weather", "latest news" — content becomes stale | `--force` |
| Refusal | LLM "I cannot help" patterns — don't cache dead ends | `--force` |
| PII | Emails, phones, IPs in answers — never cache | `--force` |
| Semantic dedup | Similar query, same answer — don't duplicate | `--force` |

## Source Scope

- **`federated`** (default) — visible to ALL agents (like federated brain sources)
- **`<source_name>`** — visible only to agents with a grant for that source
  (matches the RLS model: `mycortex.source_grants` controls per-role visibility)

## RLS Isolation

The same per-profile isolation model applies: each Hermes profile connects as
`mycortex_reader_<profile>` and sees only answers whose `source_scope` is
`federated` OR whose scope matches a source the profile has a grant for.

## Pruning

The existing `agent-mycortex-retention` cron handles stale answers:
- Orphaned answers: archived after 90 days with zero access
- Active low-use: access_count < 3 after 180 days
- Manual: `mycortex answer prune --days 90 --min-access 0`

## Test Commands

```bash
mycortex answer store "What is the capital of France?" "Paris" \
  --confidence high --tokens 5 --force

mycortex answer search "capital of France" --json

mycortex answer stats

mycortex answer prune --days 0 --min-access 0 --dry-run
```
