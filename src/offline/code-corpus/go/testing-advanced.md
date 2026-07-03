---
language: go
tags: [go, testing, quality, patterns]
title: Advanced Go Testing Patterns
description: Table-driven tests, test helpers, golden files, httptest, fuzzing, race detection
source: pattern
---

# Advanced Go Testing Patterns

Production-grade testing patterns for Go: from table-driven tests through
fuzzing and race detection.

## 1. Table-Driven Tests

The standard pattern for testing multiple input/output combinations.

```go
// math.go
package math

import "errors"

func Add(a, b int) int { return a + b }

func Divide(a, b int) (int, error) {
    if b == 0 {
        return 0, errors.New("division by zero")
    }
    return a / b, nil
}

func Reverse(s string) string {
    r := []rune(s)
    for i, j := 0, len(r)-1; i < j; i, j = i+1, j-1 {
        r[i], r[j] = r[j], r[i]
    }
    return string(r)
}
```

```go
// math_test.go
package math

import "testing"

func TestAdd(t *testing.T) {
    tests := []struct {
        name string
        a, b int
        want int
    }{
        {name: "positive", a: 1, b: 2, want: 3},
        {name: "negative", a: -1, b: -2, want: -3},
        {name: "zero", a: 0, b: 5, want: 5},
        {name: "mixed", a: -3, b: 7, want: 4},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            if got := Add(tt.a, tt.b); got != tt.want {
                t.Errorf("Add(%d, %d) = %d, want %d", tt.a, tt.b, got, tt.want)
            }
        })
    }
}

func TestDivide(t *testing.T) {
    tests := []struct {
        name    string
        a, b    int
        want    int
        wantErr bool
    }{
        {name: "simple", a: 10, b: 2, want: 5, wantErr: false},
        {name: "by zero", a: 5, b: 0, want: 0, wantErr: true},
        {name: "truncation", a: 7, b: 3, want: 2, wantErr: false},
        {name: "negative", a: -6, b: 3, want: -2, wantErr: false},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got, err := Divide(tt.a, tt.b)
            if (err != nil) != tt.wantErr {
                t.Errorf("Divide(%d, %d) error = %v, wantErr %v", tt.a, tt.b, err, tt.wantErr)
                return
            }
            if got != tt.want {
                t.Errorf("Divide(%d, %d) = %d, want %d", tt.a, tt.b, got, tt.want)
            }
        })
    }
}

// Subtle: test Reverse with a symmetric property
func TestReverse(t *testing.T) {
    tests := []struct {
        name string
        input string
        want string
    }{
        {name: "palindrome", input: "racecar", want: "racecar"},
        {name: "normal", input: "hello", want: "olleh"},
        {name: "unicode", input: "Go语言", want: "言语oG"},
        {name: "empty", input: "", want: ""},
        {name: "single", input: "a", want: "a"},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            if got := Reverse(tt.input); got != tt.want {
                t.Errorf("Reverse(%q) = %q, want %q", tt.input, got, tt.want)
            }
        })
    }
}

// Property-based check: reversing twice gives the original
func TestReverseInvolution(t *testing.T) {
    inputs := []string{"hello", "world", "Go语言", "a", "", "racecar"}
    for _, s := range inputs {
        t.Run(s, func(t *testing.T) {
            if got := Reverse(Reverse(s)); got != s {
                t.Errorf("Reverse(Reverse(%q)) = %q, want %q", s, got, s)
            }
        })
    }
}
```

## 2. Test Helpers

Shared setup/teardown utilities using `t.Helper()`.

```go
// testhelper/testdb.go
package testhelper

import (
    "database/sql"
    "os"
    "testing"
)

// OpenTestDB opens a test database and registers a cleanup.
func OpenTestDB(t *testing.T) *sql.DB {
    t.Helper()

    dsn := os.Getenv("TEST_DATABASE_URL")
    if dsn == "" {
        dsn = "postgres://postgres:postgres@localhost:5432/testdb?sslmode=disable"
    }

    db, err := sql.Open("postgres", dsn)
    if err != nil {
        t.Fatalf("failed to open test DB: %v", err)
    }

    t.Cleanup(func() {
        if err := db.Close(); err != nil {
            t.Errorf("failed to close test DB: %v", err)
        }
    })

    return db
}

// TruncateTables clears all rows from the given tables after the test.
func TruncateTables(t *testing.T, db *sql.DB, tables ...string) {
    t.Helper()

    t.Cleanup(func() {
        for _, table := range tables {
            if _, err := db.Exec("TRUNCATE TABLE " + table + " CASCADE"); err != nil {
                t.Errorf("failed to truncate table %s: %v", table, err)
            }
        }
    })
}

// AssertError checks that an error matches expectations.
func AssertError(t *testing.T, got error, want bool) {
    t.Helper()
    if (got != nil) != want {
        t.Errorf("got error = %v, wantErr = %v", got, want)
    }
}
```

