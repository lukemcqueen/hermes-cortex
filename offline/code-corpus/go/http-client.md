---
language: go
tags: [pattern, web, net]
title: HTTP Client
description: http.Get/Post/Do, custom headers, timeouts, JSON request/response decoding, and client configuration.
source: pattern
---

```go
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"
)

type Todo struct {
	UserID int    `json:"userId"`
	ID     int    `json:"id"`
	Title  string `json:"title"`
	Done   bool   `json:"completed"`
}

// --- Custom HTTP client ---

func newHTTPClient(timeout time.Duration) *http.Client {
	return &http.Client{
		Timeout: timeout,
		Transport: &http.Transport{
			MaxIdleConns:        10,
			IdleConnTimeout:     30 * time.Second,
			DisableCompression:  false,
		},
	}
}

// getJSON performs a GET and decodes JSON into target.
func getJSON(ctx context.Context, client *http.Client, url string, target interface{}) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return fmt.Errorf("creating request: %w", err)
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "go-http-client/1.0")

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("executing request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("unexpected status %d: %s", resp.StatusCode, string(body))
	}

	if err := json.NewDecoder(resp.Body).Decode(target); err != nil {
		return fmt.Errorf("decoding response: %w", err)
	}
	return nil
}

// postJSON sends a POST with JSON body and decodes the response.
func postJSON(ctx context.Context, client *http.Client, url string, payload, target interface{}) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshalling payload: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("creating request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("executing request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("request failed with %d: %s", resp.StatusCode, string(body))
	}

	if target != nil {
		if err := json.NewDecoder(resp.Body).Decode(target); err != nil {
			return fmt.Errorf("decoding response: %w", err)
		}
	}
	return nil
}

func main() {
	client := newHTTPClient(10 * time.Second)
	ctx := context.Background()

	// GET request
	var todo Todo
	if err := getJSON(ctx, client, "https://jsonplaceholder.typicode.com/todos/1", &todo); err != nil {
		log.Fatal(err)
	}
	fmt.Printf("GET /todos/1: %+v\n", todo)

	// POST request
	newTodo := map[string]interface{}{
		"title":  "foo",
		"body":   "bar",
		"userId": 1,
	}
	var created map[string]interface{}
	if err := postJSON(ctx, client, "https://jsonplaceholder.typicode.com/todos", newTodo, &created); err != nil {
		log.Fatal(err)
	}
	fmt.Printf("POST response: %+v\n", created)
}

```
