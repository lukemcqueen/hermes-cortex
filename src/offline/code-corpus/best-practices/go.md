---
language: go
tags: [go, best-practices, idiomatic, golang]
title: Go Best Practices
description: Idiomatic Go — zero values, error handling (not exceptions), small interfaces, table-driven tests, gofmt, avoid global state, context.Context as first param
source: pattern
---

# Go Best Practices

## Zero Values
Leverage Go's zero-value guarantee — every `var` declaration is ready to use:

```go
type Config struct {
    Host string // defaults to ""
    Port int    // defaults to 0
    Debug bool  // defaults to false
}

// No constructor needed for simple types
var cfg Config
cfg.Host = "localhost"
```

## Error Handling (Not Exceptions)
Errors are values — handle them explicitly:

```go
func ReadUser(r io.Reader) (User, error) {
    var u User
    dec := json.NewDecoder(r)
    if err := dec.Decode(&u); err != nil {
        return User{}, fmt.Errorf("decoding user: %w", err)
    }
    // Check business logic invariants
    if u.Name == "" {
        return User{}, errors.New("user name is required")
    }
    return u, nil
}
```

## Small Interfaces
Define interfaces with 1–3 methods. Prefer accepting interfaces, returning structs:

```go
// io.Reader and io.Writer are the canonical examples
type Storer interface {
    Store(ctx context.Context, key string, value []byte) error
    Load(ctx context.Context, key string) ([]byte, error)
}
```

## Table-Driven Tests
Use subtests with `t.Run` for exhaustive coverage:

```go
func TestParseDuration(t *testing.T) {
    tests := []struct {
        name  string
        input string
        want  time.Duration
        err   bool
    }{
        {"seconds", "30s", 30 * time.Second, false},
        {"minutes", "5m", 5 * time.Minute, false},
        {"invalid", "abc", 0, true},
        {"zero", "0s", 0, false},
    }

    for _, tc := range tests {
        t.Run(tc.name, func(t *testing.T) {
            got, err := ParseDuration(tc.input)
            if (err != nil) != tc.err {
                t.Fatalf("ParseDuration(%q) error = %v, want err=%v", tc.input, err, tc.err)
            }
            if got != tc.want {
                t.Errorf("ParseDuration(%q) = %v, want %v", tc.input, got, tc.want)
            }
        })
    }
}
```

## `gofmt` / Formatting
Always run `gofmt` (or `go fmt ./...`) before committing. Align on tabs, not spaces.

## Avoid Global State
Inject dependencies explicitly. Avoid `init()` functions and package-level `var`:

```go
// Bad
var db *sql.DB

func init() {
    db = openDB() // hard to test, mutate, or swap
}

// Good
type App struct {
    db *sql.DB
}

func NewApp(db *sql.DB) *App {
    return &App{db: db}
}
```

## `context.Context` as First Parameter
Thread context through every public function that touches I/O:

```go
func FetchWeather(ctx context.Context, city string) (Weather, error) {
    // Context carries deadlines, cancellation, and tracing
    url := fmt.Sprintf("https://api.weather.com/v1/%s", city)
    req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
    if err != nil {
        return Weather{}, fmt.Errorf("creating request: %w", err)
    }
    // ...
}
```

## Additional Patterns
- Use `:=` for declaration + assignment, `var` for zero-value declarations
- Prefer composite literals `&T{}` over `new(T)`
- Use `_` to silence the unused-variable compiler error
- Document exported symbols with doc comments (`// PackageName …`)