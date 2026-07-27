# Loop Governance Data Schema

Reference for the self-improvement data layer. Schema is auto-created by `loop_db.py`.

## Tables

### loop_cycles

Primary table: one row per scored loop iteration.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| timestamp | TEXT | ISO datetime of scoring |
| task_id | TEXT | Which task this cycle belongs to |
| cycle_num | INTEGER | 1-based cycle number within the task |
| spec_hash | TEXT | FK to content_assets (spec text) |
| code_hash | TEXT | FK to content_assets (implementation) |
| test_output_hash | TEXT | FK to content_assets (test runner output) |
| completeness | REAL | 0-10 |
| quality | REAL | 0-10 |
| progress | REAL | 0-10 |
| composite | REAL | 0-10 (weighted blend) |
| no_progress | INTEGER | Boolean — 1 if progress < no_progress_score |
| decision | TEXT | STOP / LOOP / MOVE ON / STOP (fail) |
| user_overrode | INTEGER | NULL=unknown, 0=accepted, 1=overrode |
| outcome_note | TEXT | Free-text user note |
| schema_version | INTEGER | Default 1 |
| model_name | TEXT | Embedding model used (default: nomic-embed-text) |

### content_assets

Content-addressable store for deduplication.

| Column | Type | Description |
|--------|------|-------------|
| hash | TEXT PK | SHA-256 first 16 hex chars |
| content | TEXT | The actual text (sanitized) |
| type | TEXT | spec / code / test_output |
| created | TEXT | ISO datetime |

### config_history

Rollback tracking for threshold/config changes.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| applied_at | TEXT | ISO datetime |
| config_json | TEXT | Full config snapshot |
| diff_from_previous | TEXT | What changed |

## Useful Analysis Queries

```sql
-- Decision distribution
SELECT decision, COUNT(*) as count
FROM loop_cycles GROUP BY decision ORDER BY count DESC;

-- Average scores by decision type
SELECT decision,
       AVG(completeness) as avg_comp,
       AVG(quality) as avg_qual,
       AVG(composite) as avg_comp
FROM loop_cycles
GROUP BY decision;

-- Tasks that spun the most (highest no-progress ratio)
SELECT task_id,
       COUNT(*) as cycles,
       SUM(no_progress) as np_cycles,
       ROUND(100.0 * SUM(no_progress) / COUNT(*), 1) as np_pct
FROM loop_cycles
GROUP BY task_id
HAVING np_pct > 30
ORDER BY np_pct DESC;

-- Decision accuracy (requires user_overrode to be set)
SELECT decision,
       SUM(CASE WHEN user_overrode = 0 THEN 1 ELSE 0 END) as accepted,
       SUM(CASE WHEN user_overrode = 1 THEN 1 ELSE 0 END) as overridden,
       COUNT(*) as total
FROM loop_cycles
WHERE user_overrode IS NOT NULL
GROUP BY decision;
```