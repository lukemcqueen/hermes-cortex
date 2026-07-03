---
language: go
tags: [go, http, middleware, patterns]
title: HTTP Middleware Patterns
description: Logging, auth, rate limiting, recovery, chaining with http.Handler and alice
source: pattern
---

# HTTP Middleware Patterns in Go

Reusable, composable HTTP middleware for Go services. Covers common middleware
implementations and chaining patterns.

## The Middleware Signature

The standard middleware signature wraps an `http.Handler`:

```go
// Middleware is a function that takes a Handler and returns a Handler.
type Middleware func(http.Handler) http.Handler
```

## Chaining Utilities

### Manual Chaining

```go
// Chain applies middlewares inside-out (first wraps last)
func Chain(handler http.Handler, middlewares ...Middleware) http.Handler {
    for i := len(middlewares) - 1; i >= 0; i-- {
        handler = middlewares[i](handler)
    }
    return handler
}

// Usage
handler := Chain(
    myHandler,
    RecoveryMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
)
```

### Using `alice` (Community Standard)

```shell
go get github.com/justinas/alice
```

```go
import "github.com/justinas/alice"

func main() {
    mux := http.NewServeMux()
    mux.HandleFunc("/api/users", usersHandler)

    // alice chains left-to-right (natural reading order)
    chain := alice.New(
        RecoveryMiddleware,
        RequestIDMiddleware,
        LoggingMiddleware,
        CORSMiddleware,
    ).Then(mux)

    http.ListenAndServe(":8080", chain)
}
```

## 1. Structured Logging Middleware

```go
// middleware/logging.go
package middleware

import (
    "log"
    "log/slog"
    "net/http"
    "time"
)

// responseWriter wraps http.ResponseWriter to capture the status code.
type responseWriter struct {
    http.ResponseWriter
    statusCode int
    wroteHeader bool
}

func (rw *responseWriter) WriteHeader(code int) {
    if rw.wroteHeader {
        return
    }
    rw.statusCode = code
    rw.wroteHeader = true
    rw.ResponseWriter.WriteHeader(code)
}

func (rw *responseWriter) Write(b []byte) (int, error) {
    if !rw.wroteHeader {
        rw.WriteHeader(http.StatusOK)
    }
    return rw.ResponseWriter.Write(b)
}

// LoggingMiddleware logs each request with duration and status code.
func LoggingMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        start := time.Now()
        rw := &responseWriter{ResponseWriter: w, statusCode: http.StatusOK}

        next.ServeHTTP(rw, r)

        duration := time.Since(start)
        slog.Info("request",
            "method", r.Method,
            "path", r.URL.Path,
            "status", rw.statusCode,
            "duration", duration,
            "remote", r.RemoteAddr,
            "user_agent", r.UserAgent(),
        )
    })
}

// With structured logger package (log/slog):
func StructuredLoggingMiddleware(logger *slog.Logger) Middleware {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            start := time.Now()
            rw := &responseWriter{ResponseWriter: w, statusCode: http.StatusOK}

            next.ServeHTTP(rw, r)

            logger.Info("request",
                "method", r.Method,
                "path", r.URL.Path,
                "query", r.URL.RawQuery,
                "status", rw.statusCode,
                "duration_ms", time.Since(start).Milliseconds(),
            )
        })
    }
}
```

## 2. Request ID Injection

```go
// middleware/requestid.go
package middleware

import (
    "crypto/rand"
    "encoding/hex"
    "net/http"
)

type contextKey string

const RequestIDKey contextKey = "request_id"

// GenerateID creates a 16-byte hex request ID.
func GenerateID() string {
    b := make([]byte, 16)
    rand.Read(b)
    return hex.EncodeToString(b)
}

// GetRequestID retrieves the request ID from the context.
func GetRequestID(r *http.Request) string {
    if id, ok := r.Context().Value(RequestIDKey).(string); ok {
        return id
    }
    return ""
}

// RequestIDMiddleware injects a unique request ID into every request.
func RequestIDMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        id := r.Header.Get("X-Request-ID")
        if id == "" {
            id = GenerateID()
        }

        w.Header().Set("X-Request-ID", id)
        ctx := context.WithValue(r.Context(), RequestIDKey, id)
        next.ServeHTTP(w, r.WithContext(ctx))
    })
}
```

## 3. Authentication Middleware

