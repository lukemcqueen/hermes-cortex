---
name: go-lang
description: Use this skill to write, review, refactor, and test idiomatic Go code. Optimized for small models: simple workflow, strict defaults, minimal guessing.
---

# Go Skill

## Mission

Produce Go code that is:

- idiomatic
- simple
- testable
- context-aware
- easy to maintain
- safe around errors, resources, and concurrency

Prefer boring, clear Go over clever Go.

---

## Default Workflow

For every Go task:

1. Understand the goal.
2. Inspect existing code before editing.
3. Make the smallest correct change.
4. Run formatting and tests when possible.
5. Report what changed and how it was verified.

Do not simulate tool results. If a command was not run, say so.

---

## Output Format

When generating new code, return:

1. `Code`
2. `Tests`
3. `Notes`
4. `Verify`

Keep explanations short.

---

## Core Go Rules

### Simplicity

Prefer:

```go
if err != nil {
	return fmt.Errorf("load config: %w", err)
}
```

Avoid unnecessary abstraction, generic helpers, global state, magic behavior, or large frameworks.

---

### Errors

Always return errors with context.

```go
return fmt.Errorf("open file %q: %w", path, err)
```

Use:

* `errors.Is`
* `errors.As`
* sentinel errors only when callers must branch on them

Do not:

* panic for normal errors
* swallow errors
* return vague errors like `failed`

---

### Context

Accept `context.Context` for request, network, database, filesystem, queue, and long-running work.

```go
func (s *Service) Do(ctx context.Context, id string) error
```

Rules:

* first parameter is `ctx context.Context`
* never store context in structs
* pass context downward
* respect cancellation when looping

---

### Interfaces

Define interfaces where they are consumed, not where they are implemented.

Prefer small interfaces:

```go
type UserStore interface {
	Get(ctx context.Context, id string) (User, error)
}
```

Avoid huge interfaces and premature abstraction.

---

### Packages

Package names should be short, lowercase, and meaningful.

Good:

```txt
user
auth
store
config
```

Avoid:

```txt
utils
helpers
common
manager
```

Split packages by responsibility, not by technical layer only.

---

### Structs

Keep structs explicit.

```go
type Service struct {
	store UserStore
	log   Logger
}
```

Prefer constructor functions when dependencies are required.

```go
func NewService(store UserStore, log Logger) *Service {
	return &Service{store: store, log: log}
}
```

---

### HTTP

Keep handlers thin.

Handlers should:

1. parse input
2. call service
3. write response

Business logic belongs in services.

```go
func (h *Handler) GetUser(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	// parse -> service -> respond
}
```

Always set status codes intentionally.

---

### Resources

Always close or unlock resources.

```go
f, err := os.Open(path)
if err != nil {
	return err
}
defer f.Close()
```

For mutexes:

```go
mu.Lock()
defer mu.Unlock()
```

---

### Concurrency

Use goroutines only when needed.

Rules:

* avoid shared mutable state
* protect shared state with mutexes or channels
* always avoid goroutine leaks
* use context cancellation
* prefer `errgroup` for coordinated goroutines when available

---

### Data

Prefer slices over arrays.

Use map comma-ok checks:

```go
v, ok := m[key]
if !ok {
	return zero, fmt.Errorf("missing key %q", key)
}
```

Preallocate when size is known:

```go
items := make([]Item, 0, len(rows))
```

---

## Testing Rules

Every meaningful change should include tests.

Cover:

* success case
* error case
* edge case

Prefer table tests:

```go
func TestThing(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want string
	}{
		{name: "valid", in: "a", want: "A"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := Thing(tt.in)
			if got != tt.want {
				t.Fatalf("got %q, want %q", got, tt.want)
			}
		})
	}
}
```

Use temporary directories:

```go
dir := t.TempDir()
```

Use deadlines carefully; avoid flaky sleeps.

---

## Verification Commands

Run what applies:

```bash
gofmt -w .
go test ./...
go vet ./...
go mod tidy
```

For targeted testing:

```bash
go test ./path/to/pkg -run TestName -v
```

For race-sensitive code:

```bash
go test -race ./...
```

---

## Review Checklist

Before final answer, check:

* code is gofmt-ready
* errors are wrapped with context
* context is passed where needed
* handlers are thin
* interfaces are small
* tests cover success and failure
* no unnecessary globals
* no fake command results
* no over-engineering

---

## Small Model Guardrails

When unsure:

1. choose the simplest working design
2. avoid adding new dependencies
3. do not invent repository structure
4. do not rewrite unrelated code
5. ask only if blocked
6. otherwise make a safe minimal change

Prefer correct small code over ambitious architecture.