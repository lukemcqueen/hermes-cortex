# Answer Cache Implementation (S-017, 2026-09-03)

## Design Intent

When mycortex (`search`) misses and the model answers from training data, that
answer is ephemeral. Next session pays the same token cost. The answer cache
inserts a local-DB lookup between RAG miss and model call.

Key rule: **works with ALL repos an agent has, not just hermes-cortex** —
source_scope on answers controls visibility (federated or per-source-name).

## Files Created

| File | Purpose |
|------|---------|
| `ops/services/mycortex/schema/v005__answers.sql` | Schema migration — `mycortex.answers` table, RLS policies, indexes, grants |
| `ops/scripts/manage/mycortex` (modified) | Added `answer store/search/stats/prune` subcommands (~600 lines) |
| `skills/devops/answer-cache/SKILL.md` | Agent protocol skill — step-by-step caching flow |
| `ops/install/install.sh` (modified) | Creates `~/brain/answers/` dir, registers as mycortex source |

## Key Implementation Details

### Schema

The `mycortex.answers` table:
- `query` / `normalized_query` (lowercased+stripped for matching) / `answer`
- `query_hash` (sha256 of normalized query) for exact dedup
- `answer_hash` (sha256 of answer) for content change detection
- `source_scope` — `'federated'` (all agents) or a source name (isolated)
- `confidence` — `high` / `medium` / `low`
- `quality_gate` — `passed` / `refused` / `pii_rejected` / `time_sensitive`
- `token_count` / `model` / `agent_name` for cost tracking
- `accessed_at` / `access_count` for LRU pruning

Indexes: GIN on query and normalized_query trigrams, GIN on FTS, btree on
created_at DESC and access_count. All partial (WHERE NOT archived).

### RLS

Same per-profile isolation model as page sources:
- `mycortex.is_answer_visible(answer_id, role)` SECURITY DEFINER helper
- Federated answers visible to all; source-scoped answers need a `source_grants` row
- FORCE RLS on answers table with 5 policies (admin SELECT/INSERT/UPDATE,
  ingest ALL, reader SELECT)

### Quality Gates

Auto-applied on `answer store` (unless `--force`):

1. **Time-sensitive** — keywords like "current", "today", "weather", "news", "price"
2. **Refusal** — regex patterns matching "I cannot", "as an AI", "I'm sorry"
3. **PII** — email, phone (###-###-####), IP address regex
4. **Semantic dedup** — trigram similarity > 0.6 on normalized_query before insert

### CLI Details

```bash
# Store — dedup by query hash, then semantic similarity
mycortex answer store "<query>" "<answer>" [--confidence] [--model] [--tokens] [--force] [--update] [--source-scope]

# Search — exact hash first, trigram similarity 0.4+, ILIKE fallback
mycortex answer search "<query>" [--limit N] [--min-score 0.0] [--json]

# Stats — aggregate counts by confidence, quality, source, token metrics
mycortex answer stats [--json]

# Prune — archive old/low-access entries
mycortex answer prune [--days 90] [--min-access 0] [--dry-run]
```

### Agent Protocol (4 steps)

1. `mycortex search "<query>" --limit 5 --json` — existing RAG
2. `mycortex answer search "<query>" --limit 3 --min-score 0.5 --json` — cache check
3. Model fallback → `mycortex answer store "<query>" "<answer>" --confidence medium --tokens <N>` — auto-store
4. Repeat query now hits cache (0 tokens)

### Pitfalls Found During Implementation

- **Semantic dedup needs `normalized_query` column, not raw query** — trigram
  similarity on `"capital of France"` vs `"capitol of france"` fails without
  normalization. Fixed mid-implementation.
- **CLI reads as `mycortex_reader` for dedup checks** — the ingest role can't
  `SELECT` for existence checking before insert; reader role + RLS is correct.
- **`--force` bypasses ALL quality gates** — design paper says "quality gate
  passes? auto-store", but `--force` exists for known-safe content.
- **Install.sh: register answers as local mode, not git** — answers are
  DB-only, the `~/brain/answers/` dir is for future file-based export/import.
