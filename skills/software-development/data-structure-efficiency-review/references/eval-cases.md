# Evaluation cases for skill maintenance

Regression tests for this skill. Grade on four axes: Found (pattern named correctly), Severity (within one band), Patch (minimal, idiomatic, semantic gates pass), Guard (false-positive/semantic-regression blockers work).

## Ruby core
- C1: 100k items; inner loop `allowed_ids.include?(id)` on Array → P1, High; Set built once outside loop
- C2: 5-element Array `include?` once in request → None/Info
- C6: Hot queue drained with `shift` over 10⁵ items → P6, Medium/High
- C7: `html += part` over 10k rows → P7
- C9: `Set.new` without `require "set"` → version-aware patch required
- C10: `users.find { |u| u.id == id }` in loop, duplicates possible → P2 with last-wins caveat
- C11: Repeated `sort_by(&:created_at)` unchanged data → P5

## Rails/AR
- C3: Loop over posts accesses `post.author.name` without eager loading → P8 N+1
- C4: Eager-load 3 huge `has_many` → memory/row explosion warning
- C5: `Model.all.select { |x| x.active? }` → P9 load-then-filter
- C8: Deep offset over millions → P9 keyset candidate
- C12: Loop calls `User.find(order.user_id)` → P8 per-row query
- C13: Per-row `order.save!` in loop → batch write with callbacks trade-off
- C14: Full relation `.each` over 10⁶ rows → `find_each`/`in_batches`
- C15: N+1 "fixed" with `includes` but assoc used in `where` → correct fix is `joins`
- C16: Per-user cache no expiry → P10
- C17: Index from model declaration alone → "needs measurement"

## Python
- C18: `pop(0)` over 10⁶ → P6 deque
- C19: `if x in ids_list` in nested loop → P1 set
- C20: Generator wrapped in `list()` consumed once → P9/P11
- C21: `@cache` keyed by user-generated strings → P10 bounded lru_cache
- C22: Repeated `sorted()` unchanged data → P5
- C23: One-shot sorted 2k items → None/Low
- C24: `groupby` unsorted → defaultdict fix
- C25: Membership compact int 0..10⁶ in list → P1/P16 set
- C26: `defaultdict` only for reads → use `.get`

## Rust
- C27: Repeated `Vec::remove(0)` → P6 VecDeque
- C28: Clone 5MB Vec per request → P11 borrow
- C29: HashSet over-reserved → measure iteration cost
- C30: Sorted Vec 8 elements binary search → None (keep Vec)
- C31: `HashMap<String>` from `&str` → borrowed keys
- C32: `Arc<Mutex>` per item in hot loop → restructuring first
- C33: Fast hasher for attacker keys → reject

## Go
- C34: Nested loop scan 10⁴ × 10⁴ → P1/P2 map
- C35: Subslice of 100MB retained globally → P10 copy
- C36: Plain map from goroutines → P13 race
- C37: sync.Map under one owner → question it
- C38: Slice-front queue unclear → guide correctly
- C39: Map-of-maps hot lookups → flatten/composite key
- C40: `&u` in range → loop-variable pitfall

## TypeScript/Next.js
- C41: `users.map(u => roles.find(r => r.id === u.roleId))` → P2 Map
- C42: Global Map keyed by request URLs → P10 bound/TTL
- C43: Identical fetch in server components → understand request memoization
- C44: Large records to Client Component using 2 fields → P15 project server-side
- C45: Object-keyed metadata cache → WeakMap with limits
- C46: Reducer `[...acc, item]` over big array → P7
- C47: `useMemo` with unstable deps → fix upstream identity
- C48: Lookup object `{"10": a}` converted to Map → order difference
- C49: `JSON.parse(JSON.stringify(x))` deep clone → P11

## Cross-language
- C50: Full sort 10⁷ records for top 10 → P4 heap/select
- C51: Adjacency matrix sparse → adjacency list candidate
- C52: Dense int IDs 0..1M in hash map → indexed vector comparison
- C53: Per-user cache global → P10 High
- C54: Cache fixes N+1 but stale across scopes → identify root issue
- C55: JSON round-trip as clone → P11
- C56: Ordered to unordered hash → preserve order or state trade-off
- C57: Bloom filter for auth → reject
- C58: One global lock for 100 independent shards → partitioning after contention evidence
- C59: Map with attacker keys fast hasher → reject
- C60: O(n²) but n capped at 12 and cold → Low/None
- C61: Composite index without query plan → needs measurement
- C62: 10⁷ bools for membership → bitmap vs set
- C63: Prefix scan millions of strings → trie/search index with measurement
- C64: Rolling window max rescanning → monotonic deque
- C65: Connectivity queries static graph → union-find candidate
- C66: Queue faster than consumers → bounded queue/backpressure
- C67: Language with no reference file → generic P1 applies, no invented APIs
- C68: New dependency to fix structure issue → existing primitives first