```go
// middleware/auth.go
package middleware

import (
    "crypto/hmac"
    "crypto/sha256"
    "crypto/subtle"
    "encoding/hex"
    "net/http"
    "strings"
)

// APIKeyAuth validates API keys from the Authorization header.
func APIKeyAuth(validKeys []string) Middleware {
    keySet := make(map[string]struct{}, len(validKeys))
    for _, k := range validKeys {
        keySet[k] = struct{}{}
    }

    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            auth := r.Header.Get("Authorization")
            if !strings.HasPrefix(auth, "Bearer ") {
                http.Error(w, "missing or malformed authorization header", http.StatusUnauthorized)
                return
            }

            token := strings.TrimPrefix(auth, "Bearer ")
            if _, ok := keySet[token]; !ok {
                http.Error(w, "invalid API key", http.StatusForbidden)
                return
            }

            next.ServeHTTP(w, r)
        })
    }
}

// HMACAuth validates HMAC-signed requests.
func HMACAuth(secret []byte) Middleware {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            signature := r.Header.Get("X-Signature")
            if signature == "" {
                http.Error(w, "missing X-Signature header", http.StatusUnauthorized)
                return
            }

            // Sign the body (in practice, canonicalize the full request)
            body := []byte(r.URL.Path + r.Method)
            mac := hmac.New(sha256.New, secret)
            mac.Write(body)
            expected := hex.EncodeToString(mac.Sum(nil))

            if subtle.ConstantTimeCompare([]byte(signature), []byte(expected)) != 1 {
                http.Error(w, "invalid signature", http.StatusForbidden)
                return
            }

            next.ServeHTTP(w, r)
        })
    }
}

// JWTAuth validates JWT tokens (simplified — use a library in production).
func JWTAuth(secret []byte) Middleware {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            // Parse and validate JWT from Authorization header
            // ... (use github.com/golang-jwt/jwt/v5)
            next.ServeHTTP(w, r)
        })
    }
}
```

## 4. Rate Limiting

```go
// middleware/ratelimit.go
package middleware

import (
    "net/http"
    "sync"
    "time"
)

type visitor struct {
    lastSeen time.Time
    count    int
}

// RateLimiter implements a simple in-memory sliding window rate limiter.
type RateLimiter struct {
    mu       sync.Mutex
    visitors map[string]*visitor
    limit    int
    window   time.Duration
}

func NewRateLimiter(limit int, window time.Duration) *RateLimiter {
    rl := &RateLimiter{
        visitors: make(map[string]*visitor),
        limit:    limit,
        window:   window,
    }

    // Periodic cleanup
    go func() {
        ticker := time.NewTicker(time.Minute)
        defer ticker.Stop()
        for range ticker.C {
            rl.mu.Lock()
            for ip, v := range rl.visitors {
                if time.Since(v.lastSeen) > rl.window*2 {
                    delete(rl.visitors, ip)
                }
            }
            rl.mu.Unlock()
        }
    }()

    return rl
}

func (rl *RateLimiter) Middleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        ip := r.RemoteAddr

        rl.mu.Lock()
        v, exists := rl.visitors[ip]
        if !exists {
            rl.visitors[ip] = &visitor{lastSeen: time.Now(), count: 1}
            rl.mu.Unlock()
            next.ServeHTTP(w, r)
            return
        }

        // Sliding window check
        if time.Since(v.lastSeen) > rl.window {
            v.count = 1
            v.lastSeen = time.Now()
            rl.mu.Unlock()
            next.ServeHTTP(w, r)
            return
        }

        v.count++
        v.lastSeen = time.Now()
        if v.count > rl.limit {
            rl.mu.Unlock()
            w.Header().Set("Retry-After", "60")
            http.Error(w, "rate limit exceeded", http.StatusTooManyRequests)
            return
        }

        rl.mu.Unlock()
        next.ServeHTTP(w, r)
    })
}
```

## 5. Panic Recovery

```go
// middleware/recovery.go
package middleware

import (
    "log"
    "net/http"
    "runtime/debug"
)

func RecoveryMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        defer func() {
            if rec := recover(); rec != nil {
                log.Printf("PANIC recovered: %v\n%s", rec, debug.Stack())
                http.Error(w, "Internal Server Error", http.StatusInternalServerError)
            }
        }()
        next.ServeHTTP(w, r)
    })
}

// RecoveryWithErrorHandler allows custom error handling on panic.
func RecoveryWithErrorHandler(errorHandler func(w http.ResponseWriter, r *http.Request, err interface{})) Middleware {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            defer func() {
                if rec := recover(); rec != nil {
                    log.Printf("PANIC: %v", rec)
                    errorHandler(w, r, rec)
                }
            }()
            next.ServeHTTP(w, r)
        })
    }
}
```

## 6. CORS Middleware

