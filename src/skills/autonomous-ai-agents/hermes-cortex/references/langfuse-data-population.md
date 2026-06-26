# Langfuse Sample Data Population

When the Langfuse web container cycles restart (Next.js exits after init, Docker restart:always kicks in), the API is only available in brief ~2-second windows. Direct Postgres insertion via `docker exec` bypasses this entirely.

## Schema

Key tables for trace data:

- **traces** — top-level units of work (conversations, code reviews, API calls)
- **observations** — spans within traces (generations, LLM calls). `type = 'GENERATION'`
- **scores** — evaluations on traces or observations (quality, accuracy, cost-efficiency)

## Insert Template

```sql
-- Trace
INSERT INTO traces (id, timestamp, name, project_id, metadata, user_id, input, output, tags, session_id)
VALUES ('trace-<name>-<seq>', now() - interval '<N> minutes', '<display-name>', 'default-project',
        '{"key": "value"}'::jsonb, 'luke',
        '"Input text"', '"Output text"',
        ARRAY['tag1', 'tag2'],
        'session-<id>');  -- optional

-- Generation (observation)
INSERT INTO observations (id, name, trace_id, type, project_id, model, "modelParameters", input, output,
                          prompt_tokens, completion_tokens, total_tokens,
                          start_time, end_time, input_cost, output_cost, total_cost,
                          level, status_message)
VALUES ('obs-<name>-<seq>', '<generation-name>', 'trace-<parent-id>', 'GENERATION', 'default-project',
        'model-name',
        '{"temperature": 0.7, "maxTokens": 500}'::jsonb,
        '"Input"', '"Output"',
        25, 15, 40,
        now() - interval '<N> minutes', now() - interval '<N-1> minutes',
        0.00001, 0.0000075, 0.0000175,
        'ERROR', 'error message');  -- level optional, defaults to DEFAULT

-- Score
INSERT INTO scores (id, "timestamp", name, value, trace_id, project_id, source, data_type, comment)
VALUES ('score-<name>-<seq>', now() - interval '<N> minutes', 'metric-name', 0.92,
        'trace-<parent-id>', 'default-project', 'API', 'NUMERIC',
        'Comment about the score');
```

## Key Facts

- **Project ID** is always `'default-project'` — not a UUID, not `cmq-` prefixed
- **modelParameters** is case-sensitive — must be quoted: `"modelParameters"`
- **timestamp** is also case-sensitive on scores: `"timestamp"`
- **Input/output** must be valid JSON strings (double-quoted): `'"text"'` not `'text'`
- **Costs** are in dollars (USD), stored as `numeric(65,30)`
- **Tags** are PostgreSQL text arrays: `ARRAY['tag1', 'tag2']`

## Verification

```sql
SELECT 'Traces:' as metric, count(*) as count FROM traces WHERE project_id = 'default-project';
SELECT 'Generations:' as metric, count(*) as count FROM observations WHERE project_id = 'default-project' AND type = 'GENERATION';
SELECT 'Scores:' as metric, count(*) as count FROM scores WHERE project_id = 'default-project';
SELECT 'Sessions:' as metric, count(DISTINCT session_id) as value FROM traces WHERE session_id IS NOT NULL;
SELECT format('Total Cost: %s', round(sum(total_cost)::numeric, 6)) as value FROM observations WHERE project_id = 'default-project' AND total_cost IS NOT NULL;
```

## When to Use Direct SQL vs API

| Method | When | Why |
|--------|------|-----|
| **Direct SQL** | Web container cycles, API unavailable, or bulk import | Bypasses the ~2s serving window |
| **REST API** | Server is stable, single traces | Proper auth, validation, auto-flushing |
