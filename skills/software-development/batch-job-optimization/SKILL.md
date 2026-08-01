---
name: batch-job-optimization
description: "Systematically analyze and optimize database-bound batch processing jobs (imports, exports, ETL, bulk updates) in Rails and similar frameworks."
version: 1.0.0
author: Hermes Cortex
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [performance, optimization, batch, database, profiling, queries]
    related_skills: [root-cause-debugging, project-map, server-hardening]
---

# Batch Job Optimization

## When to Use

- User reports a job is "too slow" (import, export, migration, ETL, bulk update)
- User asks "why is this import taking hours?"
- User asks "how can I make this job faster?"
- User asks you to analyze slow queries in a batch context
- A job processes large datasets row-by-row or in small batches

This is for BATCH jobs, not web request latency. Web performance profiling uses different tools (rack-mini-profiler, scout, skylight).

## The Methodology

A batch job's performance is determined by the number of queries per **record**, and the cost of each query. Optimization is a two-step discipline:

1. **Measure** — profile to find the actual bottleneck (never guess)
2. **Fix the dominant term** — the pattern producing O(N) or O(N×M) queries

## Step 1: Measure

### Baseline timing

```bash
# Time the whole job
time rails runner 'ImportJob.new.perform'

# Time with SQL logging to count queries
rails runner 'ActiveRecord::Base.logger = Logger.new(STDOUT); ImportJob.new.perform' 2>&1 | grep -c "SELECT\|INSERT\|UPDATE"
```

### Find the query count per record

```ruby
# Wrap the inner loop and count queries per iteration
queries_before = ActiveRecord::Base.connection.query_cache.size
# ... one iteration ...
queries_after = ActiveRecord::Base.connection.query_cache.size
```

Or use `ActiveSupport::Notifications` to count queries:

```ruby
count = 0
ActiveSupport::Notifications.subscribe("sql.active_record") { |*| count += 1 }
ImportJob.new.perform
puts "Total SQL queries: #{count}"
```

### Identify the top offenders

```bash
# Rails: enable query logging, then grep the top repeated queries
rails runner 'ActiveRecord::Base.logger = Logger.new(STDOUT); ImportJob.new.perform' 2>&1 | \
  grep -oP 'SELECT .{0,80}' | sort | uniq -c | sort -rn | head -10
```

## Step 2: Fix the Dominant Term

### Anti-pattern 1: N+1 queries

The classic: one query per record inside a loop.

```ruby
# ❌ 1 query per user → N queries
users.each do |user|
  puts user.orders.count    # SELECT count(*) FROM orders WHERE user_id = ?
end

# ✅ 1 query total
counts = Order.group(:user_id).count
users.each do |user|
  puts counts[user.id] || 0
end
```

Fix with `includes`/`preload`/`eager_load`, or better: one aggregate query.

### Anti-pattern 2: Row-by-row writes

```ruby
# ❌ N INSERTs
rows.each do |row|
  Record.create!(row)
end

# ✅ 1 bulk INSERT (Rails 6+)
Record.insert_all!(rows)          # skips callbacks — verify you don't need them
# or with callbacks:
records = rows.map { |r| Record.new(r) }
Record.import!(records)           # activerecord-import gem
```

### Anti-pattern 3: Loading columns you don't need

```ruby
# ❌ SELECT * for 10 columns, uses 2
users = User.all
users.each { |u| puts u.name }

# ✅ Only the columns used
users = User.select(:id, :name).all
```

### Anti-pattern 4: Re-querying the same data per record

```ruby
# ❌ Lookup per record
rows.each do |row|
  country = Country.find_by(code: row[:country_code])   # N queries
end

# ✅ Cache the lookup
countries = Country.where(code: rows.map { |r| r[:country_code] }).index_by(&:code)
rows.each do |row|
  country = countries[row[:country_code]]
end
```

### Anti-pattern 5: Missing index

```sql
-- Query filters on status + created_at but only id is indexed
EXPLAIN ANALYZE SELECT * FROM records WHERE status = 'pending' AND created_at < NOW();
-- → Seq Scan on records (cost=... rows=... width=...)

-- Add the composite index
CREATE INDEX CONCURRENTLY index_records_on_status_and_created_at
  ON records (status, created_at);
```

```ruby
# Rails migration
add_index :records, [:status, :created_at]
```

## The Numbers Game

Track these before/after numbers and report them:

| Metric | Before | After |
|--------|--------|-------|
| Wall time | 3h 12m | 18m |
| Total SQL queries | 2,400,000 | 3,100 |
| Queries per record | 12 | 1.2 |
| Rows per write | 1 | 5,000 (bulk) |

## Batching & Memory

A job that loads ALL rows into memory will OOM on large datasets:

```ruby
# ❌ Loads everything
User.find_each { |u| ... }       # find_each IS batched (default 1000)

# ✅ Explicit batch size + find_in_batches for raw access
User.find_in_batches(batch_size: 5000) do |batch|
  # process batch
end
```

Also consider `in_batches(of: 5000)` (Rails 6+) with `update_all`:

```ruby
User.where(active: true).in_batches(of: 5000).update_all(flag: true)
```

## Verification

```bash
# Re-run the same benchmark after the fix
time rails runner 'ImportJob.new.perform'
# Compare: wall time, query count, memory (see below)

# Memory check
/usr/bin/time -v rails runner 'ImportJob.new.perform' 2>&1 | grep "Maximum resident"
```

## Pitfalls

- ❌ **Optimizing without measuring** — the "obvious" slow part is often not the bottleneck
- ❌ **`insert_all!` when callbacks matter** — it skips validations/callbacks silently; audit first
- ❌ **Index on the wrong columns** — index for the WHERE, not just the first column you see
- ❌ **Batch size too large** — 50k+ row batches cause transaction bloat; tune empirically
- ❌ **Optimizing the loop when the DB is the bottleneck** — check `EXPLAIN` first

## Related
- `root-cause-debugging` — 6-phase debugging framework
- `project-map` — understand the codebase structure first
- `rails-data-pipeline-debugging` — data transformation debugging in Rails
- `server-hardening` — system-level tuning (complementary)
