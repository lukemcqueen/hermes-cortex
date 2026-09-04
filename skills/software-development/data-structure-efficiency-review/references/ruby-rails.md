# Ruby / Rails structural review

Load only when reviewing Ruby or Rails/Active Record code. Pattern numbers (P1–P16) refer to SKILL.md section 3.

## If you take nothing else

- `Array#include?`/`find`/`index` inside a loop over other data = P1/P2 → build a `Hash`/`Set` once, outside the loop.
- `Set` is built in for Ruby ≥ 3.2 (autoloaded). For Ruby < 3.2 add `require "set"` at the top of the file.
- N+1 (P8): eager-load with `includes`/`preload`/`eager_load`, then verify the SQL query count dropped. Eager-loading *three huge* `has_many` graphs to fix an N+1 usually trades queries for a memory/row explosion — prefer fewer/batched loads.
- Per-row `find`/`exists?` in a loop → single `where(id: ids)` + `index_by(&:id)`.
- Whole-table work in Ruby that SQL can do — push it down when per-row Ruby semantics are not needed.
- Do not propose database indexes from model declarations alone: needs the real predicate/order and query plan.

## Ruby core recipes

### P1/P2 — membership and key lookup

```ruby
# Before (P1): linear scan per iteration, W = posts × allowed
allowed = User.active.pluck(:id)                 # Array
posts.each { |p| p.visible = allowed.include?(p.user_id) }

# After: one Set, membership only
require "set" if RUBY_VERSION < "3.2"
allowed = User.active.pluck(:id).to_set
posts.each { |p| p.visible = allowed.include?(p.user_id) }
```

```ruby
# Before (P2): find per iteration returns one record
posts.each { |p| user = users.find { |u| u.id == p.user_id } ... }

# After: map built once
users_by_id = users.index_by(&:id)
posts.each { |p| user = users_by_id[p.user_id] ... }
```

### P3 — index/group rebuilt inside a loop or request

Hoist `group_by`/`index_by`/`to_h`/sort out of the loop:
```ruby
grouped = rows.group_by(&:kind)
rows.each { |row| use grouped[row.kind] }
```

### P4 — sort when only extremes/top-k are needed

`max_by`, `min_by`, `minmax_by` are O(n) scans:
```ruby
users.sort_by(&:created_at).last(5)   # ->  users.max_by(5, &:created_at)
```

### P5 — repeated sort of unchanged data

Sort once and memoize in the right scope. Sorting a *rebuilt* collection every request is not P5; it is fine.

### P6 — queue via `Array#shift`/`unshift` in a hot loop

Consume-once pattern: walk with an index (O(1), retains until done).
True interleaved enqueue/dequeue: two-array trick for amortized O(1):
```ruby
in_a, out_a = [], []
# enqueue -> in_a << x
# dequeue -> out_a.empty? ? (out_a = in_a.reverse; in_a = []; out_a.pop) : out_a.pop
```
Caution: stdlib `Queue` is a *thread* queue with a mutex — don't suggest for single-threaded hot path.

### P7 — quadratic string/array accumulation

```ruby
# Before: html += "<li>#{x}</li>" inside a loop over 10k rows
# After:
html = rows.map { |x| "<li>#{x}</li>" }.join
```

## ActiveRecord / Rails recipes

### P8 — N+1 and per-row queries

```ruby
# Before: one query for posts + one per post for author
posts.each { |post| author_names << post.author.name }

# After: 2 queries total
posts = Post.where(active: true).includes(:author).to_a
author_names = posts.map { |post| post.author.name }
```

`preload` always issues a second query; `eager_load` joins; `includes` picks one. If association data is used in `where`/`order`, plain `includes` is insufficient — use `joins`/`eager_load`. For per-row writes: `insert_all`/`upsert_all`/`update_all` — but they skip callbacks/validations (state the trade-off).

### P9 — over-fetch / in-Ruby filtering

- `Model.all.select { |r| r.active? }` → `Model.where(active: true)` (Rails `select` takes columns, not a block).
- `sort_by`/`group_by`/`count` over relations → SQL equivalents.
- Full model loading where a narrow result suffices → `pluck`, `pick`, `ids`, `exists?`, `select(:col_a, :col_b)`.
- Large dataset walking → `find_each`/`in_batches(batch_size: 1000)`.

### Pagination — keyset vs offset

Deep offset pagination (P9 variant):
```ruby
posts = Post.where(active: true)
            .where("(created_at < ?) OR (created_at = ? AND id < ?)",
                   cursor_created_at, cursor_created_at, cursor_id)
            .order(created_at: :desc, id: :desc)
            .limit(25)
```
Trade-off: no arbitrary page jumps. Needs composite index `[created_at, id]`.

### Index design

Leftmost prefix rule: index `[account_id, created_at]` serves `WHERE account_id = ? ORDER BY created_at`, not `WHERE created_at = ?`. Equality before range/order. Verification is `EXPLAIN` (dev/staging only).

### Caching

`Rails.cache.fetch` keyed by user/request ids without `expires_in:` = P10. Cache only shareable, invalidatable data. Prefer request-scope for per-request data (`RequestStore`).

## Ruby gotchas

- Ruby Hash preserves insertion order; Set does not guarantee iteration order semantics.
- `Array#sort` stability not guaranteed by language.
- Keys of Hash/Set must not mutate fields used by `hash`/`eql?` while stored.
- Dynamic symbol creation from user input (`"#{input}".to_sym`) is retention smell.
- `Set#to_a` loses duplicates and order.
- Do not convert *sorted-iterated* arrays to Set.
- `Relation#count` is SQL; `array.count` is Ruby. Relation inside a loop re-queries each time — memoize with `.load`/`to_a`.

## Verification commands

```ruby
count = 0
ActiveSupport::Notifications.subscribed(
  ->(*) { count += 1 }, "sql.active_record"
) { PostsController.new.send(:index) }
puts count
```
Run endpoint/job against identical data before/after; assert identical output; compare wall time and query count.