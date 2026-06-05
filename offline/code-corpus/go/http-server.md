---
language: go
tags: [web, api, server]
title: HTTP Server
description: Basic HTTP server with routing, middleware, JSON responses, and graceful shutdown.
source: pattern
---

```go
package main

import (
    "encoding/json"
    "log"
    "net/http"
    "os"
    "os/signal"
    "syscall"
)

func main() {
    mux := http.NewServeMux()
    mux.HandleFunc("/api/health", handleHealth)
    mux.HandleFunc("/api/items", handleItems)
    mux.HandleFunc("/api/items/", handleItemByID)

    server := &http.Server{Addr: ":8080", Handler: loggingMiddleware(mux)}

    // Graceful shutdown
    go func() {
        sig := make(chan os.Signal, 1)
        signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
        <-sig
        log.Println("Shutting down...")
        server.Close()
    }()

    log.Println("Listening on :8080")
    log.Fatal(server.ListenAndServe())
}

func loggingMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        log.Printf("%s %s", r.Method, r.URL.Path)
        next.ServeHTTP(w, r)
    })
}

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(status)
    json.NewEncoder(w).Encode(data)
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
    writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func handleItems(w http.ResponseWriter, r *http.Request) {
    if r.Method == "GET" {
        writeJSON(w, http.StatusOK, []interface{}{})
    } else {
        http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
    }
}

func handleItemByID(w http.ResponseWriter, r *http.Request) {
    writeJSON(w, http.StatusOK, map[string]interface{}{"id": 1})
}

```