```go
// testhelper/http.go
package testhelper

import (
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "testing"
)

// JSONBody returns an http.Handler that responds with the given JSON body.
func JSONBody(t *testing.T, status int, body interface{}) http.Handler {
    t.Helper()
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        w.WriteHeader(status)
        if err := json.NewEncoder(w).Encode(body); err != nil {
            t.Errorf("failed to encode JSON: %v", err)
        }
    })
}

// ParseResponse decodes a JSON response body.
func ParseResponse(t *testing.T, rec *httptest.ResponseRecorder, target interface{}) {
    t.Helper()
    if err := json.NewDecoder(rec.Body).Decode(target); err != nil {
        t.Fatalf("failed to decode response body: %v\nbody: %s", err, rec.Body.String())
    }
}
```

## 3. Golden Files

Snapshot testing with golden files — compare output against stored expected
output.

```go
// golden_test.go
package parser

import (
    "flag"
    "os"
    "path/filepath"
    "testing"
)

// -update flag: when set, rewrites golden files instead of comparing.
var update = flag.Bool("update", false, "update golden files")

// goldenPath returns the path to the golden file for this test.
func goldenPath(t *testing.T, name string) string {
    t.Helper()
    return filepath.Join("testdata", t.Name()+"."+name+".golden")
}

// updateGolden writes the actual output to the golden file.
func updateGolden(t *testing.T, path string, data []byte) {
    t.Helper()
    os.MkdirAll(filepath.Dir(path), 0755)
    if err := os.WriteFile(path, data, 0644); err != nil {
        t.Fatalf("failed to write golden file: %v", err)
    }
}

// goldenEqual compares actual output against a golden file.
func goldenEqual(t *testing.T, path string, actual []byte) {
    t.Helper()
    expected, err := os.ReadFile(path)
    if err != nil {
        t.Fatalf("failed to read golden file %s: %v", path, err)
    }
    if string(actual) != string(expected) {
        t.Errorf("output mismatch\n--- expected (%s)\n+++ actual\n%s\n%s",
            path, expected, actual)
    }
}

// --- Actual test ---

func TestParseConfig(t *testing.T) {
    input := []byte(`
server:
  port: 8080
  host: "0.0.0.0"
logging:
  level: info
`)

    result, err := ParseConfig(input)
    if err != nil {
        t.Fatal(err)
    }

    got, err := FormatAsJSON(result)
    if err != nil {
        t.Fatal(err)
    }

    golden := goldenPath(t, "json")
    if *update {
        updateGolden(t, golden, got)
    }

    goldenEqual(t, golden, got)
}
```

Run with golden file updates:

```shell
go test -run TestParseConfig -update   # writes/updates golden files
go test ./...                           # normal comparison run
```

## 4. Testing HTTP Handlers with `httptest`

```go
// handlers/users.go
package handlers

import (
    "encoding/json"
    "net/http"
)

type User struct {
    ID   int    `json:"id"`
    Name string `json:"name"`
}

type UserService interface {
    GetUser(id int) (*User, error)
    CreateUser(name string) (*User, error)
}

type UserHandler struct {
    svc UserService
}

func NewUserHandler(svc UserService) *UserHandler {
    return &UserHandler{svc: svc}
}

func (h *UserHandler) GetUser(w http.ResponseWriter, r *http.Request) {
    // Uses Go 1.22+ routing: GET /users/{id}
    id := r.PathValue("id")
    // ... parse id, call svc, return JSON
}
```

