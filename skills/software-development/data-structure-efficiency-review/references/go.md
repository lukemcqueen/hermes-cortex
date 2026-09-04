# Go structural review

Load only when reviewing Go code. Pattern numbers (P1–P16) refer to SKILL.md section 3.

## If you take nothing else

- Slice scans inside a loop = P1/P2 → build a `map[K]struct{}` (membership) or `map[K]V` (lookup) once.
- Go map iteration order is **randomized by design** — never rely on it.
- `q = append(q[1:], ...)` / repetitive slice-front patterns: understand retention first.
- A subslice keeps its whole backing array alive; substring keeps the whole string reachable.
- Ordinary maps are not safe for concurrent read/write — race = correctness bug.
- Preallocate with `make([]T, 0, n)` when size is known.

## Recipes

### P1/P2 — membership and key lookup

```go
// Before: linear scan per order
for _, o := range orders {
    for _, u := range users {
        if u.ID == o.UserID { ... }
    }
}

// After: index built once
allowed := make(map[uint64]struct{}, len(users))
for _, u := range users {
    allowed[u.ID] = struct{}{}
}
for _, o := range orders {
    if _, ok := allowed[o.UserID]; ok { ... }
}
```

### P6 — front-of-slice queues

Concurrent: buffered channel. Single-goroutine: head-index cursor pattern:
```go
type Queue struct {
    buf  []int
    head int
}
func (q *Queue) Push(v int) { q.buf = append(q.buf, v) }
func (q *Queue) Pop() (int, bool) {
    if q.head >= len(q.buf) { return 0, false }
    v := q.buf[q.head]
    q.head++
    if q.head > 1024 && q.head*2 > len(q.buf) {
        n := copy(q.buf, q.buf[q.head:])
        q.buf = q.buf[:n]
        q.head = 0
    }
    return v, true
}
```

### P10 — backing array retention

```go
// Long-lived subslice retains entire 100MB buffer
var keep = bigBuf[0:100]
// Fix: copy the small retained part
keep := append([]byte(nil), bigBuf[:100]...)
```

### P13 — concurrency

Reach for `sync.Map` only for disjoint key sets OR write-once/read-many with long-lived keys. Otherwise `map + RWMutex` or sharded mutexes.

## Go gotchas

- Taking `&u` inside `for _, u := range` (pre-1.22) captures one shared variable.
- `sort.Slice` is not stable; `sort.SliceStable` is.
- Map value `bool` vs `struct{}`: `struct{}` is zero-size, behavior identical.
- Slices are views: "copying" a slice does not copy elements.

## Verification commands

```bash
go test -race ./...
go test -bench=. -benchmem ./pkg
go tool pprof -top cpu.out
```