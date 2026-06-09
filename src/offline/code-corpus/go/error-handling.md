---
language: go
tags: [pattern, util]
title: Error Handling
description: The error interface, fmt.Errorf with %w wrapping, errors.Is/As, sentinel errors, and custom error types.
source: pattern
---

```go
package main

import (
	"errors"
	"fmt"
	"os"
)

// --- Sentinel errors ---

var ErrNotFound = errors.New("item not found")
var ErrPermission = errors.New("permission denied")

// --- Custom error type ---

type ValidationError struct {
	Field   string
	Message string
}

func (e *ValidationError) Error() string {
	return fmt.Sprintf("validation failed on %s: %s", e.Field, e.Message)
}

func (e *ValidationError) Unwrap() error {
	return fmt.Errorf("field %s: %s", e.Field, e.Message)
}

// --- Functions returning wrapped errors ---

func findUser(id int) (string, error) {
	if id <= 0 {
		return "", &ValidationError{Field: "id", Message: "must be positive"}
	}
	if id > 100 {
		return "", fmt.Errorf("find user %d: %w", id, ErrNotFound)
	}
	return "Alice", nil
}

func loadConfig(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("loading config %s: %w", path, err)
	}
	_ = data
	return nil
}

// --- Error inspection ---

func main() {
	// Sentinel error with errors.Is
	_, err := findUser(200)
	if errors.Is(err, ErrNotFound) {
		fmt.Println("Got expected not-found error")
	}

	// Custom error type with errors.As
	_, err = findUser(-1)
	var valErr *ValidationError
	if errors.As(err, &valErr) {
		fmt.Printf("Validation error on field %q: %s\n", valErr.Field, valErr.Message)
	}

	// Wrapped error from stdlib
	err = loadConfig("/nonexistent/config.json")
	if err != nil {
		fmt.Println("Load error:", err)
		if errors.Is(err, os.ErrNotExist) {
			fmt.Println("  -> underlying: file does not exist")
		}
	}

	// Simple error check
	result, err := findUser(5)
	if err != nil {
		fmt.Println("Error:", err)
	} else {
		fmt.Println("Found:", result)
	}
}

```