```go
// handlers/users_test.go
package handlers

import (
    "encoding/json"
    "errors"
    "net/http"
    "net/http/httptest"
    "testing"
)

// mockUserService implements UserService for testing.
type mockUserService struct {
    getUserFn func(id int) (*User, error)
}

func (m *mockUserService) GetUser(id int) (*User, error) {
    return m.getUserFn(id)
}

func (m *mockUserService) CreateUser(name string) (*User, error) {
    return nil, errors.New("not implemented")
}

func TestGetUser_Success(t *testing.T) {
    svc := &mockUserService{
        getUserFn: func(id int) (*User, error) {
            return &User{ID: id, Name: "Alice"}, nil
        },
    }
    handler := NewUserHandler(svc)

    req := httptest.NewRequest("GET", "/users/42", nil)
    // Set path value for Go 1.22+ routing
    req.SetPathValue("id", "42")
    rec := httptest.NewRecorder()

    handler.GetUser(rec, req)

    if rec.Code != http.StatusOK {
        t.Fatalf("expected 200, got %d", rec.Code)
    }

    var user User
    if err := json.NewDecoder(rec.Body).Decode(&user); err != nil {
        t.Fatalf("failed to decode response: %v", err)
    }
    if user.Name != "Alice" || user.ID != 42 {
        t.Errorf("unexpected user: %+v", user)
    }
}

func TestGetUser_NotFound(t *testing.T) {
    svc := &mockUserService{
        getUserFn: func(id int) (*User, error) {
            return nil, errors.New("user not found")
        },
    }
    handler := NewUserHandler(svc)

    req := httptest.NewRequest("GET", "/users/999", nil)
    req.SetPathValue("id", "999")
    rec := httptest.NewRecorder()

    handler.GetUser(rec, req)

    if rec.Code != http.StatusNotFound {
        t.Errorf("expected 404, got %d", rec.Code)
    }
}

// Test with a full httptest.Server for integration
func TestServerIntegration(t *testing.T) {
    svc := &mockUserService{
        getUserFn: func(id int) (*User, error) {
            return &User{ID: id, Name: "Bob"}, nil
        },
    }

    mux := http.NewServeMux()
    handler := NewUserHandler(svc)
    mux.HandleFunc("GET /api/users/{id}", handler.GetUser)

    srv := httptest.NewServer(mux)
    defer srv.Close()

    resp, err := http.Get(srv.URL + "/api/users/1")
    if err != nil {
        t.Fatalf("request failed: %v", err)
    }
    defer resp.Body.Close()

    if resp.StatusCode != http.StatusOK {
        t.Fatalf("expected 200, got %d", resp.StatusCode)
    }
}
```

## 5. Fuzzing

Go 1.18+ built-in fuzzing — generates random inputs to find edge cases.

```go
// reverse_test.go

func FuzzReverse(f *testing.F) {
    // Seed corpus with known inputs
    f.Add("hello")
    f.Add("Go语言")
    f.Add("racecar")
    f.Add("a")
    f.Add("")

    f.Fuzz(func(t *testing.T, orig string) {
        rev := Reverse(orig)
        doubleRev := Reverse(rev)

        // Involution property: reversing twice gives the original
        if doubleRev != orig {
            t.Errorf("Reverse(Reverse(%q)) = %q, want %q", orig, doubleRev, orig)
        }

        // UTF-8 validity: reversing a valid UTF-8 string must produce valid UTF-8
        if len(rev) != len([]rune(orig)) {
            t.Errorf("Reverse(%q) changed rune count: got %d runes, want %d",
                orig, len([]rune(rev)), len([]rune(orig)))
        }
    })
}
```

```go
// deserialize_test.go

func FuzzDeserializeConfig(f *testing.F) {
    f.Add([]byte(`{"port": 8080, "host": "0.0.0.0"}`))
    f.Add([]byte(`{}`))

    f.Fuzz(func(t *testing.T, data []byte) {
        // Must never panic, never return a nil pointer without error
        config, err := DeserializeConfig(data)
        if err != nil && config != nil {
            t.Errorf("both error and non-nil config returned: err=%v, config=%+v", err, config)
        }
        if config != nil && config.Port < 0 || config.Port > 65535 {
            t.Errorf("invalid port: %d", config.Port)
        }
    })
}
```

Run fuzzing:

