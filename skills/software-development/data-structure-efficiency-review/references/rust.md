# Rust structural review

Load only when reviewing Rust code. Pattern numbers (P1–P16) refer to SKILL.md section 3.

## If you take nothing else

- Repeated linear `Vec` search (`iter().find/position/any`, `.contains`) inside a loop = P1/P2 → build a `HashSet`/`HashMap` once.
- `Vec::remove(0)` / `insert(0, …)` sustained = P6 → `VecDeque`.
- `.clone()` of large collections per iteration/request = P11 → borrow, `&str`/slices, `Cow`.
- Full sort when only min/max/top-k used = P4 → `min`/`max` via `iter()`, `select_nth_unstable`, `BinaryHeap`.
- Repeated `collect::<Vec<_>>()` between iterator stages = P3/P11.
- Standard `HashMap` hasher is DoS-resistant — do not replace for attacker-controlled keys.

## Recipes

### P1/P2 — membership and key lookup

```rust
use std::collections::{HashMap, HashSet};

// Before
let allowed: Vec<u64> = ...;
for order in &orders {
    if allowed.contains(&order.user_id) { ... }
}

// After
let allowed: HashSet<u64> = allowed.into_iter().collect();
for order in &orders {
    if allowed.contains(&order.user_id) { ... }
}
```

### P6 — queue via `Vec::remove(0)`

```rust
use std::collections::VecDeque;
let mut queue: VecDeque<Job> = VecDeque::from(initial);
queue.push_back(new_job);
let job = queue.pop_front();  // O(1)
```

### P4/P16 — extrema and top-k

```rust
// One-shot min/max: O(n) scan
let best = items.iter().max_by_key(|i| i.score);

// Top-k partial selection (one-shot, no full sort)
let mut items: Vec<Item> = ...;
if k > 0 && k < items.len() {
    let n = items.len();
    items.select_nth_unstable_by(n - k, |a, b| a.score.cmp(&b.score));
    let largest = &items[n - k..];
}
```

### P11 — clones, capacity, layout

```rust
// Known size -> one allocation
let mut v = Vec::with_capacity(n);
let mut s = String::with_capacity(est_len);
```

### P13 — concurrency

Plain shared `HashMap` mutated from several threads = data race (correctness finding). Use `Mutex<HashMap>`/`RwLock`, sharding, or message-passing.

## Rust gotchas

- Debug builds distort perf wildly — benchmark in `--release`.
- `clone` is sometimes semantically required.
- `HashSet`/`HashMap` iteration is unordered; current std iteration cost can scale with capacity.
- Mutable key problem: changing a field that participates in `Hash`/`Ord` while stored breaks structures.
- `Vec::swap_remove` is O(1) but changes order.
- Never propose exotic hash crates as first step.

## Verification commands

```bash
cargo test --release
cargo build --release
```