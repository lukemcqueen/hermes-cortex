---
name: data-structure-efficiency-review
description: Find inefficient data structures and hot loops in code.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [code-review, performance, data-structure, efficiency, refactoring, N+1, hot-loop, memory, database, ORM]
    related_skills: [code-review, requesting-code-review]
---

# Data Structure Efficiency Review

Find structural inefficiency — in-memory collections, object layout, database tables/indexes, ORM loading, caches, queues, serialized payloads, streams, concurrency structures — and refactor it with minimal, semantics-preserving patches.

## The honesty rule (read first)

Separate every finding into one of:

1. **Proven from code** — complexity or behavior follows directly from the implementation.
2. **Highly likely** — recognizable structural smell; impact depends on workload/cardinality.
3. **Needs measurement** — requires benchmark, profiler, query plan, allocation profile, or production trace.

Never claim "this is faster" without a measurement or an unambiguous asymptotic win. Never claim an index helps without a real predicate/query shape. Small contiguous collections can beat hashed/tree structures at low n due to constant factors and locality.

## Do this in order

1. **Scope and inventory** — decide what you are reviewing and list the code that moves data.
2. **Find the hot paths** — loops, request handlers, per-row DB/API calls, retained structures.
3. **Run the pattern catalog** (section 3) on each hot path — most structural problems are one of these named patterns; name each finding after its pattern.
4. **Choose the structure** from the decision table (section 4) if the problem is a wrong structure.
5. **Rate severity and confidence** with the decision procedure (section 5). Do not rate by feel.
6. **Write findings** in the required format (section 6), each with a minimal patch.
7. **Gate every patch** on the semantic checklist (section 7) before proposing it.

Only load language reference files for languages actually in the reviewed code — one or two files, never all of them:
- `references/ruby-rails.md` — Ruby and Rails/Active Record code
- `references/nextjs-typescript.md` — TypeScript/JavaScript/Next.js
- `references/python.md` — Python
- `references/rust.md` — Rust
- `references/go.md` — Go
- `references/verification.md` — when you will run or request measurements