```go
// middleware/cors.go
package middleware

import "net/http"

type CORSOptions struct {
    AllowedOrigins   []string
    AllowedMethods   []string
    AllowedHeaders   []string
    ExposedHeaders   []string
    AllowCredentials bool
    MaxAge           int
}

var DefaultCORSOptions = CORSOptions{
    AllowedOrigins:   []string{"*"},
    AllowedMethods:   []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
    AllowedHeaders:   []string{"Accept", "Authorization", "Content-Type", "X-Request-ID"},
    AllowCredentials: true,
    MaxAge:           300,
}

func CORSMiddleware(opts CORSOptions) Middleware {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            origin := r.Header.Get("Origin")

            // Allow if origin is in allowed list or wildcard
            allowed := false
            for _, o := range opts.AllowedOrigins {
                if o == "*" || o == origin {
                    allowed = true
                    break
                }
            }
            if allowed {
                w.Header().Set("Access-Control-Allow-Origin", origin)
            }

            w.Header().Set("Access-Control-Allow-Methods", join(opts.AllowedMethods))
            w.Header().Set("Access-Control-Allow-Headers", join(opts.AllowedHeaders))

            if len(opts.ExposedHeaders) > 0 {
                w.Header().Set("Access-Control-Expose-Headers", join(opts.ExposedHeaders))
            }
            if opts.AllowCredentials {
                w.Header().Set("Access-Control-Allow-Credentials", "true")
            }
            if opts.MaxAge > 0 {
                w.Header().Set("Access-Control-Max-Age", fmt.Sprintf("%d", opts.MaxAge))
            }

            if r.Method == http.MethodOptions {
                w.WriteHeader(http.StatusNoContent)
                return
            }

            next.ServeHTTP(w, r)
        })
    }
}

func join(strs []string) string {
    if len(strs) == 0 {
        return ""
    }
    result := strs[0]
    for _, s := range strs[1:] {
        result += ", " + s
    }
    return result
}
```

## 7. Timeout Middleware

```go
// middleware/timeout.go
package middleware

import (
    "context"
    "net/http"
    "time"
)

func TimeoutMiddleware(duration time.Duration) Middleware {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            ctx, cancel := context.WithTimeout(r.Context(), duration)
            defer cancel()

            r = r.WithContext(ctx)

            done := make(chan struct{})
            go func() {
                next.ServeHTTP(w, r)
                close(done)
            }()

            select {
            case <-done:
                return
            case <-ctx.Done():
                w.WriteHeader(http.StatusGatewayTimeout)
                w.Write([]byte("request timed out"))
            }
        })
    }
}
```

## Putting It All Together

```go
// main.go
package main

import (
    "log/slog"
    "net/http"
    "os"
    "time"

    "github.com/justinas/alice"
    "github.com/user/myapp/middleware"
)

func main() {
    logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

    // Rate limiter (100 requests/min per IP)
    rateLimiter := middleware.NewRateLimiter(100, time.Minute)

    // Middleware chain
    chain := alice.New(
        middleware.RecoveryMiddleware,
        middleware.RequestIDMiddleware,
        middleware.StructuredLoggingMiddleware(logger),
        rateLimiter.Middleware,
        middleware.TimeoutMiddleware(30*time.Second),
        middleware.CORSMiddleware(middleware.DefaultCORSOptions),
    )

    mux := http.NewServeMux()
    mux.HandleFunc("GET /api/health", healthHandler)
    mux.HandleFunc("POST /api/users", usersHandler)

    // Protected routes get auth middleware
    apiChain := alice.New(
        middleware.APIKeyAuth([]string{"sk-abc123", "sk-def456"}),
    ).Then(mux)

    // Combine
    handler := chain.Then(apiChain)

    slog.Info("server starting", "addr", ":8080")
    http.ListenAndServe(":8080", handler)
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
    w.Write([]byte(`{"status":"ok"}`))
}

func usersHandler(w http.ResponseWriter, r *http.Request) {
    w.Write([]byte(`{"users":[]}`))
}
```

## Testing Middleware

```go
// middleware/logging_test.go
package middleware

import (
    "net/http"
    "net/http/httptest"
    "testing"
)

func TestLoggingMiddleware(t *testing.T) {
    handler := LoggingMiddleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.WriteHeader(http.StatusOK)
        w.Write([]byte("ok"))
    }))

    req := httptest.NewRequest("GET", "/test", nil)
    rec := httptest.NewRecorder()

    handler.ServeHTTP(rec, req)

    if rec.Code != http.StatusOK {
        t.Errorf("expected 200, got %d", rec.Code)
    }
    if rec.Body.String() != "ok" {
        t.Errorf("expected 'ok', got %q", rec.Body.String())
    }
}

func TestRecoveryMiddleware(t *testing.T) {
    handler := RecoveryMiddleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        panic("test panic")
    }))

    req := httptest.NewRequest("GET", "/panic", nil)
    rec := httptest.NewRecorder()

    handler.ServeHTTP(rec, req)

    if rec.Code != http.StatusInternalServerError {
        t.Errorf("expected 500, got %d", rec.Code)
    }
}

func TestChainOrder(t *testing.T) {
    // Middleware should execute in the order they are chained (left to right with alice)
    var order []string

    m1 := func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            order = append(order, "m1-in")
            next.ServeHTTP(w, r)
            order = append(order, "m1-out")
        })
    }
    m2 := func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            order = append(order, "m2-in")
            next.ServeHTTP(w, r)
            order = append(order, "m2-out")
        })
    }

    handler := alice.New(m1, m2).Then(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        order = append(order, "handler")
    }))

    handler.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest("GET", "/", nil))

    expected := []string{"m1-in", "m2-in", "handler", "m2-out", "m1-out"}
    for i, v := range expected {
        if order[i] != v {
            t.Errorf("step %d: expected %q, got %q", i, v, order[i])
        }
    }
}
```