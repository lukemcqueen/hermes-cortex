# Verification playbook

Load when you will run measurements or need to specify concrete verification steps.

## Golden rules

- **Safety first**: never run destructive benchmarks or touch production data. Dev/staging only.
- **Realism**: measure the operation mix, sizes, and cardinality the code actually faces.
- **Same input, same environment**: before/after differ in exactly one variable.
- **Include construction cost**: index/map/cache built per request costs as much as it saves.
- **Honest reporting**: state wall-clock vs CPU, warm vs cold, release vs debug.

## What to measure per finding type

| Finding | Confirm with |
|---|---|
| Scan-in-loop / index / top-k / queue | micro or path benchmark at realistic n; assert same output |
| N+1 / query shape | SQL query count per request/job, rows scanned vs returned |
| Index usefulness | `EXPLAIN` on the real predicate/order (safe env) |
| Over-fetch / materialization | rows/objects/bytes loaded vs used |
| Unbounded retention | cache size over time; live bytes |
| Contention / lock | block profile, queue depth |
| Layout/locality | allocation profile, cache-miss counters |

## Quick commands by language

Ruby/Rails: count SQL queries:
```ruby
count = 0
ActiveSupport::Notifications.subscribed(
  ->(*) { count += 1 }, "sql.active_record"
) { run_the_path }
puts count
```

Python:
```bash
python -m timeit -s "setup" "stmt"
python -m cProfile script.py
```

Next.js/TypeScript: `--cpu-prof`/`--heap-prof`, framework/server timings, DB query metrics, RSC payload bytes.

Rust: `cargo test --release` then benchmark release binary.

Go: `go test -race ./...`; `go test -bench=. -benchmem ./pkg`; `-cpuprofile`/`-memprofile`/`-blockprofile`.

## When you cannot measure anything

State `Evidence: needs measurement` plus the exact step that would confirm it. Workload-unknown findings stay confidence Medium and severity ≤ Medium unless unbounded growth or unambiguous asymptotics are provable.

## Decision rule

A recommendation graduates from hypothesis to confirmed only when:
1. The asymptotic defect is unambiguous at known production cardinality
2. Query-plan/count evidence establishes amplification
3. A benchmark or profile shows material cost
4. Unbounded lifetime proves a credible memory-growth path