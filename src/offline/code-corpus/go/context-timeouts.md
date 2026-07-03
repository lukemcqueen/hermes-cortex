---
language: go
tags: [pattern, concurrency, net]
title: Context & Timeouts
description: context.WithCancel, WithTimeout, WithValue, ctx.Done channel, and graceful HTTP server shutdown.
source: pattern
---

```go
package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

// --- Context with timeout ---

func slowOperation(ctx context.Context) (string, error) {
	// Simulate slow work
	select {
	case <-time.After(2 * time.Second):
		return "completed", nil
	case <-ctx.Done():
		return "", ctx.Err()
	}
}

// --- Context with cancellation ---

func worker(ctx context.Context, id int) {
	for {
		select {
		case <-ctx.Done():
			fmt.Printf("Worker %d shutting down: %v\n", id, ctx.Err())
			return
		default:
			fmt.Printf("Worker %d working...\n", id)
			time.Sleep(500 * time.Millisecond)
		}
	}
}

// --- Context with values ---

type contextKey string

const userIDKey contextKey = "user_id"

func authenticatedHandler(ctx context.Context) {
	if uid, ok := ctx.Value(userIDKey).(int); ok {
		fmt.Printf("Authenticated as user %d\n", uid)
	} else {
		fmt.Println("Not authenticated")
	}
}

// --- HTTP server with graceful shutdown ---

func main() {
	// 1. Timeout
	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Second)
	defer cancel()

	result, err := slowOperation(ctx)
	if err != nil {
		fmt.Println("Operation failed:", err)
	} else {
		fmt.Println("Result:", result)
	}

	// 2. Cancel propagation
	ctx2, cancel2 := context.WithCancel(context.Background())
	go worker(ctx2, 1)
	go worker(ctx2, 2)
	time.Sleep(1 * time.Second)
	cancel2() // signal all workers to stop
	time.Sleep(100 * time.Millisecond)

	// 3. Context values
	ctx3 := context.WithValue(context.Background(), userIDKey, 42)
	authenticatedHandler(ctx3)

	// 4. Graceful HTTP shutdown
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, "Hello!")
	})

	srv := &http.Server{Addr: ":8080", Handler: mux}

	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("HTTP serve: %v", err)
		}
	}()

	// Wait for interrupt signal
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig

	// Graceful shutdown with timeout
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Fatalf("Server shutdown: %v", err)
	}
	fmt.Println("Server stopped gracefully")
}

```
