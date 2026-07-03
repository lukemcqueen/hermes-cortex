---
language: go
tags: [io, file]
title: File Operations
description: Read/write files, walk directories, JSON config loading in Go.
source: pattern
---

```go
package main

import (
    "encoding/json"
    "fmt"
    "os"
    "path/filepath"
)

// ReadFile reads a file and returns its contents as a string.
func ReadFile(path string) (string, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return "", fmt.Errorf("reading %s: %w", path, err)
    }
    return string(data), nil
}

// WriteFile writes data to a file, creating directories if needed.
func WriteFile(path, data string) error {
    dir := filepath.Dir(path)
    if err := os.MkdirAll(dir, 0755); err != nil {
        return fmt.Errorf("creating dir %s: %w", dir, err)
    }
    return os.WriteFile(path, []byte(data), 0644)
}

// WalkFiles walks a directory, calling fn for each file.
func WalkFiles(root string, fn func(path string) error) error {
    return filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
        if err != nil {
            return err
        }
        if info.IsDir() {
            return nil
        }
        return fn(path)
    })
}

// LoadJSON reads and unmarshals a JSON config file.
func LoadJSON(path string, target interface{}) error {
    data, err := os.ReadFile(path)
    if err != nil {
        return err
    }
    return json.Unmarshal(data, target)
}

// FileExists checks if a file exists and is not a directory.
func FileExists(path string) bool {
    info, err := os.Stat(path)
    return err == nil && !info.IsDir()
}

```