```shell
go test -fuzz FuzzReverse -fuzztime 30s ./...
go test -fuzz FuzzDeserializeConfig -fuzztime 1m ./...

# Run a specific fuzz corpus entry
go test -run FuzzReverse/6f0b4e7a3c8d1a2b

# Clean cached fuzz corpora
go clean -fuzzcache
```

### Fuzzing Tips

- **Seed corpus**: provide realistic inputs via `f.Add()` so the fuzzer has a
  starting point.
- **Properties**, not expected outputs: fuzzing checks invariants (no panic,
  valid output, idempotency).
- **Don't compare against known output** — fuzzing is for finding crashes,
  panics, and violated invariants.
- **Run in CI with a time budget** (e.g., `-fuzztime 1m`).

## 6. Race Detection

```go
// race_test.go

// Counter is intentionally unsafe to demonstrate race detection.
type Counter struct {
    value int
}

func (c *Counter) Increment() {
    c.value++   // data race: concurrent writes
}

func (c *Counter) Value() int {
    return c.value  // data race: concurrent read with write
}

func TestCounterRace(t *testing.T) {
    c := &Counter{}
    done := make(chan struct{})

    // Writer goroutine
    go func() {
        for i := 0; i < 1000; i++ {
            c.Increment()
        }
        close(done)
    }()

    // Reader goroutine in the same test
    for i := 0; i < 1000; i++ {
        _ = c.Value()
    }

    <-done
}

// SafeCounter has no races.
type SafeCounter struct {
    mu    sync.Mutex
    value int
}

func (c *SafeCounter) Increment() {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.value++
}

func (c *SafeCounter) Value() int {
    c.mu.Lock()
    defer c.mu.Unlock()
    return c.value
}
```

Run with race detection:

```shell
# Run all tests with the race detector
go test -race ./...

# With verbose output
go test -race -v ./...

# With short timeout (race detector is 2-20x slower)
go test -race -short ./...

# Build a binary with race detection for production-like testing
go build -race -o myapp .

# WARNING: the race binary is unsuitable for production — memory and
# CPU overhead (5-10x) is significant.
```

### Integrating Race Detection in CI

```yaml
# .github/workflows/test.yml (excerpt)
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
      - run: go test -race -count=1 -timeout=120s ./...
```

## 7. Parallel Testing

```go
// parallel_test.go
package math

import "testing"

func TestAddParallel(t *testing.T) {
    tests := []struct {
        name string
        a, b int
        want int
    }{
        {"a=1,b=2", 1, 2, 3},
        {"a=-1,b=1", -1, 1, 0},
        {"a=0,b=0", 0, 0, 0},
        {"a=100,b=200", 100, 200, 300},
    }
    for _, tt := range tests {
        tt := tt // capture range variable
        t.Run(tt.name, func(t *testing.T) {
            t.Parallel()
            if got := Add(tt.a, tt.b); got != tt.want {
                t.Errorf("Add(%d, %d) = %d, want %d", tt.a, tt.b, got, tt.want)
            }
        })
    }
}
```

## 8. Test Coverage and Benchmarks

```shell
# Coverage
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out       # browser
go tool cover -func=coverage.out       # terminal

# Benchmarks
go test -bench=. -benchmem ./...

# Benchmark with CPU profiling
go test -bench=. -cpuprofile=cpu.out -memprofile=mem.out ./...
go tool pprof -http=:8080 cpu.out

# Compare benchmarks between branches
go test -bench=. -count=10 -benchmem ./... > /tmp/old.txt
# ... switch branch ...
go test -bench=. -count=10 -benchmem ./... > /tmp/new.txt
go install golang.org/x/perf/cmd/benchstat@latest
benchstat /tmp/old.txt /tmp/new.txt
```

## Complete Makefile Targets

```makefile
# Makefile
.PHONY: test test-race test-cover test-fuzz bench

test:
    go test -count=1 ./...

test-race:
    go test -race -count=1 -timeout=120s ./...

test-cover:
    go test -count=1 -coverprofile=coverage.out ./...
    go tool cover -func=coverage.out
    go tool cover -html=coverage.out

test-fuzz:
    go test -fuzz FuzzReverse -fuzztime=30s ./...

test-all: test test-race test-fuzz bench

bench:
    go test -bench=. -benchmem ./...
```