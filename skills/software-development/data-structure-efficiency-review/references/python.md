# Python structural review

Load only when reviewing Python code. Pattern numbers (P1–P16) refer to SKILL.md section 3.

## If you take nothing else

- `x in list` or `list.index(...)` inside a loop = P1/P2 → build a `set`/`dict` once, outside the loop.
- `list.pop(0)` / `insert(0, ...)` sustained = P6 → `collections.deque`.
- `sorted(...)` per request when only min/max/top-k used = P4 → `min`/`max` or `heapq.nlargest`/`nsmallest`.
- A `list(...)`/`tuple(...)` wrapper that only feeds one pass = P9/P11 → keep the generator.
- `str + part` or `arr = arr + [x]` accumulation inside a loop = P7 → list append + `"".join`.
- `functools.cache` / unbounded `lru_cache`-style dicts on a server = P10.
- Do not flag tiny one-shot scans or cold code.

## Recipes

### P1/P2 — membership and key lookup

```python
# Before: linear scan per iteration
allowed = [u.id for u in active_users]
for order in orders:
    if order.user_id in allowed: ...  # O(n) per test

# After: one set, built once
allowed = {u.id for u in active_users}
for order in orders:
    if order.user_id in allowed: ...
```

```python
# Before: retrieve one user per order
for order in orders:
    user = next((u for u in users if u.id == order.user_id), None)

# After: dict built once
users_by_id = {u.id: u for u in users}
for order in orders:
    user = users_by_id.get(order.user_id)
```

### P6 — FIFO via `pop(0)`

```python
from collections import deque
q = deque(items)
while q:
    item = q.popleft()  # O(1)
```

### P7 — accumulation

```python
# Before: s += line for 100k lines
# After:
s = "".join(parts)
```

### P10 — unbounded memoization

- `functools.cache` has no size limit. Use bounded `functools.lru_cache(maxsize=...)`.
- Do not "fix" by adding a plain module-level dict.

### Python gotchas

- `dict`/`set` membership is O(1) average only for hashable, well-distributed keys.
- Do not put mutable objects in a `set`/as dict keys.
- `sorted()` is stable; `set`/`dict` ordering must not be relied on.
- Generator consumed by `set(...)`/`list(...)` is one-shot.
- `defaultdict` creates entries on reads.

## Verification commands

```bash
python -m timeit -s "setup once" "statement to time"
python -m cProfile -s cumulative path/to/script.py
```

```python
import tracemalloc
tracemalloc.start()
run_the_path()
cur, peak = tracemalloc.get_traced_memory()
```