If code is in a language without a reference file (Java, C#, PHP, C++, …), sections 1–7 of this file still apply fully; the DB/ORM and cache rules in section 8 apply to any language; say "needs measurement" instead of inventing library APIs.

## 1. Scope and inventory

- **Review target:** a diff/PR → inspect changed lines, their enclosing loops, and their call sites. A whole repo → inspect entry points first (below), then persistent structures.
- **Inventory:** for each entry point, list (a) every collection built or searched, (b) every database/API read inside a loop, (c) every process-global or long-lived structure that code writes to.
- **Cardinality:** note any collection whose size grows with users, rows, requests, or input. If you cannot determine sizes, say so in the finding and mark it workload-dependent.
- **What you covered:** state at the end which entry points/paths were inspected; a huge repo review never claims exhaustiveness.

## 2. Where to look first (hot paths)

Scan in this priority order until you have the shape of the system:

1. Entry points: web request handlers/controllers/routes, background jobs/workers, CLI commands, event/message handlers, API endpoints.
2. Every loop (any of `for`, `while`, `.each`, `.map`, list comprehensions, `.iter()`, `for range`) — and in particular **loops inside loops**, loops that call a function that loops, and loops that query a database or API.
3. Code that runs once per request/event (serializers, renderers, middleware, per-request caching).
4. Process-global or module-level structures written on every request: caches, registries, memo tables, pools, unbounded queues.
5. Database layer: frequent queries, model callbacks, relation traversal, index/schema files.
6. Serialization boundaries: API responses, RPC payloads, file formats, anything JSON/base64-shaped.

## 3. Pattern catalog — run on every hot path

Each row: what the code literally looks like → the cost model → when to report it. "Recipe" entries name the section in the matching language file that contains the exact fix. A finding names its pattern, e.g. `[High] per-row DB call (N+1) — confidence High`.

| # | Pattern name | What you see in code | Cost model | When to report |
|---|---|---|---|---|
| P1 | **membership scan** | `include?`, `includes`, `contains`, `in list`, `indexOf`, `.find`, `x in arr` — a linear membership test **inside a loop** over another collection | W = outer × inner; O(n·m) | Inner collection reused across iterations and W ≥ ~10⁴; build one `Set`-like structure first. Recipe: language file "membership" |
| P2 | **lookup by key** | per-iteration `find`/`detect`/`filter`/`search` that retrieves one item from a collection by id/key | O(n·m) | Same key space is queried repeatedly; build a map/index once. Recipe: language file "key lookup" |
| P3 | **index rebuilt in loop** | `group_by`, `Map`/`dict` construction, `index_by`, `to_h`, sorting, or dedupe *inside* the loop body or per render/request | O(n) extra per iteration → O(n·m) | Index input does not change during the loop; hoist it above the loop |
| P4 | **full sort for top-k/min-max** | `.sort`/`.sorted`/`sort_by`/`qsort` when only min, max, or top N used | O(n log n) vs O(n) or O(n log k) | Sort is per-request or per-iteration, or n large and only extremes consumed |
| P5 | **repeated sort** | same collection sorted again on every request/iteration though unchanged | each sort O(n log n) | Data is static across uses (per-process/request); sort once, or keep ordered structure if written too |
| P6 | **front mutation of sequence** | `shift`, `unshift`, `pop(0)`, `insert(0, …)`, `remove(0)`, `.splice(0,…)` in a queue role | O(n) each → O(n²) sustained | Sustained FIFO with large/active queue; small rare shifts: skip. Recipe: language file "queue" |
| P7 | **quadratic accumulation** | `s += part`, `arr = [...arr, x]`, `str + part` inside a loop; repeated `JSON.parse(JSON.stringify(...))` or deep copy as clone | O(n²) copy growth | Loop builds a large aggregate (≥ ~10³ parts) or copies in a hot path |
| P8 | **per-row DB/API call (N+1)** | `find`, `find_by`, `get`, `fetch` for one id **inside** a loop over records; also per-row insert/update | 1 + n queries or requests | n ≥ ~10 rows per request on any real endpoint. Recipe: language file "N+1"/"batch" |
| P9 | **load-then-filter / over-fetch** | whole table/collection loaded then filtered/counted/sorted/grouped in memory; `SELECT *` for two fields; `to_a`/`list()`/materialize then discard | DB work ≫ needed; GC + transfer | Filter/order/aggregate can run server-side/database-side with same semantics |
| P10 | **unbounded retention** | cache/memo/registry/queue/map with no cap, TTL, eviction, or invalidation; request data stored globally; cache keyed by user/request id | memory grows without bound | Any growth path not bounded by a hard limit. Report even without measurements |
| P11 | **copy per iteration** | `.clone()`, `.dup`, `.copy()`, `.to_a`, spread/collect/materialize of the same data in every iteration/request | O(n) extra per iteration | Copy not needed for semantics; borrow/view/stream/reuse instead |
| P12 | **wrong structure** | access pattern does not match the chosen collection (see section 4) | varies | Only when a structure from section 4 clearly fits and the "don't switch" column does not apply |
| P13 | **concurrency/shared-state shape** | plain map mutated from multiple threads/goroutines; one lock guarding independent keys; unbounded worker queue; lock-free structure without need | correctness + contention | Race is a correctness bug: report regardless of measurements. Contention findings need evidence |
| P14 | **layout/locality** | pointer-heavy object graphs, boxed numerics, wide rows/objects for narrow hot ops, struct-of-arrays candidate | cache misses, per-object overhead | Only for large (≳10⁵) numeric/record hot loops; memory-profile evidence preferred |
| P15 | **payload/boundary shape** | full records sent when consumer needs a projection; repeated parse/serialize in request path; unbounded response arrays; client re-indexes huge payloads | transfer + parse + re-layout | Real payload sizes or bounded server data; see section 8 for DB variants |
| P16 | **algorithm-specific gap** | rolling window rescanned; prefix searched linearly; top-k via full sort; repeated connectivity/interval checks; boolean/ID membership in huge lists | see table below | Only when the workload actually matches (P4/P6/P12 references); do not introduce exotic structures on speculation |

Also check the classics while scanning: recursion with duplicate subproblems (memoize only when argument space is bounded), repeated parse/serialize of the same data, expensive equality/hash functions in hot structures, keys that mutate while stored in hash structures, and `O(n)` hidden inside apparently-constant loops (e.g., `.length` recomputed per iteration in languages where it is O(n), `count()` on a relation inside a loop).

### Cheap structure wins (algorithm-specific, P16)

- top-k → bounded heap / quickselect / DB `ORDER BY ... LIMIT` (see section 8)
- rolling window max/min → monotonic deque
- repeated membership over compact integer/boolean domain → bitset/bitmap
- prefix search over many strings → trie or database search index (external candidates need measurement)
- connectivity over a mostly static graph → union-find, only if query/update semantics match
- frequency counting → hash counter; approximate sketch only when exactness is provably unnecessary
- authorization/security membership via Bloom filter → **reject**: false positives break correctness

## 4. Structure decision table

Pick a candidate only when the *dominant access pattern* is in the left column. The right column is a hard guard: if it applies, the switch is probably not worth it.

| Dominant operation | Default structure | Do NOT switch when |
|---|---|---|
| Membership test, repeated | hash set (`Set`/`HashSet`/`set`) | tests are one-shot, or n ≲ 10² per test and total W < 10⁴; ordered iteration of the same data needed |
| Lookup one item by key, repeated | hash map/index | few lookups; n tiny; first-match of duplicates matters (map collapses); you need the item's *position* |
| Ordered iteration / range queries / ordered uniqueness | tree/ordered map, or sort once then binary search | unordered access only; structure rebuilt per request; writes interleave with reads and ordering cost dominates |
| First/last item (extrema) | track min/max incrementally or `min`/`max` scan | both min and max change often and n small; sort is reused elsewhere anyway |
| Top-k of a stream | bounded heap (size k) | one-shot and n small → sort once; heap never needed for k ≥ n/2 |
| FIFO queue | deque/ring/cursor (per-language recipe) | queue length small & ops rare; order not FIFO |
| LIFO stack | native array/vector (append+pop at end) | — (this is already optimal) |
| Dedupe / set operations | hash set | order must survive (use ordered set or list+seen-set); n tiny |
| Frequency counts | hash counter | one-shot small |
| Boolean/large-ID membership, compact domain | bitset/bitmap | domain sparse or huge (then hash set); need to iterate set members often |
| Graph traversal | adjacency list; matrix only for dense small graphs | doubt about density/scale — measure or note assumption |
| Keyed cache with bounded lifetime | cache with TTL + max size + invalidation (framework cache if one exists) | data already memoized at a higher scope (e.g., request memoization); cache duplicates an existing layer |
| Concurrency | start with the language's simplest safe primitive (map + mutex, single-writer + immutable snapshot) | no measured contention; a lock-free/concurrent structure proposed "because concurrent" |
| Sorted small collection read-heavy | keep sorted array (n ≲ 100), binary search | you measured a problem at real n |

A hash structure is not automatically better than a vector/array. Where the crossover matters and you cannot measure, mark the finding **needs measurement**.

## 5. Severity and confidence — decision procedure

Do this arithmetic **per finding**, then pick severity from the table. These numbers calibrate, they are not law — adjust for latency budget, request rate, and batch vs. interactive use.

1. **Estimate W** = total extra work per execution of the pattern (e.g., membership scan: outer iterations × inner size; sort per request: n log n). If sizes are unknown, write down the assumption (e.g., "per-user list, assume up to 10⁵") and note the finding as workload-dependent.
2. **How often does it run?** (a) every hot request/event (web/API path, live loop), (b) per moderate request, job, or batch run, (c) once, cold, or rare (admin task, startup, test).
3. **Is the cost unbounded in data growth?** caches, registries, queues, or maps that grow with users/requests with no cap are always High or worse — no cardinality excuse needed.
4. **Is a DB query plan involved?** without EXPLAIN/query logs you may not assert index benefits (section 8).

| Conditions | Severity |
|---|---|
| Any provable unbounded growth on a live path; or (a) with W ≥ 10⁹; or per-row DB call in a loop over ≥ 10⁵ rows | **Critical** — outage/timeout/memory-collapse risk |
| (a) with W ≥ 10⁶–10⁷; (b) with W ≥ 10⁸; N+1 over hundreds of rows per request; unbounded but rate-limited growth | **High** |
| (a) with W ~10⁴–10⁶; (b) with W ~10⁶; speculative but material at larger scale | **Medium** |
| Cold path (c), or W < 10⁴, or impact only at hypothetical scale with no evidence | **Low** (only if code is already being touched) |
| Correct alternative exists but no workload evidence of a problem | **Info** — one line, no patch required |
| n ≲ 100 one-shot operations, W < 10³ | **No finding** |

**Confidence** (attach to every finding): **Certain** — provable from code or measured; **High** — strong structural evidence plus realistic workload; **Medium** — plausible, workload-dependent; **Low** — hypothesis needing profiling. Rule: if cardinality/workload is unknown and growth is bounded, severity ≤ Medium and confidence ≤ High; the only escape is proof of unbounded growth or unambiguous asymptotics.

## 6. Finding format

For every finding at **Medium** and above, write exactly these fields:

```
[Severity] Title (pattern name) — Confidence

- Location: file:line (or component/query)
- Current structure/pattern: what the code does now
- Access pattern: dominant operations and frequency
- Why inefficient: the mechanism, with W estimate and sizes assumed
- Complexity: current O(…) vs proposed O(…)
- Memory/allocation effect: copies, retention, per-item overhead
- Patch: minimal change with imports
- Semantics preserved: which gates you checked
- Trade-offs: ordering, memory, update cost, correctness, concurrency
- Evidence: static proof / measurement / "needs measurement"
- Verification: the exact test, benchmark, or query-count step
```

**Low/Info** findings: one line each, aggregated. Never report >10 findings total.

## 7. Patch rules — semantic gates (run before proposing any patch)

A patch that preserves performance but changes behavior is a failed patch. Check **all** of these before writing the fix:

1. **Order** — does anything downstream rely on sequence or stable output?
2. **Duplicates** — Set/Map collapse duplicates or keep the last value.
3. **Laziness/effects** — switching eager to lazy changes when errors fire.
4. **Key identity and equality** — language-specific key comparison semantics.
5. **Aliasing/mutation** — slices/substrings share backing memory.
6. **Absent vs zero/false** — language-specific missing-key behavior.
7. **Concurrency** — never "fix" a race by making it cheaper.
8. **API surface** — same signatures, no new dependencies unless already used.

## 8. Cross-language rules for database and cache layers

**Database reads**
- N+1 (P8): one query + in-memory group. For ORMs use eager-loading. Avoid join fan-out with large child collections.
- Pushing work to SQL valid when per-row app logic not needed.
- Deep offset pagination → keyset/cursor with stable unique ordered key.
- Index claims need the real predicate — never assert from column names alone.

**Caches and lifetime**
- Any cache needs a cap, TTL, or invalidation. Unbounded = never acceptable.
- Don't layer caches where one exists at the right scope.
- User-specific data must not go in shared/global cache scope.

## 9. Things NOT to flag

Skip: one-shot membership over small n; plain object/map usage at small scale; default hashers; every clone/copy; every lock→concurrent switch; every DB query→cache; every allocation; code with hard-capped small n and cold. Correctness > theory.

## 10. Second-order regression check

Does the recommendation cause higher memory use, slower iteration, loss of ordering, worse writes, stale caches, sync overhead, larger payloads, more DB writes, or semantics changes? If yes, weigh or drop it.

## 11. Stop conditions

The review is complete when: all hot paths inspected; every claim rated by severity/confidence; high-impact claims verified or marked measurement-dependent; patches pass semantic gates; low-value findings excluded.

## 12. Closing summary

1. **Highest-impact structural risks** (max 5, ranked)
2. **Confirmed vs workload-dependent findings**
3. **Likely complexity improvements**
4. **Memory/retention risks** (P10/P11/P14)
5. **Database/data-access risks** (P8/P9)
6. **Measurements still needed**
